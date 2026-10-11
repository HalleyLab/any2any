# Any2Any Local Batch Converter

Double-click **StartAny2Any.bat**, click **Add Files**, select a format, and click **Convert**.
The small window has no file list or path input. Add Files appends files from any folder. Select again to add another folder; duplicates are ignored. More > Clear Files empties the batch.
The Convert button becomes Cancel while running and Open Folder after success. Selecting another format enables Convert again.
Results default to the project's output folder (E:\projects\any2any\output on the original PC). Use **More > Choose Output Folder...** to change this.
**More > Details** opens selected filenames, the output path, and conversion results in a separate window.
The original local setup includes the conversion components. Git clones exclude .venv, tools and output; follow the setup below on another PC.

## Setup from GitHub

Windows with Python 3.12 or newer is required. In the cloned project folder, run:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

Install [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) for Word, spreadsheet and presentation conversions. The app detects its standard Windows installation folder. FFmpeg and Pandoc are included through the Python packages above.

Double-click StartAny2Any.bat to launch. The app runs locally. The repository contains source code and tests, without the local virtual environment, large converter binaries or converted user files.

## Supported formats

These are supported input extensions, not a guarantee that every codec, encrypted file, or file variant can be converted.
The format selector shows only outputs supported by every file in the current batch. Convert incompatible categories in separate batches.

| Category | Common inputs | Outputs |
| --- | --- | --- |
| Video | MP4, MKV, MOV, AVI, WebM, FLV, WMV, TS, MTS, M2TS, MPG, VOB, 3GP, MXF, LRV, RM/RMVB, and others | MP4, MKV, MOV, WebM, AVI, TS, FLV, MPG, OGV, 3GP, plus the audio formats below |
| Audio | MP3, WAV, FLAC, AAC, M4A, OGG, Opus, AIFF, WMA, AC3, AMR, AU, CAF, APE, and others | MP3, WAV, FLAC, M4A, AAC, OGG, Opus, AIFF, WMA, AC3, AU |
| Images | PNG, JPG, WebP, BMP, TIFF, GIF, ICO, AVIF, HEIC/HEIF, TGA, PSD, DDS, PNM, PCX, JP2, QOI, ICNS, SVG, and others | PNG, JPG, WebP, BMP, TIFF, GIF, ICO, AVIF, HEIC, PPM, TGA, JP2, PDF |
| Documents / ebooks | DOC, DOCX, ODT, RTF, TXT, Markdown, HTML, RST, LaTeX, EPUB, FB2, Org | DOCX, DOC, ODT, RTF, PDF, TXT, Markdown, HTML, EPUB, RST, LaTeX, Org |
| Spreadsheets | XLS, XLSX, XLSM, XLSB, ODS, CSV, TSV, FODS | XLSX, XLS, ODS, CSV, TSV, PDF |
| Presentations | PPT, PPTX, PPS, PPSX, ODP, FODP | PPTX, PPT, ODP, PDF |
| PDF / pages | PDF, XPS, OXPS, CBZ | PNG, JPG, WebP, TIFF, SVG per page; extracted TXT; PDF |
| Subtitles | SRT, VTT, ASS, SSA | SRT, VTT, ASS, SSA |

See INPUTS and OUTPUTS in any2any.py for the complete extension lists.

## Output and fidelity

- Files are decoded and encoded, or converted through Office/Pandoc. This is not extension renaming.
- Originals are preserved. Converted files go directly into the output folder. Duplicate filenames receive a numeric suffix; existing files are never overwritten.
- Conversion uses a temporary folder outside the output folder. Validated results are then published as files. Failure or cancellation rolls back the current conversion. Details shows the errors.
- JPG, BMP, PPM and image-to-PDF outputs use white backgrounds for transparency. ICO images are limited to 256 by 256 pixels.
- Animated GIF, WebP, PNG/APNG and AVIF outputs retain frames. TIFF/PDF outputs retain pages. Static image outputs such as JPG export each frame separately.
- PDF images are rendered at 150 DPI, one file per page. PDF-to-TXT extracts existing text without OCR. Export scanned pages as images. Editable PDF-to-Word is not provided.
- Media output uses the first video and audio tracks and stereo audio. Extra tracks, embedded subtitles, chapters and attachments are not copied. MP4 uses H.264/AAC; odd image dimensions are padded to even dimensions.
- Compression may be lossy. Document layout, fonts, formulas, animation and special features can change. PSD and similar images are flattened without retaining editable layers.
- CSV/TSV export only the first sheet and cannot retain workbook layout, formulas or multiple sheets. Plain text and subtitle formats cannot retain all styling.
- Office macros are not executed, and macro-enabled output formats are not offered. Encrypted, damaged, DRM-protected or unsupported files produce errors.
- Assets for HTML/Markdown/LaTeX are also written as files in the output folder. Links are updated to match their final names. Keep those asset files with the document. Referenced external resources may require network access.
- Basic output checks reopen images, check PDF page counts and Office ZIP structure, and decode the first second of media. These checks do not verify every frame of a long file or exact document layout.

## Performance

See benchmark-before.json and benchmark-after.json for timings from generated small DOCX-to-PDF samples on this PC. These compare Any2Any versions, not other applications. Results depend on document size, fonts, images and disk speed.

## Command line

Open a terminal in this directory:

~~~powershell
.\.venv\Scripts\python.exe -X utf8 .\any2any.py "I:\videos\clip.LRV" --to mp4
.\.venv\Scripts\python.exe -X utf8 .\any2any.py "E:\a.heic" "E:\b.png" --to jpg --out "E:\converted"
~~~

Run without file arguments to open the English GUI. Unsupported conversions and failures return a nonzero command-line exit code.

## Tests and maintenance

Double-click **RunTests.bat**. Tests use generated temporary samples and do not modify your source files.
They cover conversion categories, Unicode and special filenames, transparency, frames/pages, duplicate names, original-file preservation, corrupt files, cancellation and basic GUI operations.
Office starts once and is reused for subsequent conversions until the app closes. The first Office conversion still pays startup and font initialization costs. Later documents avoid those costs. Without the bundled Office Python runtime, the app falls back to command-line conversion. PDF-to-image uses faster lossless PNG compression; outputs can be larger.

Dependencies are isolated in .venv. To rebuild the Python environment:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

LibreOffice 26.2.6 was extracted from its official MSI after SHA-256 verification into tools\libreoffice without registering system file associations.
The app uses this copy first and can also find LibreOffice in standard system installation directories.
If tools\libreoffice is removed, install LibreOffice from its official website to restore Office conversions.
This project requires the local Python runtime; it is not a standalone EXE for computers without Python.

## Components and official documentation

- [FFmpeg](https://ffmpeg.org/ffmpeg.html): video, audio and subtitles.
- [Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) / [pillow-heif](https://pillow-heif.readthedocs.io/): images.
- [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-images.html): PDF, SVG and page rendering.
- [Pandoc](https://pandoc.org/MANUAL.html): markup documents and ebooks.
- [LibreOffice](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html): Office documents, spreadsheets and presentations.

The reusable Office engine uses LibreOffice's [document-loading API](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1frame_1_1XComponentLoader.html). Macro execution and automatic document-link updates are disabled.
