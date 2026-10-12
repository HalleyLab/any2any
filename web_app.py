"""Local conversion engine for the shared desktop and GitHub Pages interface."""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
import webbrowser
import zipfile

import any2any

ROOT = Path(__file__).resolve().parent
PORT = 8765
PAGES = "https://halleylab.github.io"


class Batch:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="any2any-")
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.files = {}
        self.cancel = threading.Event()
        self.state = "ready"
        self.done = 0
        self.total = 0
        self.current = ""
        self.errors = []
        self.download = None
        self.deleted = False
        self.updated = time.monotonic()

    def status(self):
        return {"state": self.state, "done": self.done, "total": self.total,
                "current": self.current, "errors": list(self.errors),
                "download": self.download.name if self.download else None}

    def run(self, target, sources):
        self.total = len(sources)
        try:
            for source, stem in zip(sources, any2any.batch_names(sources)):
                self.current = source.name
                try:
                    any2any.convert(source, target, self.output, self.cancel, output_stem=stem)
                except any2any.Cancelled:
                    raise
                except Exception as error:
                    self.errors.append({"name": source.name, "message": str(error)})
                self.done += 1
            any2any.check_cancel(self.cancel)
            results = sorted(self.output.iterdir())
            if len(results) == 1:
                self.download = results[0]
            elif results:
                self.download = self.root / "Any2Any.zip"
                with zipfile.ZipFile(self.download, "w", compression=zipfile.ZIP_STORED) as archive:
                    for result in results:
                        any2any.check_cancel(self.cancel)
                        archive.write(result, result.name)
            self.state = "complete" if not self.errors else "partial" if results else "failed"
        except any2any.Cancelled:
            self.download = None
            self.state = "cancelled"
        except Exception as error:
            logging.exception("Batch failed")
            self.errors.append({"name": "Download", "message": str(error)})
            self.download = None
            self.state = "failed"
        finally:
            self.current = ""
            self.updated = time.monotonic()
            if self.deleted:
                self.temp.cleanup()


