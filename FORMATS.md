# Format reference

## Supported formats

These are supported input extensions, not a guarantee that every codec, encrypted file, or file variant can be converted.
The format selector shows only outputs supported by every file in the current batch. Convert incompatible categories in separate batches.

| Category | Common inputs | Outputs |
| --- | --- | --- |
| Video | MP4, MKV, MOV, AVI, WebM, FLV, WMV, TS, MTS, M2TS, MPG, VOB, 3GP, MXF, LRV, RM/RMVB, and others | MP4, MKV, MOV, WebM, AVI, TS, FLV, MPG, OGV, 3GP, audio, plus PNG/JPG/TIFF video frames |
| Audio | MP3, WAV, FLAC, AAC, M4A, OGG, Opus, AIFF, WMA, AC3, AMR, AU, CAF, APE, and others | MP3, WAV, FLAC, M4A, AAC, OGG, Opus, AIFF, WMA, AC3, AU |
| Images | PNG, JPG, WebP, BMP, TIFF, GIF, ICO, AVIF, HEIC/HEIF, TGA, PSD, DDS, PNM, PCX, JP2, QOI, ICNS, SVG, and others | PNG, JPG, WebP, BMP, TIFF, GIF, ICO, AVIF, HEIC, PPM, TGA, JP2, PDF |
| Documents / ebooks | DOC, DOCX, ODT, RTF, TXT, Markdown, HTML, RST, LaTeX, EPUB, FB2, Org | DOCX, DOC, ODT, RTF, PDF, TXT, Markdown, HTML, EPUB, RST, LaTeX, Org |
| Spreadsheets | XLS, XLSX, XLSM, XLSB, ODS, CSV, TSV, FODS | XLSX, XLS, ODS, CSV, TSV, PDF |
| Presentations | PPT, PPTX, PPS, PPSX, ODP, FODP | PPTX, PPT, ODP, PDF |
| PDF / pages | PDF, XPS, OXPS, CBZ | PNG, JPG, WebP, TIFF, SVG per page; TXT; PDF; LaTeX text/layout modes |
| Subtitles | SRT, VTT, ASS, SSA | SRT, VTT, ASS, SSA |
| Scientific arrays | MATLAB MAT (v4-v7.2 and numeric v7.3), NumPy NPY/NPZ, HDF5 H5/HDF5/HDF, NetCDF NC/NC4 | MAT, NPY, NPZ, HDF5, NetCDF; rectangular real arrays can also become data tables |
| Statistics and research tables | SPSS SAV/ZSAV/POR, Stata DTA, SAS XPT/SAS7BDAT, R RDS/RDA/RData, Parquet, Feather/Arrow, SQLite, CSV/TSV/DAT/ASC, Excel, Prism PZFX | CSV, TSV, DAT, ASC, XLSX, JSON/JSONL, Parquet, Feather, SAV, ZSAV, POR, DTA, XPT, RDS/RData, SQLite; numeric tables can become scientific arrays |
| Chemical structures | MOL, SDF, SMILES, MOL2, PDB, PDBQT, PQR, XYZ, CIF, GRO, HIN, ALC, MOPAC, Gaussian output, GAMESS output, NWChem output, Molden and others | SDF, MOL, SMILES/canonical SMILES, MOL2, PDB, PDBQT, PQR, XYZ, CIF, GRO, HIN, ALC, MOPAC/Gaussian/NWChem input, extended XYZ |
| Sequences and plasmids | FASTA/FASTQ, GenBank/ApE, EMBL, PIR, NEXUS, PHYLIP, Stockholm, Clustal, MAF/MSF, SeqXML, ABI/AB1, SFF, SnapGene DNA, XDNA, GCK; gzip-compressed common sequence files | FASTA, FASTQ with stored qualities, GenBank, EMBL, PIR, NEXUS, PHYLIP, Stockholm, Clustal, SeqXML, XDNA; SVG/PNG/PDF annotation maps |
| 3D triangle meshes | STL, PLY, OBJ, OFF, GLB/GLTF, 3MF, DAE | STL, PLY, OBJ, OFF, GLB |
| Code and notebooks | Python/PYW, R, Julia, MATLAB, JavaScript, TypeScript, C/C++, C#, Java, Go, Rust, SQL, Fortran, PowerShell, Bash and other scripts; IPYNB, Rmd, QMD | Notebook and same-language scripts; Markdown/Rmd/QMD, highlighted HTML, readable PDF, TXT |
| Structured text | JSON, YAML/YML, TOML, XML | JSON, YAML/YML, TOML, XML when the target can represent the input structure |
| Camera RAW | Canon CR2/CR3/CRW, Nikon NEF/NRW, Sony ARW/SR2/SRF, Fujifilm RAF, Olympus ORF, Panasonic RW2, Pentax PEF, Samsung SRW, Leica RWL, Hasselblad 3FR/FFF, Phase One IIQ, DNG and other LibRaw formats | TIFF, PNG, JPG, WebP, BMP, NPY, NPZ, HDF5 |
| Microscopy | Zeiss CZI/LSM, Nikon ND2, Leica LIF, Imaris IMS, TIFF/OME-TIFF/STK, MRC/MRCS/MAP/REC, and TIFF-based SVS/SCN/BIF/NDPI/GEL/VMS/VMU variants | TIFF stacks, PNG/JPG/WebP/BMP planes, NPY, NPZ, HDF5 |
| Electrophysiology / EEG / LFP | Axon ABF, Spike2 SMR, Intan RHD/RHS, Blackrock NS1-NS6/NEV, Plexon PLX, NeuroExplorer NEX, Neuralynx NCS/NSE/NTT/NEV, Open Ephys legacy files, WinWCP/WCP, WinEDR/EDR, AxoGraph AXGD/AXGX, Igor IBW/PXP, Micromed TRC, NWB, EDF/BDF, FIF, BrainVision VHDR, EEGLAB SET, Neuroscan CNT, GDF, EGI, SNIRF, NEDF | HDF5, NPZ, MAT, CSV, TSV; EDF/BDF and FIF for compatible continuous EEG inputs |
| Genomic records | SAM/BAM, VCF, GFF/GFF3, GTF, BED, BedGraph | CSV, TSV, JSONL; SAM/BAM can export SAM and primary read FASTA/FASTQ |
| Nanopore raw signals | FAST5, POD5 | HDF5, NPZ per read, CSV per read |
| Flow cytometry | FCS | HDF5, NPZ, MAT, CSV, TSV |

