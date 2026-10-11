"""Any2Any: local batch conversion. Run without arguments for the English GUI."""
import argparse
import atexit
import html
import re
import uuid
from urllib.parse import quote
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import warnings
import zipfile

import imageio_ffmpeg
import pypandoc
import pymupdf
from PIL import Image, ImageOps
import pillow_heif

import scientific
import source_formats
import research_formats
import imaging_formats
import genomics_formats
import lab_signals
import pdf_latex

EXTRA_CONVERTERS = (source_formats, imaging_formats, lab_signals, scientific, research_formats, genomics_formats, pdf_latex)
FORMAT_LABELS = {"tex": "tex (text)", "tex-layout": "tex (layout)"}

ROOT = Path(__file__).resolve().parent
pillow_heif.register_heif_opener()
Image.init()
warnings.simplefilter("error", Image.DecompressionBombWarning)

INPUTS = {
    "Video": "mp4 m4v mkv mov avi webm flv wmv ts mts m2ts mpg mpeg vob 3gp 3g2 ogv mxf lrv asf rm rmvb f4v",
    "Audio": "mp3 wav flac aac m4a ogg opus aiff aif wma ac3 amr au caf mka ape alac aifc oga",
    "Images": "png jpg jpeg jfif webp bmp tif tiff gif ico avif heic heif tga psd dds ppm pgm pbm pnm pcx jp2 j2k qoi blp icns dib svg",
    "Documents": "doc docx odt rtf txt md markdown html htm rst tex latex epub fb2 org",
    "Spreadsheets": "xls xlsx xlsm xlsb ods csv tsv fods",
    "Presentations": "ppt pptx pps ppsx odp fodp",
    "PDF/Pages": "pdf xps oxps cbz",
    "Subtitles": "srt vtt ass ssa",
}
OUTPUTS = {
    "Video": "mp4 mkv mov webm avi ts flv mpg ogv 3gp mp3 wav flac m4a aac ogg opus aiff wma ac3 au png jpg tiff",
    "Audio": "mp3 wav flac m4a aac ogg opus aiff wma ac3 au",
    "Images": "png jpg webp bmp tiff gif ico avif heic ppm tga jp2 pdf",
    "Documents": "docx doc odt rtf pdf txt md html epub rst tex org",
    "Spreadsheets": "xlsx xls ods csv tsv pdf",
    "Presentations": "pptx ppt odp pdf",
    "PDF/Pages": "png jpg webp tiff svg txt pdf",
    "Subtitles": "srt vtt ass ssa",
}
EXTRA_CATEGORIES = {kind for converter in EXTRA_CONVERTERS for kind in converter.INPUTS}
for converter in EXTRA_CONVERTERS:
    INPUTS.update(converter.INPUTS)
    OUTPUTS.update(converter.OUTPUTS)

AUDIO = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": [], "flac": [],  # Lossless codecs follow the original decoded precision.
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "aac": ["-c:a", "aac", "-b:a", "192k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
    "aiff": [],
    "wma": ["-c:a", "wmav2", "-b:a", "192k"],
    "ac3": ["-c:a", "ac3", "-b:a", "384k", "-ar", "48000"],
    "au": [],
}
VIDEO = {
    "mp4": ["-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart"],
    "mkv": ["-c:v", "libx264", "-crf", "20", "-c:a", "aac"],
    "mov": ["-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"],
    "avi": ["-c:v", "mpeg4", "-q:v", "3", "-c:a", "libmp3lame"],
    "ts": ["-c:v", "libx264", "-crf", "20", "-c:a", "aac"],
    "flv": ["-c:v", "libx264", "-crf", "20", "-c:a", "aac"],
    "mpg": ["-c:v", "mpeg2video", "-q:v", "3", "-r", "25", "-c:a", "mp2", "-ar", "48000"],
    "ogv": ["-c:v", "libtheora", "-q:v", "7", "-c:a", "libvorbis"],
    "3gp": ["-c:v", "mpeg4", "-q:v", "3", "-c:a", "aac", "-ar", "44100"],
}
READERS = {"md": "markdown", "markdown": "markdown", "html": "html", "htm": "html",
           "rst": "rst", "tex": "latex", "latex": "latex", "epub": "epub",
           "fb2": "fb2", "org": "org", "docx": "docx", "odt": "odt"}