class Engine(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=PORT):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.batches = {}
        self.lock = threading.RLock()
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.stopping = threading.Event()

    def expire(self):
        while not self.stopping.wait(60):
            with self.lock:
                for key, batch in list(self.batches.items()):
                    if batch.state != "running" and time.monotonic() - batch.updated > 3600:
                        batch.temp.cleanup()
                        del self.batches[key]

    def close(self):
        self.stopping.set()
        for batch in self.batches.values():
            batch.deleted = True
            batch.cancel.set()
            if batch.state != "running":
                batch.temp.cleanup()
        any2any.close_office()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed(self):
        return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                and self.headers.get("Origin") in (None, self.server.origin, PAGES))

    def headers_out(self, code, mime="application/json", length=None):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        origin = self.headers.get("Origin")
        if self.allowed() and origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        if length is not None:
            self.send_header("Content-Length", str(length))

    def reply(self, code, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.headers_out(code, length=len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        if not self.allowed():
            return self.reply(403, {"error": "Origin or host not allowed."})
        self.headers_out(204, length=0)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Any2Any-Token, X-File-Name, X-File-Group")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def body_json(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 16384:
            raise ValueError("Invalid request size.")
        data = json.loads(self.rfile.read(size))
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def dispatch(self):
        try:
            if not self.allowed():
                return self.reply(403, {"error": "Origin or host not allowed."})
            path = urlsplit(self.path).path
            if self.command == "GET" and path == "/api/health":
                return self.reply(200, {"app": "Any2Any", "token": self.server.token})
            if not path.startswith("/api/"):
                if self.command != "GET":
                    return self.reply(405, {"error": "Method not allowed."})
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/index.html": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8"),
                          "/icon.svg": ("icon.svg", "image/svg+xml")}
                if path not in assets:
                    return self.reply(404, {"error": "Not found."})
                name, mime = assets[path]
                data = (ROOT / "docs" / name).read_bytes()
                self.headers_out(200, mime, len(data))
                self.end_headers()
                return self.wfile.write(data)
            if not secrets.compare_digest(self.headers.get("X-Any2Any-Token", ""), self.server.token):
                return self.reply(403, {"error": "Reconnect to the local engine."})
            with self.server.lock:
                if self.command == "POST" and path == "/api/shutdown":
                    self.reply(200, {"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if self.command == "POST" and path == "/api/batches":
                    key = secrets.token_hex(16)
                    self.server.batches[key] = Batch()
                    return self.reply(201, {"id": key})
                match = re.fullmatch(r"/api/batches/([a-f0-9]{32})(?:/(files|convert|cancel|download)(?:/([a-f0-9]{16}))?)?", path)
                if not match or match[1] not in self.server.batches:
                    return self.reply(404, {"error": "Batch expired. Add your files again."})
                batch = self.server.batches[match[1]]
                batch.updated = time.monotonic()
                action, file_id = match[2], match[3]
                if self.command == "GET" and action is None:
                    return self.reply(200, batch.status())
                if self.command == "DELETE" and action is None:
                    batch.deleted = True
                    batch.cancel.set()
                    del self.server.batches[match[1]]
                    if batch.state != "running":
                        batch.temp.cleanup()
                    return self.reply(200, {"ok": True})
                if self.command == "POST" and action == "cancel":
                    if batch.state == "running":
                        batch.cancel.set()
                    return self.reply(200, {"ok": True})
                if self.command == "GET" and action == "download":
                    if batch.state not in ("complete", "partial") or not batch.download:
                        return self.reply(409, {"error": "No download available."})
                    download = batch.download
                else:
                    if batch.state != "ready":
                        return self.reply(409, {"error": "Create a new batch to change these files."})
                    if self.command == "DELETE" and action == "files" and file_id in batch.files:
                        batch.files.pop(file_id)["path"].unlink()
                        return self.reply(200, {"ok": True})
                    if self.command == "POST" and action == "files" and file_id is None:
                        return self.upload(batch)
                    if self.command == "POST" and action == "convert":
                        data = self.body_json()
                        target = data.get("target")
                        source_ids = data.get("sources", [key for key, item in batch.files.items() if item["targets"]])
                        if not isinstance(source_ids, list) or not source_ids or not all(isinstance(key, str) and key in batch.files for key in source_ids):
                            raise ValueError("Select at least one input file.")
                        convertible = [batch.files[key] for key in source_ids]
                        if not all(target in item["targets"] for item in convertible):
                            raise ValueError("Choose a format supported by every input file.")
                        batch.state = "running"
                        batch.total = len(convertible)
                        threading.Thread(target=batch.run, args=(target, [item["path"] for item in convertible]), daemon=True).start()
                        return self.reply(202, batch.status())
                    return self.reply(404, {"error": "Not found."})
            with download.open("rb") as stream:
                self.headers_out(200, "application/octet-stream", download.stat().st_size)
                self.end_headers()
                shutil.copyfileobj(stream, self.wfile, 1024 * 1024)
        except (ValueError, UnicodeError) as error:
            self.reply(400, {"error": str(error)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            logging.exception("Request failed")
            self.reply(500, {"error": str(error)})

    def upload(self, batch):
        name = unquote(self.headers.get("X-File-Name", ""), errors="strict")
        group = self.headers.get("X-File-Group", "")
        if not name or name in (".", "..") or any(char in name for char in '\\/:\0<>"|?*') or name.endswith((".", " ")) or Path(name).is_reserved() or any(ord(char) < 32 for char in name):
            raise ValueError("Invalid file name.")
        if not re.fullmatch(r"[0-9]{1,12}", group):
            raise ValueError("Invalid file group.")
        size = int(self.headers.get("Content-Length", "-1"))
        if size < 0:
            raise ValueError("File length required.")
        folder = batch.root / "inputs" / group
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        try:
            with path.open("xb") as stream:
                remaining = size
                while remaining:
                    data = self.rfile.read(min(1024 * 1024, remaining))
                    if not data:
                        raise ValueError("Upload interrupted. Add the file again.")
                    stream.write(data)
                    remaining -= len(data)
        except FileExistsError:
            raise ValueError("This file is already in this selection.")
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        file_id = secrets.token_hex(8)
        try:
            targets = any2any.targets(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        batch.files[file_id] = {"path": path, "targets": targets}
        return self.reply(201, {"id": file_id, "name": name, "size": size, "targets": targets})


def open_app(url):
    for executable in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
                       Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe"):
        if executable.is_file():
            subprocess.Popen([str(executable), f"--app={url}", "--window-size=560,740"])
            return
    webbrowser.open(url)


def launch(port=PORT, open_window=True):
    url = f"http://127.0.0.1:{port}"
    try:
        with urlopen(url + "/api/health", timeout=2) as response:
            if json.load(response).get("app") == "Any2Any":
                if open_window:
                    open_app(url)
                return
    except (OSError, ValueError):
        pass
    engine = Engine(port)
    threading.Thread(target=engine.expire, daemon=True).start()
    if open_window:
        open_app(url)
    try:
        engine.serve_forever()
    finally:
        engine.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Any2Any local web engine")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    (ROOT / "tools").mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / "tools/web-engine.log", level=logging.ERROR)
    try:
        launch(args.port, not args.no_open)
    except Exception:
        logging.exception("Engine could not start")
        if not args.no_open:
            import tkinter.messagebox
            tkinter.messagebox.showerror("Any2Any", "The local engine could not start. See tools/web-engine.log.")
        raise
