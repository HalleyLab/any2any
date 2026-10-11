"""One Office conversion using Any2Any's reusable local LibreOffice process."""
from pathlib import Path
import sys
import time
import uno

def properties(**values):
    result = []
    for name, value in values.items():
        prop = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
        prop.Name, prop.Value = name, value
        result.append(prop)
    return tuple(result)

def main(pipe, source_name, target_name):
    source, target = Path(source_name).resolve(), Path(target_name).resolve()
    context = uno.getComponentContext()
    resolver = context.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", context)
    deadline = time.monotonic() + 90
    while True:
        try:
            remote = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
            break
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError("Office engine did not become ready.")
            time.sleep(0.1)
    desktop = remote.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", remote)
    load = dict(Hidden=True, ReadOnly=True, Silent=True, MacroExecutionMode=0, UpdateDocMode=0)
    if source.suffix.lower() in (".csv", ".tsv"):
        sep = 44 if source.suffix.lower() == ".csv" else 9
        load.update(FilterName="Text - txt - csv (StarCalc)", FilterOptions=f"{sep},34,76")
    elif source.suffix.lower() == ".txt":
        load.update(FilterName="Text (encoded)", FilterOptions="UTF8")
    document = desktop.loadComponentFromURL(source.as_uri(), "_blank", 0, properties(**load))
    if document is None:
        raise RuntimeError("Office could not open the input file.")
    try:
        ext = target.suffix.lower().lstrip(".")
        filters = {
            "docx": "MS Word 2007 XML", "doc": "MS Word 97", "odt": "writer8",
            "rtf": "Rich Text Format", "txt": "Text (encoded)", "html": "HTML (StarWriter)",
            "xlsx": "Calc MS Excel 2007 XML", "xls": "MS Excel 97", "ods": "calc8",
            "csv": "Text - txt - csv (StarCalc)", "tsv": "Text - txt - csv (StarCalc)",
            "pptx": "Impress MS PowerPoint 2007 XML", "ppt": "MS PowerPoint 97", "odp": "impress8",
        }
        if ext == "pdf":
            if document.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
                filter_name = "calc_pdf_Export"
            elif document.supportsService("com.sun.star.presentation.PresentationDocument"):
                filter_name = "impress_pdf_Export"
            else:
                filter_name = "writer_pdf_Export"
        else:
            filter_name = filters[ext]
        options = dict(FilterName=filter_name, Overwrite=True)
        if ext in ("csv", "tsv"):
            options["FilterOptions"] = f"{44 if ext == 'csv' else 9},34,76"
        elif ext == "txt":
            options["FilterOptions"] = "UTF8"
        document.storeToURL(target.as_uri(), properties(**options))
        if not target.is_file() or not target.stat().st_size:
            raise RuntimeError("Office produced no output.")
    finally:
        document.close(True)

if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as error:
        print(f"Office conversion failed: {error}", file=sys.stderr)
        raise SystemExit(1)