## Lab images and recordings

- Video-to-image extracts every frame of the first video track into numbered files. Long videos can produce many files; cancellation removes the current incomplete conversion.
- Camera RAW is demosaiced into sRGB using camera white balance. TIFF and PNG keep the rendered 16-bit samples. This is a rendered image, not the original sensor mosaic. A listed extension does not guarantee support for every camera model or proprietary codec; BRAW and R3D video are not advertised.
- Microscopy TIFF/NPY/NPZ/HDF5 preserves the numeric array, axes and dtype. A JSON sidecar retains parsed calibration and vendor metadata. TIFF output uses shaped TIFF metadata rather than reconstructing a vendor's complete project or OME schema. CZI scenes and LIF image series are exported separately; Imaris exports ResolutionLevel 0. Keep the JSON sidecar with the images.
- PNG preserves unsigned 8/16-bit samples. JPG/WebP/BMP and other PNG input dtypes use an 8-bit display range recorded in the sidecar; these previews are not quantitative analysis data. Z/T/channel dimensions become numbered planes. Pyramid levels, ROIs, acquisition settings and annotations are not universally reproduced. Some readers assemble a whole image series in memory; very large slide scans may exceed available RAM.
- Recording exports retain parsed sample rates, start times, units, segment/channel annotations, events and spike trains. Available spike waveforms are included. HDF5 stores metadata on each dataset; NPZ/MAT also include metadata_json. Text exports contain separate arrays, time columns for regular signals, and a JSON sidecar for labels and calibration. Unsupported experiment objects and vendor-specific analyses are not reconstructed.
- EDF/BDF exports are quantized to their storage bit depth and checked within one quantization step. They require continuous channels with equal whole-second durations and unique labels within the format's ASCII/16-character limit. Original metadata is kept in JSON. HDF5/NPZ/MAT is preferred for numerical analysis or irregular/episodic recordings. FIF export uses double precision and rejects linked split output above roughly 1.9 GB.
- Select BrainVision's VHDR or EEGLAB's SET file with required companion files beside it. Neuralynx exports the selected file; legacy Open Ephys readers load the associated session directory, so select one entry per session. Binary NEX is distinguished from NEXUS text by its signature. SDK-dependent PL2/SMRX, directory-only EEG formats and undocumented raw binaries are not advertised.
- FCS export retains stored events and metadata. It does not apply compensation, log transforms, gating or FlowJo workspace analysis.
- Genomic table exports retain original field strings, sample/genotype columns, header comments and coordinate conventions. They do not perform variant calling, alignment, filtering or coordinate conversion. BAM is read without an index; SAM output preserves auxiliary tag types. FASTA/FASTQ from alignments includes primary records and restores original read orientation, skipping secondary/supplementary alignments. CRAM/BCF are not included.
- FAST5/POD5 export reads VBZ-compressed signals and keeps raw ADC counts, available sample rate/read/channel information and current calibration. Convert to pA using the recorded offset and scale. Basecalling is not performed, so a raw signal cannot become FASTQ without a basecaller.
- SnapGene/GCK imports and GenBank/XDNA exports retain the fields those parsers/writers support. Feature maps display parsed annotations with locations and direction; they do not infer genes or reproduce a vendor's exact map styling. FASTA discards annotations. XDNA exports one record per file. Gzip sequence inputs are decompressed locally; ordinary sequence formats stream records rather than buffering the entire read set.

