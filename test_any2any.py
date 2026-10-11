"""Run with the project Python: python -X utf8 test_any2any.py"""
import hashlib
from pathlib import Path
import tempfile
import threading
import zipfile
import any2any as a

def main():
    checks = 0
    failures = []
    with tempfile.TemporaryDirectory(prefix="any2any-tests-") as name:
        base = Path(name)
        out = base / "output"
        def check(source, ext):
            nonlocal checks
            try:
                products = a.convert(source, ext, out)
                assert all(file.parent == out for file in products)
                assert all(file.is_file() for file in out.iterdir())
                assert products and all(p.stat().st_size for p in products)
                if ext in ("docx", "xlsx", "pptx", "odt", "ods", "odp", "epub"):
                    assert zipfile.is_zipfile(products[0])
                    with zipfile.ZipFile(products[0]) as archive:
                        assert archive.testzip() is None
                checks += 1
                print(f"PASS {source.suffix} -> {ext}", flush=True)
                return products[0]
            except Exception as error:
                failures.append(f"{source.name} -> {ext}: {error}")
                print("FAIL " + failures[-1], flush=True)
                return None

        image = base / "café space[1]! & photo.png"
        a.Image.new("RGBA", (64, 48), (250, 30, 40, 0)).save(image)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        for ext in a.OUTPUTS["Images"].split():
            check(image, ext)
        jpg = check(image, "jpg")
        with a.Image.open(jpg) as im:
            assert min(im.getpixel((5, 5))) > 245
        assert digest == hashlib.sha256(image.read_bytes()).hexdigest()
        assert sum(p.name.startswith(image.stem) and p.suffix == ".jpg" for p in out.iterdir()) == 2

        animated = base / "animation.gif"
        frames = [a.Image.new("RGB", (24, 24), color) for color in ("red", "blue")]
        frames[0].save(animated, save_all=True, append_images=frames[1:], duration=[100, 200], loop=0)
        for ext in ("gif", "webp", "png", "tiff", "avif", "pdf", "jpg"):
            result = check(animated, ext)
            if result and ext == "jpg":
                assert len(list(result.parent.glob("animation_*.jpg"))) == 2
            if result and ext == "pdf":
                with a.pymupdf.open(result) as doc:
                    assert len(doc) == 2

        svg = base / "vector.svg"
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60"><rect width="80" height="60" fill="red"/></svg>', encoding="utf-8")
        check(svg, "png")
        check(svg, "pdf")

        video = base / "sample.LRV"
        a.run_command([a.imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi",
                       "-i", "color=c=blue:s=64x48:r=25", "-f", "lavfi", "-i", "sine=frequency=440",
                       "-t", "0.4", "-c:v", "libx264", "-c:a", "aac", "-f", "mp4", video])
        for ext in a.VIDEO:
            check(video, ext)
        wav = check(video, "wav")
        for ext in a.AUDIO:
            check(wav, ext)

        subtitle = base / "subtitle.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello world\n", encoding="utf-8")
        for ext in a.OUTPUTS["Subtitles"].split():
            check(subtitle, ext)

        md = base / "document.md"
        fixture = base / "picture.png"
        a.Image.new("RGB", (50, 50), "red").save(fixture)
        md.write_text("# Test document\n\nHello Unicode conversion.\n\n![picture](picture.png)\n", encoding="utf-8")
        docx = check(md, "docx")
        for ext in a.OUTPUTS["Documents"].split():
            result = check(docx, ext)
            if result and ext == "md":
                assert list(result.parent.glob("document_asset_*.png"))
                assert "assets/" not in result.read_text(encoding="utf-8")
            if result and ext == "pdf":
                with a.pymupdf.open(result) as doc:
                    assert doc.page_count >= 1
        check(md, "pdf")
        repeated = a.convert(docx, "md", out)[0]
        import re
        from urllib.parse import unquote
        for reference in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", repeated.read_text(encoding="utf-8")):
            asset = out / unquote(reference)
            assert asset.is_file() and asset.parent == out
        assert not any(file.is_dir() for file in out.iterdir())
        txt = base / "plain.txt"
        txt.write_text("Plain Unicode text.\n", encoding="utf-8")
        check(txt, "epub")

        csv = base / "table.csv"
        csv.write_text('name,value\n"Unicode,item",00123\nsecond,5\n', encoding="utf-8-sig")
        xlsx = check(csv, "xlsx")
        for ext in a.OUTPUTS["Spreadsheets"].split():
            check(xlsx, ext)
        tsv = base / "table.tsv"
        tsv.write_text("name\tvalue\nUnicode\t5\n", encoding="utf-8")
        check(tsv, "xlsx")

        slides = base / "slides.fodp"
        slides.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
 office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.presentation">
 <office:body><office:presentation>
 <draw:page draw:name="Slide 1"><draw:frame svg:x="1cm" svg:y="1cm" svg:width="12cm" svg:height="3cm"><draw:text-box><text:p>Hello</text:p></draw:text-box></draw:frame></draw:page>
 <draw:page draw:name="Slide 2"><draw:frame svg:x="1cm" svg:y="1cm" svg:width="12cm" svg:height="3cm"><draw:text-box><text:p>Second</text:p></draw:text-box></draw:frame></draw:page>
 </office:presentation></office:body></office:document>''', encoding="utf-8")
        pptx = check(slides, "pptx")
        for ext in a.OUTPUTS["Presentations"].split():
            result = check(pptx, ext)
            if result and ext == "pdf":
                with a.pymupdf.open(result) as doc:
                    assert doc.page_count == 2

        pdf = base / "pages.pdf"
        with a.pymupdf.open() as doc:
            for text in ("page 1", "page 2"):
                doc.new_page().insert_text((72, 72), text)
            doc.save(pdf)
        for ext in a.OUTPUTS["PDF/Pages"].split():
            result = check(pdf, ext)
            if result and ext not in ("pdf", "txt"):
                assert len(list(result.parent.glob(f"pages_*.{ext}"))) == 2

        before_publish = set(out.iterdir())
        cancel_publish = threading.Event()
        original_replace = a.os.replace
        def cancel_after_one(source, destination):
            original_replace(source, destination)
            cancel_publish.set()
        try:
            a.os.replace = cancel_after_one
            try:
                a.convert(pdf, "png", out, cancel_publish)
                raise AssertionError("Publication cancellation ignored")
            except a.Cancelled:
                pass
        finally:
            a.os.replace = original_replace
        assert set(out.iterdir()) == before_publish

        broken = base / "broken.png"
        broken.write_bytes(b"not an image")
        before = set(out.iterdir())
        try:
            a.convert(broken, "jpg", out)
            raise AssertionError("Corrupt file accepted")
        except a.Image.UnidentifiedImageError:
            pass
        assert set(out.iterdir()) == before
        cancel = threading.Event()
        cancel.set()
        try:
            a.convert(image, "png", out, cancel)
            raise AssertionError("Cancellation ignored")
        except a.Cancelled:
            pass
        try:
            a.convert(image, "../bad", out)
            raise AssertionError("Invalid target accepted")
        except ValueError:
            pass
        assert hashlib.sha256(image.read_bytes()).hexdigest() == digest
        print("PASS originals, collisions, frame/page counts, corrupt-file cleanup, cancellation and target validation.", flush=True)
    if failures:
        raise AssertionError("\n".join(failures))
    print(f"SUCCESS: {checks} actual conversions plus safety checks.", flush=True)


def office_cancel():
    a.close_office()
    with tempfile.TemporaryDirectory(prefix="any2any-office-test-") as name:
        base = Path(name)
        draft = base / "restart.md"
        draft.write_text("# Office restart check\n", encoding="utf-8")
        source = a.convert(draft, "docx", base / "input")[0]
        output = base / "output"
        cancel = threading.Event()
        timer = threading.Timer(1, cancel.set)
        timer.start()
        try:
            try:
                a.convert(source, "pdf", output, cancel)
                raise AssertionError("Office cancellation ignored")
            except a.Cancelled:
                pass
        finally:
            timer.cancel()
            timer.join()
        assert a._office is None and not list(output.iterdir())
        result = a.convert(source, "pdf", output)[0]
        with a.pymupdf.open(result) as document:
            assert "Office restart check" in document[0].get_text()
        print("PASS real Office cancellation, output cleanup and engine restart.", flush=True)


def smoke():
    import tkinter as tk
    import traceback
    from tkinter import ttk, filedialog
    from PIL import ImageGrab

    with tempfile.TemporaryDirectory(prefix="any2any-ui-") as name:
        base = Path(name)
        samples = [base / "one" / "sample.png", base / "two" / "sample.png"]
        for sample in samples:
            sample.parent.mkdir()
            a.Image.new("RGB", (32, 32), "blue").save(sample)
        broken = base / "broken.png"
        broken.write_bytes(b"not an image")
        chosen = [str(samples[0])]
        original_tk = tk.Tk
        original_files, original_directory = filedialog.askopenfilenames, filedialog.askdirectory
        original_open, original_convert = a.os.startfile, a.convert
        errors, completed, opened = [], [], []
        root = None

        def widgets(parent):
            result = []
            for child in parent.winfo_children():
                result.append(child)
                result.extend(widgets(child))
            return result

        def details_text(menu):
            menu.invoke("Details")
            root.update()
            window = next(item for item in root.winfo_children() if isinstance(item, tk.Toplevel))
            log = next(item for item in widgets(window) if isinstance(item, tk.Text))
            text = log.get("1.0", "end")
            assert log.cget("state") == "disabled"
            window.destroy()
            return text

        def exercise():
            try:
                items = widgets(root)
                assert not any(isinstance(item, (ttk.Treeview, tk.Text)) or type(item) is ttk.Entry for item in items)
                buttons = {item.cget("text"): item for item in items if isinstance(item, ttk.Button)}
                assert set(buttons) == {"Add Files", "Convert"}
                choose, action = buttons["Add Files"], buttons["Convert"]
                assert action.instate(["disabled"])
                more = next(item for item in items if isinstance(item, ttk.Menubutton))
                menu = root.nametowidget(str(more.cget("menu")))
                combo = next(item for item in items if isinstance(item, ttk.Combobox))
                choose.invoke()
                assert choose.cget("text") == "Add Files (1)"
                chosen[:] = [str(samples[1]), str(samples[0])]
                choose.invoke()
                assert choose.cget("text") == "Add Files (2)"
                assert "jpg" in combo.cget("values")
                menu.invoke("Clear Files")
                assert choose.cget("text") == "Add Files" and action.instate(["disabled"])
                choose.invoke()
                chosen.clear()
                choose.invoke()
                assert choose.cget("text") == "Add Files (2)"
                menu.invoke("Choose Output Folder...")
                combo.set("jpg")
                action.invoke()
                assert action.cget("text") == "Cancel"
                assert more.instate(["disabled"]) and choose.instate(["disabled"])

                def finish():
                    try:
                        if action.cget("text") != "Open Folder":
                            root.after(100, finish)
                            return
                        assert len(list((base / "output").glob("*.jpg"))) == 2
                        log = details_text(menu)
                        assert all(str(sample) in log for sample in samples) and "OK:" in log
                        assert all(file.is_file() for file in (base / "output").iterdir())
                        assert not any(isinstance(item, tk.Toplevel) for item in root.winfo_children())
                        action.invoke()
                        assert opened[-1] == base / "output"
                        root.update()
                        assert root.winfo_width() <= 420 and root.winfo_height() <= 200
                        for widget in widgets(root):
                            if widget.winfo_ismapped():
                                assert widget.winfo_height() > 1
                                assert widget.winfo_rootx() + widget.winfo_width() <= root.winfo_rootx() + root.winfo_width()
                                assert widget.winfo_rooty() + widget.winfo_height() <= root.winfo_rooty() + root.winfo_height()
                        ImageGrab.grab(window=root.winfo_id()).save(a.ROOT / "ui-preview.png")
                        combo.set("webp")
                        combo.event_generate("<<ComboboxSelected>>")
                        assert action.cget("text") == "Convert"
                        menu.invoke("Clear Files")
                        chosen[:] = [str(broken)]
                        choose.invoke()
                        combo.set("jpg")
                        action.invoke()
                        root.after(200, failed)
                    except Exception:
                        errors.append(traceback.format_exc())
                        root.destroy()

                def failed():
                    try:
                        if action.cget("text") == "Cancel":
                            root.after(100, failed)
                            return
                        assert action.cget("text") == "Convert"
                        assert "Failed: broken.png" in details_text(menu)
                        assert not list((base / "output").glob("broken*.jpg"))
                        menu.invoke("Clear Files")
                        chosen[:] = [str(samples[0])]
                        choose.invoke()
                        def wait_until_cancelled(source, ext, output, cancel):
                            cancel.wait(5)
                            raise a.Cancelled("Cancelled")
                        a.convert = wait_until_cancelled
                        action.invoke()
                        assert action.cget("text") == "Cancel"
                        action.invoke()
                        assert action.cget("text") == "Cancelling..." and action.instate(["disabled"])
                        root.after(200, cancelled)
                    except Exception:
                        errors.append(traceback.format_exc())
                        root.destroy()

                def cancelled():
                    try:
                        if action.cget("text") != "Convert":
                            root.after(100, cancelled)
                            return
                        assert not action.instate(["disabled"])
                        assert not more.instate(["disabled"]) and not choose.instate(["disabled"])
                        assert "Cancelled:" in details_text(menu)
                        completed.append(True)
                    except Exception:
                        errors.append(traceback.format_exc())
                    root.destroy()
                root.after(200, finish)
            except Exception:
                errors.append(traceback.format_exc())
                root.destroy()

        def factory():
            nonlocal root
            root = original_tk()
            root.after(200, exercise)
            def timeout():
                errors.append("GUI timed out")
                root.destroy()
            root.after(15000, timeout)
            return root

        try:
            tk.Tk = factory
            filedialog.askopenfilenames = lambda **kwargs: tuple(chosen)
            filedialog.askdirectory = lambda **kwargs: str(base / "output")
            a.os.startfile = lambda path: opened.append(Path(path))
            a.gui()
        finally:
            tk.Tk = original_tk
            filedialog.askopenfilenames, filedialog.askdirectory = original_files, original_directory
            a.os.startfile, a.convert = original_open, original_convert
        assert not errors, errors
        assert completed
    print("PASS multi-folder selection, deduplication, flat same-name output, tiny GUI, errors and cancellation.", flush=True)

if __name__ == "__main__":
    try:
        main()
        office_cancel()
        smoke()
    finally:
        a.close_office()