WRITERS = {"md": "markdown", "html": "html5", "epub": "epub3", "rst": "rst",
           "tex": "latex", "org": "org", "docx": "docx", "odt": "odt", "txt": "plain"}
OFFICE_DOC = {"doc", "docx", "odt", "rtf", "txt", "html", "htm"}
OFFICE_TARGET = {"doc", "docx", "odt", "rtf", "pdf", "txt", "html"}

class Cancelled(Exception):
    pass

def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("Cancelled")

def category(path):
    ext = Path(path).suffix.lower().lstrip(".")
    return next((kind for kind, extensions in INPUTS.items() if ext in extensions.split()), None)

def targets(path):
    kind = category(path)
    result = OUTPUTS[kind].split() if kind and kind not in EXTRA_CATEGORIES else []
    for converter in EXTRA_CONVERTERS:
        result.extend(converter.targets(path))
    return list(dict.fromkeys(result))

def soffice():
    candidates = [ROOT / "tools/libreoffice/program/soffice.exe"]
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(env):
            candidates.append(Path(os.environ[env]) / "LibreOffice/program/soffice.exe")
    found = shutil.which("soffice")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("LibreOffice was not found. See the component instructions in README.md.")

def run_command(args, cancel=None, cwd=None, timeout=7200):
    check_cancel(cancel)
    with subprocess.Popen([str(arg) for arg in args], cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        deadline = time.monotonic() + timeout
        try:
            while True:
                check_cancel(cancel)
                if time.monotonic() > deadline:
                    raise RuntimeError("Conversion timed out.")
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            stop_process(process)
            process.communicate()
            raise
        message = (stderr + stdout).decode("utf-8", errors="replace").strip()
        if process.returncode:
            raise RuntimeError(message[-3000:] or f"Converter exit code: {process.returncode}")
        return message

def office_cli_convert(source, ext, folder, scratch, cancel):
    profile = scratch / "lo-profile"
    (profile / "user").mkdir(parents=True, exist_ok=True)
    (profile / "user/registrymodifications.xcu").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '</item></oor:items>', encoding="utf-8")
    filters = {
        "csv": "csv:Text - txt - csv (StarCalc):44,34,76",
        "tsv": "tsv:Text - txt - csv (StarCalc):9,34,76",
        "txt": "txt:Text (encoded):UTF8",
        "html": "html:HTML (StarWriter)",
    }
    args = [soffice(), f"-env:UserInstallation={profile.as_uri()}",
            "--headless", "--nologo", "--nodefault", "--norestore"]
    if source.suffix.lower() in (".csv", ".tsv"):
        sep = 44 if source.suffix.lower() == ".csv" else 9
        args += [f"--infilter=Text - txt - csv (StarCalc):{sep},34,76"]
    args += ["--convert-to", filters.get(ext, ext), "--outdir", folder, source]
    message = run_command(args, cancel, timeout=300)
    result = folder / f"{source.stem}.{ext}"
    if not result.is_file() or not result.stat().st_size:
        raise RuntimeError("Office conversion produced no file: " + message[-1500:])
    return result

_office = None
_office_lock = threading.Lock()

def stop_process(process):
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            process.kill()
        process.wait(timeout=10)

def close_office():
    global _office
    if _office is not None:
        session, _office = _office, None
        stop_process(session["process"])
        for attempt in range(20):
            try:
                session["profile"].cleanup()
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.1)

atexit.register(close_office)