## PDF to LaTeX

- **tex (text)** extracts editable paragraphs and embedded raster images into a .tex file. Compile with XeLaTeX or LuaLaTeX. It does not reconstruct equation source, tables, columns, vector graphics or the original typography. Scanned PDFs without text are rejected with an OCR message; OCR is not bundled.
- **tex (layout)** creates a .tex wrapper plus a PDF asset using pdfpages. It preserves the original page appearance, including equations and vector drawings; page content remains embedded PDF rather than editable LaTeX. Compile with a standard LaTeX installation containing pdfpages.
- Both modes write files directly into the output folder, update asset references after collision renaming and leave the original file intact. Keep the assets beside the .tex file. A TeX installation is only needed to compile the result, not to perform the conversion.

See INPUTS and OUTPUTS in any2any.py and the converter modules for the complete extension lists. Notebook script choices follow the original programming language. Input aliases are counted separately from file-format families.

## Research and code behavior

- MAT, NPZ, HDF5 and NetCDF keep multiple named arrays in one file. NPY produces one file per array. MATLAB uses column vectors for one-dimensional NumPy inputs.
- HDF5/NetCDF conversion copies root and dataset attributes. NetCDF dimension names survive an HDF5 round trip through an internal dataset attribute. Exports to formats without these attributes apply packing scale/offset and replace declared missing values with NaN. Units and other metadata do not fit every target format.
- Object/pickled arrays, MATLAB cells/structs/references, HDF4, grouped NetCDF datasets and proprietary scientific application models are not supported. Arrays above two dimensions or containing complex numbers are rejected for table output instead of being flattened.
- Table conversion preserves all worksheets/tables: XLSX and SQLite combine tables; single-table formats produce numbered files directly in the output folder. Array export from tables requires numeric columns.
- Statistical exports preserve common column/value labels and user-missing codes when the target supports them. Format-specific metadata is not universal. Legacy formats restrict names, strings and dates; errors leave no partial results. R data-frame export does not preserve arbitrary R lists/S4 objects, factor levels or timezone-aware date types. Large integers are rejected when a statistical/R export would require lossy doubles.
- Delimited data is read as UTF-8 (including a BOM). Imports keep leading-zero identifiers as text; an entirely numeric first row is treated as headerless data with generated column names. Literal strings beginning with an equals sign remain strings in generated spreadsheets. Spreadsheets containing formulas use LibreOffice to calculate values before data export; styles, charts and formulas are not kept in data-only outputs.
- Prism PZFX imports plain XML data tables, including replicate subcolumns. Binary Prism files, graphs and analyses are not converted or executed. Origin currently uses its exported CSV/TSV/DAT/ASC/Excel exchange files; native OPJ/OPJU conversion is not provided.
- Chemical files are parsed by Open Babel. Multi-molecule input produces one file per molecule, with a heavy-atom count check where the output can be read back. Crystal CIF output requires a unit cell. Coordinate-only formats may infer bonding; bond order, stereochemistry, charges, residues and calculation settings are not universally preserved. Quantum chemistry output exports the structure, not the full calculation results.
- If a small molecule lacks coordinates and a geometry format needs them, Open Babel generates a starting 3D geometry. This is limited to 200 atoms, may add hydrogens and is not a validated optimized structure.
- Biological conversion checks the sequence content. FASTQ needs existing quality scores. FASTA has no feature annotations or quality scores; sequence type is inferred when absent, with FNA/FAA indicating DNA/protein. Alignment formats require equal-length sequences and may limit identifiers.
- Mesh export checks geometry bounds. GLB keeps a scene in one file; other targets flatten scene transforms into a triangle mesh. OBJ output contains geometry without external texture files. Materials, units and scene metadata depend on the output format.
- Source code is never run. Notebook/script conversion retains its programming language and original source extension, rather than translating algorithms into another language. Exported notebooks need the matching kernel to run; kernel-specific magics, dependencies and runtime behavior require the original environment.
- Notebook HTML/PDF includes code, Markdown, text outputs and inline PNG figures. Script/Markdown exports do not preserve every rich output or interactive widget. PDF wraps long code lines for readability. QMD uses the common R Markdown cell syntax; Quarto-specific execution/render options are outside this converter.
- YAML uses safe parsing, NumPy pickle loading is disabled, and XML DTDs/entities are rejected. XML conversion keeps text/structure, not JSON numeric/boolean types. XML needs one root key; TOML cannot represent null or a top-level array. Comments and formatting in structured text are not preserved.

