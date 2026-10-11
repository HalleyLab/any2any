"""Notebook, source-code export and structured text. Input code is never executed."""
from pathlib import Path
from functools import lru_cache
import base64
import html
import json
import shutil
import tomllib
import textwrap

LANGUAGES = {
    "py": "python", "pyw": "python", "r": "r", "jl": "julia", "m": "matlab", "sh": "bash", "ps1": "powershell",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript", "jsx": "javascript", "ts": "typescript", "tsx": "typescript", "cpp": "c++", "cc": "c++", "cxx": "c++", "c": "c", "h": "c", "hpp": "c++",
    "cs": "csharp", "java": "java", "go": "go", "rs": "rust", "lua": "lua", "rb": "ruby",
    "php": "php", "swift": "swift", "kt": "kotlin", "sql": "sql", "f90": "fortran", "f": "fortran",
    "groovy": "groovy", "scala": "scala", "fs": "fsharp", "fsx": "fsharp", "hs": "haskell",
    "clj": "clojure", "scm": "scheme", "ss": "scheme", "wolfram": "wolfram language",
    "sage": "sage", "sas": "sas", "do": "stata", "tcl": "tcl", "gp": "gnuplot", "pro": "idl",
    "robot": "robotframework", "resource": "robotframework", "sos": "sos", "xsh": "xonsh",
    "coco": "coconut", "lgt": "logtalk", "logtalk": "logtalk",
}
NOTEBOOKS = "ipynb rmd qmd".split()
STRUCTURED = "json yaml yml toml xml".split()
INPUTS = {"Code and notebooks": " ".join(LANGUAGES) + " " + " ".join(NOTEBOOKS),
          "Structured text": " ".join(STRUCTURED)}
OUTPUTS = {"Code and notebooks": " ".join(LANGUAGES) + " ipynb md rmd qmd html pdf txt",
           "Structured text": " ".join(STRUCTURED)}

def notebook_language(notebook):
    metadata = notebook.get("metadata", {})
    language = metadata.get("language_info", {}).get("name") or metadata.get("jupytext", {}).get("main_language") or metadata.get("kernelspec", {}).get("language", "")
    return {"python3": "python", "c#": "csharp", "c++17": "c++", "c++14": "c++", "c++11": "c++", "octave": "matlab"}.get(language.lower(), language.lower())


@lru_cache(maxsize=128)
def script_target(path, modified, size):
    notebook = json.loads(path.read_text(encoding="utf-8-sig")) if path.suffix.lower() == ".ipynb" else read_notebook(path)
    language = notebook_language(notebook)
    original = notebook.get("metadata", {}).get("any2any_source_extension")
    if original and LANGUAGES.get(original) == language:
        return original
    return next((key for key, value in LANGUAGES.items() if value == language), None)


def targets(path):
    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    if ext in STRUCTURED:
        return STRUCTURED
    if ext in LANGUAGES:
        return list(dict.fromkeys([ext, "ipynb", "md", "rmd", "qmd", "html", "pdf", "txt"]))
    if ext in NOTEBOOKS:
        result = ["ipynb", "md", "rmd", "qmd", "html", "pdf", "txt"]
        try:
            stat = path.stat()
            preferred = script_target(path, stat.st_mtime_ns, stat.st_size)
            if preferred:
                result.insert(0, preferred)
        except (ValueError, OSError, KeyError, TypeError, AttributeError):
            pass
        return result
    if ext in ("md", "markdown"):
        return ["ipynb", "rmd", "qmd"]
    return []

def handles(path, ext):
    return ext in targets(path)

def read_notebook(source):
    import jupytext
    import nbformat
    from jupytext.languages import _SCRIPT_EXTENSIONS
    ext = source.suffix.lower().lstrip(".")
    if ext == "ipynb":
        notebook = nbformat.read(source, as_version=4)
    elif ext in LANGUAGES:
        if "." + ext in _SCRIPT_EXTENSIONS:
            notebook = jupytext.reads(source.read_text(encoding="utf-8-sig"), fmt=("R" if ext == "r" else ext) + ":percent")
        else:
            notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source.read_text(encoding="utf-8-sig"))])
        notebook.metadata["language_info"] = {"name": LANGUAGES[ext]}
        notebook.metadata["any2any_source_extension"] = ext
    else:
        notebook = jupytext.reads(source.read_text(encoding="utf-8-sig"), fmt="md" if ext in ("md", "markdown") else ("Rmd" if ext in ("rmd", "qmd") else ext))
    nbformat.validate(notebook)
    return notebook