def office_convert(source, ext, folder, scratch, cancel):
    global _office
    executable = Path(soffice())
    python = executable.parent / "python.exe"
    if not python.is_file():
        return office_cli_convert(source, ext, folder, scratch, cancel)
    result = folder / f"{source.stem}.{ext}"
    with _office_lock:
        check_cancel(cancel)
        if _office is None or _office["process"].poll() is not None:
            close_office()
            profile = tempfile.TemporaryDirectory(prefix="any2any-office-", delete=False)
            pipe = "any2any-" + uuid.uuid4().hex
            try:
                process = subprocess.Popen(
                    [str(executable), f"-env:UserInstallation={Path(profile.name).as_uri()}",
                     "--headless", "--nologo", "--nodefault", "--norestore",
                     f"--accept=pipe,name={pipe};urp;StarOffice.ServiceManager"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except BaseException:
                profile.cleanup()
                raise
            _office = {"process": process, "profile": profile, "pipe": pipe}
        try:
            run_command([python, "-X", "utf8", ROOT / "office_worker.py", _office["pipe"], source, result],
                        cancel, timeout=300)
        except BaseException:
            close_office()
            raise
    if not result.is_file() or not result.stat().st_size:
        raise RuntimeError("Office conversion produced no file.")
    return result

def convert_document(source, ext, folder, scratch, cancel):
    original_stem = source.stem
    kind = category(source)
    src_ext = source.suffix.lower().lstrip(".")
    if kind in ("Spreadsheets", "Presentations") or (src_ext in OFFICE_DOC and ext in OFFICE_TARGET):
        return office_convert(source, ext, folder, scratch, cancel)
    intermediate = scratch / "intermediate"
    intermediate.mkdir(exist_ok=True)
    if src_ext not in READERS:
        source = office_convert(source, "docx", intermediate, scratch, cancel)
        src_ext = "docx"
    needs_office = ext in ("pdf", "doc", "rtf")
    target = intermediate / "converted.docx" if needs_office else folder / f"{source.stem}.{ext}"
    writer = "docx" if needs_office else WRITERS[ext]
    args = [pypandoc.get_pandoc_path(), source, "--from", READERS[src_ext],
            "--to", writer, "--standalone", "--resource-path", source.parent, "-o", target]
    if not needs_office and ext == "html":
        args += ["--embed-resources"]
    elif not needs_office and ext in ("md", "rst", "tex", "org"):
        args += ["--extract-media", "assets"]
    run_command(args, cancel, cwd=folder, timeout=300)
    if needs_office:
        result = office_convert(target, ext, folder, scratch, cancel)
        destination = folder / f"{original_stem}.{ext}"
        if result != destination:
            result.rename(destination)
        return destination
    return target

def rgb_on_white(image):
    rgba = image.convert("RGBA")
    result = Image.new("RGB", image.size, "white")
    result.paste(rgba, mask=rgba.getchannel("A"))
    return result

def save_image(image, target):
    ext = target.suffix.lower()
    if ext in (".jpg", ".bmp", ".ppm", ".pdf"):
        image = rgb_on_white(image)
    elif ext == ".gif":
        image = image.convert("RGBA")
    if ext == ".ico":
        image = image.convert("RGBA")
        image.thumbnail((256, 256))
    options = {"quality": 95} if ext in (".jpg", ".webp", ".avif", ".heic") else {}
    if ext == ".ico":
        options["sizes"] = [image.size]
    if ext == ".webp":
        options.update(lossless=True, exact=True)
    if ext == ".png":
        from PIL.PngImagePlugin import PngInfo
        metadata = PngInfo()
        for key, value in image.info.items():
            if isinstance(value, str):
                metadata.add_text(key, value)
        options.update(compress_level=3, pnginfo=metadata)
    if ext in (".png", ".jpg", ".tiff", ".pdf") and "dpi" in image.info:
        options["dpi"] = image.info["dpi"]
    image.save(target, **options)
    if ext != ".pdf":
        with Image.open(target) as verified:
            verified.load()

def convert_image(source, ext, folder, cancel):
    if source.suffix.lower() == ".svg":
        return convert_pages(source, ext, folder, cancel)
    import json
    import numpy as np
    from imaging_formats import json_default
    metadata = {"source_format": source.suffix, "frames": [], "preserved_files": []}
    with Image.open(source) as original:
        count = getattr(original, "n_frames", 1)
        durations, frames = [], []
        multi = count > 1 and ext in ("gif", "webp", "png", "tiff", "pdf", "avif")
        # ponytail: multi-frame encoders buffer frames; split to JPG per frame if memory is insufficient.
        for index in range(count):
            check_cancel(cancel)
            original.seek(index)
            frame = ImageOps.exif_transpose(original.copy())
            metadata["frames"].append({"mode": frame.mode, "size": frame.size, "info": frame.info, "palette": frame.getpalette()})
            if (ext in ("jpg", "gif", "avif", "heic", "ico", "pdf", "bmp", "ppm") or
                (frame.mode in ("P", "I", "I;16", "F") and ext not in ("png", "tiff")) or (multi and ext == "webp")):
                backup = folder / f"frame_{index:04d}.npy"
                np.save(backup, np.asarray(frame), allow_pickle=False)
                metadata["preserved_files"].append({"file": backup.name, "frame": index, "role": "Original decoded image samples."})
            if multi:
                frames.append(rgb_on_white(frame) if ext == "pdf" else frame.convert("RGBA"))
                durations.append(original.info.get("duration", 100))
            else:
                suffix = f"_{index + 1:04d}" if count > 1 else ""
                save_image(frame, folder / f"{source.stem}{suffix}.{ext}")
        if multi:
            options = {"save_all": True, "append_images": frames[1:]}
            if ext in ("gif", "webp", "png", "avif"):
                options.update(duration=durations, loop=original.info.get("loop", 0))
            if ext == "webp":
                options.update(lossless=True, exact=True)
            result = folder / f"{source.stem}.{ext}"
            frames[0].save(result, **options)
            if ext != "pdf":
                with Image.open(result) as verified:
                    if getattr(verified, "n_frames", 1) != count:
                        raise RuntimeError("Output frame count differs; the result was not saved.")
                    for index in range(count):
                        verified.seek(index)
                        verified.load()
        (folder / "image_metadata.json").write_text(json.dumps(metadata, indent=2, default=json_default), encoding="utf-8")

def convert_pages(source, ext, folder, cancel):
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError("This file is password-protected. Decrypt it first.")
        if not document.page_count:
            raise ValueError("The file contains no convertible pages.")
        if ext == "pdf":
            result = folder / f"{source.stem}.pdf"
            if document.is_pdf:
                document.save(result)
            else:
                result.write_bytes(document.convert_to_pdf())
        elif ext == "txt":
            with (folder / f"{source.stem}.txt").open("w", encoding="utf-8") as output:
                for page in document:
                    check_cancel(cancel)
                    output.write(page.get_text() + "\n\f\n")
        else:
            for index, page in enumerate(document):
                check_cancel(cancel)
                result = folder / f"{source.stem}_{index + 1:04d}.{ext}"
                if ext == "svg":
                    result.write_text(page.get_svg_image(), encoding="utf-8")
                else:
                    pix = page.get_pixmap(dpi=150, alpha=True)
                    image = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
                    save_image(image, result)

def convert_media(source, ext, folder, cancel):
    result = folder / f"{source.stem}.{ext}"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if ext in ("png", "jpg", "tiff"):
        safe_stem = source.stem.replace("%", "_")
        pattern = folder / f"{safe_stem}_%06d.{ext}"
        args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-protocol_whitelist", "file,pipe,data,crypto", "-i", source,
                "-map", "0:v:0", "-an", "-fps_mode", "passthrough"]
        args += ["-q:v", "2"] if ext == "jpg" else ["-pix_fmt", "rgb48le"] if ext == "tiff" else []
        run_command(args + ["-start_number", "1", pattern], cancel)
        frames = sorted(folder.glob(f"*.{ext}"))
        if not frames:
            raise ValueError("No video frames were decoded.")
        for frame in (frames[0], frames[-1]):
            with Image.open(frame) as verified:
                verified.load()
        return
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
            "-protocol_whitelist", "file,pipe,data,crypto", "-i", source]
    if category(source) == "Subtitles":
        codec = {"srt": "srt", "vtt": "webvtt", "ass": "ass", "ssa": "ass"}[ext]
        args += ["-map", "0:s:0", "-c:s", codec]
    elif ext in AUDIO:
        if ext in ("wav", "aiff", "au", "flac"):
            info = run_command([ffmpeg, "-hide_banner", "-nostdin", "-protocol_whitelist", "file,pipe,data,crypto", "-i", source,
                                "-map", "0:a:0", "-af", "ashowinfo", "-frames:a", "1", "-f", "null", "-"], cancel)
            match = re.search(r"fmt:(\w+) channels:(\d+) .*?rate:(\d+)", info)
            if not match:
                raise ValueError("Could not determine the original audio precision and channels.")
            sample_format, channels, rate = match.groups()
            sample_format = sample_format.rstrip("p")
            codec = {"u8": "pcm_s16", "s16": "pcm_s16", "s32": "pcm_s32", "flt": "pcm_f32", "dbl": "pcm_f64"}.get(sample_format)
            if codec is None or (ext == "flac" and sample_format in ("flt", "dbl")):
                raise ValueError("This audio precision cannot be kept in the selected format. Use WAV or AIFF.")
            options = ["-c:a", "flac"] if ext == "flac" else ["-c:a", codec + ("le" if ext == "wav" else "be")]
            args += ["-map", "0:a:0", "-vn", "-ac", channels, "-ar", rate] + options
        else:
            args += ["-map", "0:a:0", "-vn", "-ac", "2"] + AUDIO[ext]
    else:
        args += ["-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-ac", "2",
                 "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p"] + VIDEO[ext]
    run_command(args + [result], cancel)
    if ext in ("wav", "aiff", "au", "flac"):
        hashes = [run_command([ffmpeg, "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe,data,crypto", "-i", path,
                               "-map", "0:a:0", "-vn", "-c:a", "pcm_f64le", "-f", "hash", "-hash", "sha256", "-"], cancel)
                  for path in (source, result)]
        if hashes[0] != hashes[1]:
            raise ValueError("Audio output changed decoded samples. Use WAV or AIFF for this precision.")
    if category(source) != "Subtitles":
        run_command([ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", result,
                     "-t", "1", "-f", "null", "-"], cancel, timeout=120)

