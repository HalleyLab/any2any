# Any2Any

Local batch file converter for Windows, with a compact English interface.

1. Open **StartAny2Any.bat**.
2. Click **Add Files**; repeat to add files from other folders.
3. Choose an output format and click **Convert**.

Results go directly into the output folder. Existing files are never overwritten.
Use **More** to change the output folder, clear files or view errors.

Supports documents, media, images, scientific data, code/notebooks, microscopy,
sequences/plasmids and electrophysiology. PDF-to-LaTeX offers editable text and
layout-preserving modes. See [formats and limitations](FORMATS.md).

## Setup

Python 3.12+ on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/)
for Office conversions. FFmpeg and Pandoc are included with the Python dependencies.
Local dependencies and converted files are excluded from Git.

Run **RunTests.bat** for conversion and interface checks.

[MIT License](LICENSE). Third-party components retain their own licenses.