def render_notebook(notebook, title, wrap=False):
    from markdown_it import MarkdownIt
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.lexers.special import TextLexer
    from pygments.util import ClassNotFound
    markdown = MarkdownIt("commonmark", {"html": False})
    try:
        lexer = get_lexer_by_name(notebook_language(notebook))
    except ClassNotFound:
        lexer = TextLexer()
    formatter = HtmlFormatter(noclasses=True, nowrap=True)
    parts = [f"<h1>{html.escape(title)}</h1>"]
    for cell in notebook.cells:
        if cell.cell_type == "markdown":
            parts.append(markdown.render(cell.source))
        else:
            source = cell.source
            if wrap:
                source = "\n".join(
                    "\n".join(textwrap.wrap(line.expandtabs(4), width=80, replace_whitespace=False,
                                            drop_whitespace=False, break_on_hyphens=False))
                    for line in source.split("\n")
                )
            parts.append("<pre>" + (highlight(source, lexer, formatter) if cell.cell_type == "code" else html.escape(source)) + "</pre>")
        for output in cell.get("outputs", []):
            text = output.get("text") or output.get("data", {}).get("text/plain")
            if text:
                parts.append("<pre>" + html.escape("".join(text) if isinstance(text, list) else text) + "</pre>")
            picture = output.get("data", {}).get("image/png")
            if picture:
                picture = "".join(picture) if isinstance(picture, list) else picture
                base64.b64decode(picture, validate=True)
                parts.append('<img src="data:image/png;base64,' + picture + '">')
    css = "body{font-family:sans-serif;font-size:10pt;margin:24px}pre{font-family:monospace;font-size:8pt;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f4;padding:8px}img{max-width:100%}"
    return "<!doctype html><html><head><meta charset=\"utf-8\"><title>" + html.escape(title) + "</title><style>" + css + "</style></head><body>" + "".join(parts) + "</body></html>"

def structured(source, ext, target):
    import yaml
    import xmltodict
    import tomli_w
    src = source.suffix.lower().lstrip(".")
    text = source.read_text(encoding="utf-8-sig")
    if src == "json":
        data = json.loads(text)
    elif src in ("yaml", "yml"):
        data = yaml.safe_load(text)
    elif src == "toml":
        data = tomllib.loads(text)
    else:
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("XML with DTDs or entities is not supported.")
        data = xmltodict.parse(text, disable_entities=True)
    if ext == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        json.loads(content)
    elif ext in ("yaml", "yml"):
        content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        yaml.safe_load(content)
    elif ext == "toml":
        if not isinstance(data, dict):
            raise ValueError("TOML needs a top-level object and cannot represent null values.")
        content = tomli_w.dumps(data)
        tomllib.loads(content)
    else:
        if not isinstance(data, dict) or len(data) != 1:
            raise ValueError("XML export needs exactly one root key, for example {\"root\": {...}}.")
        content = xmltodict.unparse(data, pretty=True)
        xmltodict.parse(content, disable_entities=True)
    target.write_text(content, encoding="utf-8")

def convert(source, ext, folder, check):
    import jupytext
    import nbformat
    from jupytext.languages import _SCRIPT_EXTENSIONS
    src = source.suffix.lower().lstrip(".")
    target = folder / f"{source.stem}.{ext}"
    check()
    preserved = None
    if src in STRUCTURED:
        structured(source, ext, target)
        preserved = folder / ("preserved_source." + src)
        while preserved.exists():
            preserved = preserved.with_stem(preserved.stem + "_original")
        shutil.copyfile(source, preserved)
    elif src in LANGUAGES and ext in (src, "txt"):
        shutil.copyfile(source, target)
    else:
        notebook = read_notebook(source)
        if src in NOTEBOOKS and ext != "ipynb":
            nbformat.write(notebook, folder / "preserved_notebook.ipynb")
        if ext in LANGUAGES and LANGUAGES[ext] != notebook_language(notebook):
            raise ValueError("Notebook-to-script export must keep the original programming language.")
        if ext == "ipynb":
            nbformat.write(notebook, target)
            nbformat.validate(nbformat.read(target, as_version=4))
        elif ext in ("html", "pdf"):
            content = render_notebook(notebook, source.name, wrap=ext == "pdf")
            if ext == "html":
                target.write_text(content, encoding="utf-8")
            else:
                import pymupdf
                media = pymupdf.Rect(0, 0, 595, 842)
                area = media + (32, 32, -32, -32)
                with pymupdf.DocumentWriter(str(target)) as writer:
                    pymupdf.Story(html=content).write(writer, lambda number, filled: (media, area, None))
        elif ext == "txt":
            target.write_text("\n\n".join(cell.source for cell in notebook.cells), encoding="utf-8")
        elif ext in LANGUAGES and "." + ext not in _SCRIPT_EXTENSIONS:
            target.write_text("\n\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code") + "\n", encoding="utf-8")
        else:
            # shortcut: QMD uses common R Markdown cells; use Quarto for its execution/rendering options.
            fmt = ("R" if ext == "r" else ext) + ":percent" if ext in LANGUAGES else ("Rmd" if ext in ("rmd", "qmd") else ext)
            target.write_text(jupytext.writes(notebook, fmt=fmt), encoding="utf-8")
    check()
    return preserved