def convert(source, ext, output, cancel=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    ext = ext.lower().lstrip(".")
    if not source.is_file():
        raise ValueError(f"File not found: {source}")
    kind = category(source)
    if ext not in targets(source):
        raise ValueError(f"Unsupported conversion: {source.suffix} → .{ext}")
    check_cancel(cancel)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="any2any-") as scratch_name, \
         tempfile.TemporaryDirectory(prefix=".any2any-", dir=output.parent) as staging_name:
        folder, scratch = Path(staging_name), Path(scratch_name)
        sidecar = None
        converter = next((module for module in EXTRA_CONVERTERS if module.handles(source, ext)), None)
        if converter is not None:
            input_source = source
            if converter is scientific and scientific.needs_office(source):
                prepared = scratch / "tables"
                prepared.mkdir()
                input_source = office_convert(source, "xlsx", prepared, scratch, cancel)
            sidecar = converter.convert(input_source, ext, folder, lambda: check_cancel(cancel))
        elif kind in ("Video", "Audio", "Subtitles"):
            convert_media(source, ext, folder, cancel)
        elif kind == "Images":
            convert_image(source, ext, folder, cancel)
        elif kind == "PDF/Pages":
            convert_pages(source, ext, folder, cancel)
        else:
            convert_document(source, ext, folder, scratch, cancel)
        check_cancel(cancel)
        output_ext = "tex" if ext == "tex-layout" else ext
        companions = set()
        manifests = []
        if converter in (scientific, imaging_formats):
            import json
            manifests = [sidecar] if sidecar else list(folder.glob("*.json"))
            for manifest in manifests:
                for item in json.loads(manifest.read_text(encoding="utf-8")).get("preserved_files", []):
                    companions.add(folder / item["file"])
        elif converter is None and kind == "Images" and (folder / "image_metadata.json").exists():
            manifests = [folder / "image_metadata.json"]
        produced = [file for file in folder.glob(f"*.{output_ext}") if file != sidecar and file not in companions]
        if not produced or any(not file.stat().st_size for file in produced):
            raise RuntimeError("No valid output was produced.")
        containers = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml",
                      "pptx": "ppt/presentation.xml", "odt": "content.xml",
                      "ods": "content.xml", "odp": "content.xml", "epub": "META-INF/container.xml"}
        for file in produced:
            if ext in containers:
                with zipfile.ZipFile(file) as archive:
                    archive.getinfo(containers[ext])
            if ext == "pdf":
                with pymupdf.open(file) as document:
                    if not document.page_count:
                        raise RuntimeError("The output PDF has no pages.")
        return publish_files(folder, produced, source, output, cancel, manifests)

