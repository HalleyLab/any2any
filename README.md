# Any2Any

Formats converter for Windows. [Open the web app](https://halleylab.github.io/any2any/).

1. Run **StartAny2Any.bat** to start the local engine and desktop interface.
2. **Add files** from one or more folders, choose a format, then **Convert**.
3. When conversion completes, click **Download** and choose where to save.

The desktop and Pages interfaces use the same local engine. Files stay on your
computer. Use Edge or Chrome; allow local-network access when prompted.
Multiple outputs download as a flat ZIP, including metadata and preservation files.
Keep these files together. Add companions in the same selection; click a file's
format badge to mark it as a companion.
Same-name inputs with different suffixes become `sample_png.jpg`, `sample_tiff.jpg`;
remaining collisions get numbers. Existing files are never overwritten by the engine.
Use **···** to clear the selection or quit the engine. Closing the window keeps the
engine available; inactive batches expire after one hour.

## Supported formats

Common inputs and outputs are listed below. Available conversions depend on the
input format and content. See [all formats and limits](FORMATS.md) and
[fidelity checks](FIDELITY.md).

| Category | Common inputs | Common outputs |
| --- | --- | --- |
| Video | MP4, MKV, MOV, AVI, WebM, MTS/M2TS, MXF, LRV | MP4, MKV, MOV, WebM, AVI, TS; audio; PNG/JPG/TIFF frames |
| Audio | MP3, WAV, FLAC, AAC, M4A, OGG, Opus, AIFF, WMA, APE | MP3, WAV, FLAC, AAC, M4A, OGG, Opus, AIFF, WMA, AC3, AU |
| Images | PNG, JPG, WebP, BMP, TIFF, GIF, HEIC/HEIF, AVIF, PSD, SVG | PNG, JPG, WebP, BMP, TIFF, GIF, ICO, AVIF, HEIC, PDF |
| Documents / ebooks | DOC/DOCX, ODT, RTF, TXT, Markdown, HTML, LaTeX, EPUB | DOC/DOCX, ODT, RTF, PDF, TXT, Markdown, HTML, LaTeX, EPUB |
| PDF / pages | PDF, XPS/OXPS, CBZ | PNG, JPG, WebP, TIFF, SVG, TXT, PDF, LaTeX (text/layout) |
| Spreadsheets | XLS/XLSX/XLSM/XLSB, ODS, CSV, TSV | XLS/XLSX, ODS, CSV, TSV, PDF; research data formats |
| Presentations | PPT/PPTX, PPS/PPSX, ODP | PPT/PPTX, ODP, PDF |
| Subtitles | SRT, VTT, ASS, SSA | SRT, VTT, ASS, SSA |
| Scientific arrays | MAT, NPY/NPZ, HDF5, NetCDF | MAT, NPY/NPZ, HDF5, NetCDF; compatible data tables |
| Research tables | CSV/TSV, Excel, Parquet, Feather, SQLite, SAV, DTA, XPT/SAS7BDAT, RDS/RData, PZFX | CSV/TSV, XLSX, JSON/JSONL, Parquet, Feather, SAV/ZSAV/POR, DTA, XPT, RDS/RData, SQLite |
| Chemistry | MOL/SDF, SMILES, MOL2, PDB, XYZ, CIF; Gaussian/GAMESS/NWChem output | MOL/SDF, SMILES, MOL2, PDB/PDBQT, XYZ, CIF, GRO; calculation inputs |
| Sequences / plasmids | FASTA/FASTQ (+ gzip), GenBank/EMBL, SnapGene DNA, XDNA, AB1, SFF, alignments | FASTA/FASTQ, GenBank/EMBL, XDNA, alignments; SVG/PNG/PDF maps |
| 3D meshes | STL, PLY, OBJ, OFF, GLB/GLTF, 3MF, DAE | STL, PLY, OBJ, OFF, GLB |
| Code / notebooks | Python, R, Julia, MATLAB, C/C++, JS/TS and other scripts; IPYNB, Rmd, QMD | IPYNB, same-language scripts, Markdown/Rmd/QMD, HTML, PDF, TXT |
| Structured text | JSON, YAML/YML, TOML, XML | JSON, YAML/YML, TOML, XML |
| Camera RAW | Canon CR2/CR3, Nikon NEF, Sony ARW, Fujifilm RAF, DNG and other LibRaw formats | TIFF, PNG, JPG, WebP, BMP, NPY, NPZ, HDF5 |
| Microscopy | CZI/LSM, ND2, LIF, IMS, OME-TIFF, MRC, SVS/NDPI | TIFF, PNG, JPG, WebP, BMP, NPY, NPZ, HDF5 |
| Electrophysiology / EEG / LFP | ABF, SMR, RHD/RHS, PLX, NEX, NS1-NS6/NEV, NWB, EDF/BDF, FIF, VHDR, SET | HDF5, NPZ, MAT, CSV, TSV; EDF/BDF/FIF for compatible EEG inputs |
| Genomic records | SAM/BAM, VCF, GFF/GFF3, GTF, BED, BedGraph | CSV, TSV, JSONL; SAM/BAM also export SAM and primary-read FASTA/FASTQ |
| Nanopore signals | FAST5, POD5 | HDF5, NPZ, CSV |
| Flow cytometry | FCS | HDF5, NPZ, MAT, CSV, TSV |

PDF-to-LaTeX supports editable text or preserved page layout. Code exports keep
the original programming language. FASTQ output requires stored quality scores.

## Setup

Python 3.12+ on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/)
for Office conversions. FFmpeg and Pandoc are included with the Python dependencies.
Local dependencies and converted files are excluded from Git.

Run **RunTests.bat** for conversion and local API checks. Optional browser checks:
`node test_web_ui.cjs` (Playwright installed, local engine running).

[MIT License](LICENSE). Third-party components retain their own licenses.
