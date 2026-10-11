"""PDF to editable text LaTeX or a faithful PDF-pages LaTeX wrapper."""
from pathlib import Path

INPUTS = {}
OUTPUTS = {}

def targets(path):
    return ["tex", "tex-layout"] if Path(path).suffix.lower() in (".pdf", ".xps", ".oxps", ".cbz") else []

def handles(path, ext):
    return ext in targets(path)

def escape(text):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
                    "#": r"\#", "%": r"\%", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in text if char in "\n\t" or ord(char) >= 32)

def convert(source, ext, folder, check):
    import pymupdf
    with pymupdf.open(source) as document:
        if document.needs_pass or not document.page_count:
            raise ValueError("The document is encrypted or contains no pages.")
        target = folder / f"{source.stem}.tex"
        if ext == "tex-layout":
            check()
            asset = folder / "pages.pdf"
            if document.is_pdf:
                document.save(asset, garbage=3, deflate=True)
            else:
                asset.write_bytes(document.convert_to_pdf())
            text = ("% Layout-preserving wrapper. Page content is not editable LaTeX.\n"
                    "\\documentclass{article}\n\\usepackage{pdfpages}\n\\begin{document}\n"
                    "\\includepdf[pages=-,fitpaper=true]{pages.pdf}\n\\end{document}\n")
        else:
            parts = [r"% Compile with XeLaTeX or LuaLaTeX. Text extraction does not reconstruct equations.",
                     r"\documentclass{article}", r"\usepackage[margin=20mm]{geometry}",
                     r"\usepackage{fontspec}", r"\usepackage{graphicx}",
                     r"\IfFontExistsTF{DejaVu Sans}{\setmainfont{DejaVu Sans}}{}",
                     r"\IfFileExists{xeCJK.sty}{\ifdefined\XeTeXversion\usepackage{xeCJK}",
                     r"\IfFontExistsTF{Noto Sans CJK SC}{\setCJKmainfont{Noto Sans CJK SC}}{\IfFontExistsTF{Microsoft YaHei}{\setCJKmainfont{Microsoft YaHei}}{}}\fi}{}",
                     r"\setlength{\parindent}{0pt}", r"\setlength{\parskip}{6pt}", r"\begin{document}"]
            text_count = 0
            for number, page in enumerate(document, 1):
                check()
                if number > 1:
                    parts.append(r"\clearpage")
                parts.append(f"% Source page {number}; reading order and equations require review.")
                for index, block in enumerate(page.get_text("dict", sort=True)["blocks"]):
                    check()
                    if block["type"] == 0:
                        lines = ["".join(span["text"] for span in line["spans"]) for line in block["lines"]]
                        paragraph = " ".join(line.strip() for line in lines).strip()
                        if paragraph:
                            text_count += len(paragraph)
                            parts.extend([escape(paragraph), ""])
                    elif block["type"] == 1:
                        asset = folder / f"figure_{number:04d}_{index:04d}.png"
                        pix = pymupdf.Pixmap(block["image"])
                        if pix.colorspace is None:
                            continue
                        if pix.n - pix.alpha != 3:
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                        pix.save(asset)
                        width = min(1.0, max(0.05, (block["bbox"][2] - block["bbox"][0]) / page.rect.width))
                        parts.append(r"\includegraphics[width=" + f"{width:.3f}" + r"\linewidth]{" + asset.name + "}\n")
            if not text_count:
                raise ValueError("No extractable text was found. Run OCR first, or choose tex (layout).")
            parts.append(r"\end{document}")
            text = "\n".join(parts) + "\n"
        target.write_text(text, encoding="utf-8")
        check()