def publish_files(folder, produced, source, output, cancel, manifests):
    files = sorted(file for file in folder.rglob("*") if file.is_file())
    destinations = {}
    reserved = []
    try:
        asset_index = 0
        source_stem = source.with_suffix("").stem if genomics_formats.sequence_gzip(source) else source.stem
        tex_assets = any(file.suffix.lower() == ".tex" for file in produced)
        asset_stem = re.sub(r"[^A-Za-z0-9_-]", "_", source_stem)[:100] if tex_assets else source_stem
        for file in files:
            if file in produced:
                name = f"{source_stem}{file.suffix}" if len(produced) == 1 else file.name
            else:
                asset_index += 1
                name = f"{asset_stem}_asset_{asset_index}{file.suffix}"
            candidate = output / name
            index = 1
            while True:
                try:
                    with candidate.open("xb"):
                        pass
                    break
                except FileExistsError:
                    candidate = output / f"{Path(name).stem}_{index}{Path(name).suffix}"
                    index += 1
            reserved.append(candidate)
            destinations[file] = candidate
        import json
        for file in manifests:
            data = json.loads(file.read_text(encoding="utf-8"))
            for item in data.get("preserved_files", []):
                item["file"] = destinations[folder / item["file"]].name
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        replacements = {}
        # Notebook archives are not linked resources; filenames in code must remain unchanged.
        for file in files:
            if file not in produced and file.suffix.lower() != ".ipynb":
                old = file.relative_to(folder).as_posix()
                new = destinations[file].name
                replacements[old] = new
                replacements[quote(old, safe="/")] = quote(new, safe="")
                replacements[html.escape(old, quote=True)] = html.escape(new, quote=True)
                replacements[old.replace("_", r"\_")] = new
        for file in produced:
            if file.suffix.lower() in (".md", ".html", ".htm", ".tex", ".rst", ".org"):
                text = file.read_text(encoding="utf-8")
                for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
                    text = text.replace(old, new)
                file.write_text(text, encoding="utf-8")
        for file, destination in destinations.items():
            check_cancel(cancel)
            os.replace(file, destination)
        return [destinations[file] for file in produced]
    except BaseException:
        for file in reserved:
            file.unlink(missing_ok=True)
        raise