## Output and fidelity

- Files are decoded and encoded, or converted through Office/Pandoc. This is not extension renaming.
- Originals are preserved. Converted files go directly into the output folder. Duplicate filenames receive a numeric suffix; existing files are never overwritten.
- Conversion uses a temporary folder outside the output folder. Validated results are then published as files. Failure or cancellation rolls back the current conversion. Details shows the errors.
- JPG, BMP, PPM and image-to-PDF outputs use white backgrounds for transparency. ICO images are limited to 256 by 256 pixels.
- Animated GIF, WebP, PNG/APNG and AVIF outputs retain frames. TIFF/PDF outputs retain pages. Static image outputs such as JPG export each frame separately.
- PDF images are rendered at 150 DPI, one file per page. PDF-to-TXT and editable LaTeX extract existing text without OCR. Use tex (layout) for scanned pages. Editable PDF-to-Word is not provided.
- Media output uses the first video and audio tracks and stereo audio. Extra tracks, embedded subtitles, chapters and attachments are not copied. MP4 uses H.264/AAC; odd image dimensions are padded to even dimensions.
- Compression may be lossy. Document layout, fonts, formulas, animation and special features can change. PSD and similar images are flattened without retaining editable layers.
- CSV/TSV data export writes separate files for multiple worksheets and cannot retain workbook layout or formulas. Plain text and subtitle formats cannot retain all styling.
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
The original suite covers 84 conversions plus Unicode filenames, transparency, frames/pages, collisions, original preservation, cancellation and the compact GUI. test_extra_formats.py covers generated research/code fixtures and checks numeric values, dimensions, missing-value scaling, precision, statistical labels, sequences, geometry, source retention and blocked object loading.
test_lab_formats.py adds generated camera DNG, two-scene CZI, multidimensional OME-TIFF, MRC/Imaris, SnapGene, BAM/SAM, genomic, FAST5/POD5, ABF, EDF/FIF/NWB, FCS and PDF-to-LaTeX checks. These fixtures do not cover every vendor model or file variant.

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

- [pandas IO](https://pandas.pydata.org/docs/user_guide/io.html), [SciPy MAT](https://docs.scipy.org/doc/scipy/reference/io.html), [h5py](https://docs.h5py.org/) and [NetCDF4](https://unidata.github.io/netcdf4-python/): scientific data.
- [pyreadstat](https://github.com/Roche/pyreadstat) and [pyreadr](https://github.com/ofajardo/pyreadr): statistical formats.
- [Open Babel / Pybel](https://openbabel.org/docs/UseTheLibrary/Python_Pybel.html): chemistry. The installed Windows wheel is maintained by [openbabel-wheel](https://github.com/njzjz/openbabel-wheel).
- [Biopython SeqIO](https://biopython.org/wiki/SeqIO), [Trimesh](https://trimesh.org/) and [Jupytext](https://jupytext.readthedocs.io/): sequences, meshes and notebooks.

The MIT license covers Any2Any source code. Third-party components retain their own licenses; their binaries are excluded from this repository.

- [rawpy / LibRaw](https://github.com/letmaik/rawpy), [tifffile](https://github.com/cgohlke/tifffile), [czifile](https://github.com/cgohlke/czifile), [nd2](https://github.com/tlambert03/nd2), [readlif](https://github.com/Arcadia-Science/readlif) and [mrcfile](https://mrcfile.readthedocs.io/): lab images.
- [Neo IO](https://neo.readthedocs.io/en/stable/iolist.html), [MNE](https://mne.tools/stable/overview/implementation.html), [PyEDFlib](https://pyedflib.readthedocs.io/) and [PyNWB](https://pynwb.readthedocs.io/): calibrated recordings.
- [BAMnostic](https://github.com/betteridiot/bamnostic), [POD5](https://github.com/nanoporetech/pod5-file-format) and [FlowIO](https://github.com/whitews/FlowIO): specialized lab formats.