def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title("Any2Any")
    root.minsize(360, 0)
    root.resizable(False, False)
    style = ttk.Style(root)
    style.theme_use("vista")
    style.configure(".", font=("Segoe UI", 10))
    main = ttk.Frame(root, padding=14)
    main.pack(fill="both", expand=True)
    toolbar = ttk.Frame(main)
    toolbar.pack(fill="x")
    controls = ttk.Frame(main)
    controls.pack(fill="x", pady=12)
    ttk.Label(controls, text="To").pack(side="left")
    files, details, events, cancel = [], [], queue.Queue(), threading.Event()
    state = {"busy": False, "finished": False}
    target = tk.StringVar()
    output = tk.StringVar(value=str(ROOT / "output"))
    status = tk.StringVar(value="Choose files to start.")
    formats = ttk.Combobox(controls, textvariable=target, width=14, state="readonly")
    formats.pack(side="left", padx=10)
    ttk.Label(main, textvariable=status, width=44, wraplength=320).pack(anchor="w")

    def reset_action():
        state["finished"] = False
        start_button.configure(text="Convert", state="normal" if files else "disabled")

    def update_files():
        common = [ext for ext in targets(files[0]) if all(ext in targets(f) for f in files)] if files else []
        common = [FORMAT_LABELS.get(ext, ext) for ext in common]
        formats.configure(values=common)
        if target.get() not in common:
            target.set(common[0] if common else "")
        choose_button.configure(text=f"Add Files ({len(files)})" if files else "Add Files")
        status.set(f"{len(files)} file(s) selected." if files else "Choose files to start.")
        reset_action()

    def choose():
        chosen = filedialog.askopenfilenames(title="Select files to convert", filetypes=[("All files", "*.*")])
        if not chosen:
            return
        selected, rejected = files.copy(), []
        for value in chosen:
            path = Path(value)
            if path in selected:
                continue
            if not category(path):
                rejected.append(path.name + ": unsupported format")
                continue
            if not set.intersection(*(set(targets(f)) for f in selected + [path])):
                rejected.append(path.name + ": convert in a separate batch")
                continue
            selected.append(path)
        files[:] = selected
        update_files()
        if rejected:
            messagebox.showinfo("Some files were not added", "\n".join(rejected), parent=root)

    def clear():
        if not state["busy"]:
            files.clear()
            update_files()

    def browse():
        selected = filedialog.askdirectory(title="Choose an output folder")
        if selected:
            output.set(selected)

    def open_output():
        path = Path(output.get()).expanduser()
        if path.is_dir():
            os.startfile(path)
        else:
            messagebox.showinfo("Output folder", "This folder will be created when conversion starts.", parent=root)

    def show_details():
        window = tk.Toplevel(root)
        window.title("Details")
        window.geometry("600x320")
        window.transient(root)
        log = tk.Text(window, wrap="word", font=("Segoe UI", 10))
        scrollbar = ttk.Scrollbar(window, command=log.yview)
        log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        log.pack(fill="both", expand=True)
        log.insert("end", "Output: " + output.get() + "\n\n"
                   + "\n".join(str(path) for path in files) + "\n\n" + "\n".join(details))
        log.configure(state="disabled")

    def work(batch, ext, folder):
        succeeded = failed = 0
        for index, source in enumerate(batch):
            if cancel.is_set():
                break
            events.put(("status", f"Converting {index + 1}/{len(batch)}..."))
            try:
                result = convert(source, ext, folder, cancel)
                succeeded += 1
                events.put(("log", f"OK: {source.name} -> " + ", ".join(str(path) for path in result)))
            except Cancelled:
                events.put(("log", f"Cancelled: {source.name}"))
                break
            except Exception as error:
                failed += 1
                events.put(("log", f"Failed: {source.name}\n{error}"))
        events.put(("done", succeeded, failed, cancel.is_set()))

    def start():
        if state["busy"]:
            cancel.set()
            start_button.configure(text="Cancelling...", state="disabled")
            status.set("Cancelling...")
            return
        if state["finished"]:
            open_output()
            return
        if not files or not target.get():
            messagebox.showinfo("No files selected", "Choose files and an output format first.", parent=root)
            return
        if not output.get().strip():
            messagebox.showerror("Output folder", "Choose a valid output folder.", parent=root)
            return
        cancel.clear()
        details.clear()
        state["busy"] = True
        choose_button.configure(state="disabled")
        more.configure(state="disabled")
        formats.configure(state="disabled")
        start_button.configure(text="Cancel")
        status.set("Converting...")
        threading.Thread(target=work, args=(files.copy(), next((ext for ext, label in FORMAT_LABELS.items() if label == target.get()), target.get()), output.get()), daemon=True).start()

    def poll():
        try:
            while True:
                event = events.get_nowait()
                if event[0] == "status":
                    status.set(event[1])
                elif event[0] == "log":
                    details.append(event[1])
                elif event[0] == "done":
                    state["busy"] = False
                    state["finished"] = bool(event[1]) and not event[3]
                    choose_button.configure(state="normal")
                    more.configure(state="normal")
                    formats.configure(state="readonly")
                    start_button.configure(text="Open Folder" if state["finished"] else "Convert", state="normal")
                    status.set(f"{'Cancelled' if event[3] else 'Done'}: {event[1]} converted"
                               + (f", {event[2]} failed. More > Details." if event[2] else "."))
        except queue.Empty:
            pass
        root.after(100, poll)

    def close():
        if state["busy"]:
            messagebox.showinfo("Converting", "Click Cancel and wait for the current operation to stop before closing.", parent=root)
        else:
            close_office()
            root.destroy()

    choose_button = ttk.Button(toolbar, text="Add Files", command=choose)
    choose_button.pack(side="left")
    more = ttk.Menubutton(toolbar, text="More")
    menu = tk.Menu(more, tearoff=False)
    more.configure(menu=menu)
    menu.add_command(label="Choose Output Folder...", command=browse)
    menu.add_command(label="Open Output Folder", command=open_output)
    menu.add_separator()
    menu.add_command(label="Clear Files", command=clear)
    menu.add_command(label="Details", command=show_details)
    menu.add_command(label="Help", command=lambda: os.startfile(ROOT / "README.md"))
    more.pack(side="right")
    start_button = ttk.Button(controls, text="Convert", width=12, command=start, state="disabled")
    start_button.pack(side="right")
    formats.bind("<<ComboboxSelected>>", lambda event: reset_action())
    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Any2Any local batch converter. Run without file arguments to open the GUI.")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--to", help="Output extension, for example mp4 / png / pdf")
    parser.add_argument("--out", default=str(ROOT / "output"))
    args = parser.parse_args()
    if args.files:
        if not args.to:
            parser.error("Command-line conversion requires --to")
        failures = 0
        for name in args.files:
            try:
                for result in convert(name, args.to, args.out):
                    print(result)
            except Exception as error:
                failures += 1
                print(f"Failed: {name}\n{error}")
        raise SystemExit(bool(failures))
    gui()
