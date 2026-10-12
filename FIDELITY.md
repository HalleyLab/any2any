# Fidelity validation

Validated on Windows with the pinned dependencies, 2026-10-12.

**Supported does not mean universally lossless.** A readable output can still lose
values, annotations or layout. Preservation files retain information that the
selected target cannot hold; keep them beside the result. They are not automatically
reapplied by every reverse converter. Originals are never replaced.

## Results

The six suites completed **1,298 successful conversions and 58 safe refusals**,
plus cancellation, collision and original-preservation checks. Local API and browser
checks cover cross-folder selection, extension-based names, asset links, flat ZIP
downloads, save streams, access controls and responsive layouts.
Failures publish no partial files; existing outputs are not overwritten.

| Suite | Successful conversions | Safe refusals |
| --- | ---: | ---: |
| Core | 84 | Additional safety assertions |
| Research/code | 166 | Additional boundary assertions |
| Generated lab/image/genomic/LaTeX | 113 | Additional safety assertions |
| Adversarial fidelity | 78 | 31 |
| Extended cross-format/preservation | 811 | 27 |
| Public instrument samples | 46 | 0 |

The public suite checks 6 Leica image series and 881 signal/event/waveform arrays
containing 7,851,613 recording values. It includes XZ, emission/excitation wavelength
and combined Z/time/wavelength acquisitions; ABF1/ABF2, Spike2 SMR, Plexon PLX,
Intan RHD and NeuroExplorer NEX. Leica planes match independently exported
Fiji/Bio-Formats TIFF references. All ABF sweeps/channels also match development-only
pyABF within float32 reader precision. Remaining export comparisons are exact
against the parsed arrays, not an independent certification of each vendor decoder.

Run `RunTests.bat` for all suites. Public samples require a one-time explicit
`test_vendor_formats.py --download`; without the cache that suite reports SKIP.
[Fixture provenance](fixtures/README.md) and [URL/hash manifest](fixtures/vendor-samples.json)
record the external samples; binaries stay outside Git.

## Preservation and checks

| Area | Checks and retained information | Limits |
| --- | --- | --- |
| Arrays | Cross-format matrix: bool, signed/unsigned 8/16/32/64-bit integers, float16/32/64, complex64/128, Unicode/binary strings; scalar, vector, matrix, 3D and empty shapes. Exact runtime readback checks names, shape, values, complex components and signed zero. HDF5 groups/attributes and NetCDF calibration/dimensions retain metadata. | MAT uses 1x1 scalars and column vectors; padded/reshaped strings are rejected. NetCDF uses integer bool storage and promotes float16 exactly. Object/reference arrays, linked HDF5 objects and grouped NetCDF are refused. |
| Tables | Large nullable integers, leading-zero IDs, empty versus missing text, booleans, precise floats, worksheets and common labels. Reopen outputs; add an exact typed Parquet companion when values, column names or dtypes differ. Schema/attributes remain in JSON. Scientific XLSX numeric changes are refused. | Parsed tables are preserved, not complete workbook formulas/styles/charts or arbitrary R/SPSS project objects. A companion may be required to recover original types or values. |
| Microscopy/RAW | Full numeric arrays, axes, parsed metadata and calibration; Leica spectral/XZ axes and acquisition XML. TIFF pyramid levels and visible RAW sensor mosaic/Bayer pattern retain NPZ companions. Reduced-depth/lossy previews retain original numeric arrays. | RAW primary outputs are rendered sRGB. Sensor margins, proprietary projects and every ROI/acquisition object are not reconstructed. Some readers need an entire series in RAM. Unsupported LIF channel layouts or inconsistent pixel blocks are refused. |
| Ordinary images | Representative RGBA/uint16 samples, palettes, parsed metadata, ICC/resolution; lossless static WebP. Lossy, flattened, resized and animated-WebP exports retain decoded pixel companions. Animation frames/timing are checked. | JPEG/AVIF/HEIC, palette changes and resized icons can change primary pixels. Animated WebP can normalize RGB beneath zero alpha; companions retain those samples. PSD layers and unknown source fields are not archived. |
| Recordings | Complete parsed samples, sample rates, units, labels/times, first sample and available waveform timing. Neo analog calibration uses float64 and records original channel calibration. CSV/TSV decimal output round-trips parsed float values exactly. HDF5/NPZ/MAT retain arrays and JSON metadata. | Proprietary analyses, original ADC blocks, all project metadata and every acquisition variant are not universally archived. Reader calibration and interpretation still matter. |
| EDF/BDF/nanopore | EDF sample rate/count/calibration/event readback; FAST5/POD5 exact ADC counts plus current calibration and read/channel data. | EDF/BDF quantizes within 1.1 digital steps; event times within 0.1 ms. Nanopore export does not perform basecalling. |
| Sequences/plasmids | Sequence/case and FASTQ quality checks. Every parsed record also retains JSONL sequence, identifiers, quality arrays, annotations and GenBank feature locations/qualifiers. Gzip multi-record XDNA/maps keep separate files. | FASTA primary files cannot hold qualities/features. Writers may omit fuzzy locations or normalize annotation fields; the companion retains parsed data. Alignment-to-reads includes primary alignments only. Maps are pictures. |
| Notebooks/structured text | Original notebook cells, metadata, outputs and attachments retain an IPYNB companion. Structured conversions keep original source bytes, including comments and scalar representation. Input code is never executed. | Scripts/HTML/PDF cannot reproduce interactive notebook behavior. Structured primary output can normalize formatting/types; unsupported structures fail. |
| Documents/PDF/LaTeX | Paragraphs, table cells, exact numeric text and image captions across DOCX/ODT/RTF/PDF/HTML/TXT/Markdown/LaTeX; pages, assets, collisions and rollback. Both PDF-to-LaTeX modes previously compiled on a two-page sample. | Fonts, layout, equations and advanced Office objects are not universally preserved. Editable PDF-to-LaTeX does not recover equation source/tables/vectors. Layout mode embeds PDF pages. |
| Chemistry/meshes | Representative chemistry bonds/charge/stereochemistry and mesh triangle counts/coordinates; runtime heavy-atom/bounds checks. | Not all coordinates, residues, textures, materials, topology, scene or calculation metadata are guaranteed. |
| Audio/video | Exact decoded PCM24/32 and float32/64 audio, channels and sample rates; full sample hashes for WAV/AIFF/AU/representable FLAC. Frame/readability checks for video. | Lossy input cannot be restored. Video/compressed audio remains lossy and selects the first tracks. Every frame of long videos was not visually compared. |

## Additional defects fixed

- Restored Leica wavelength dimensions that were previously omitted, and XZ scans
  that previously failed. Pixel block sizes must match declared dimensions/bit depth.
- Avoided forcing waveform loading for channels without waveforms; normalized Neo
  annotation arrays required by real Intan recordings.
- Prevented float32 string formatting from shortening recording CSV samples.
- Preserved RAW sensor/Bayer information before demosaicing mutates decoder state.
- Kept binary HDF5 strings as bytes; avoided reserved-key collisions in NPZ writing;
  refused duplicate NPZ variables and duplicate delimited headers.
- Added exact array readback so incompatible MAT strings and NetCDF types fail
  before publication, instead of producing silently changed data.
- Fixed compressed multi-record sequence filenames and icons smaller than 16 pixels.
- Updated preservation-file references after collision renaming, without modifying
  user-authored JSON that happens to contain similar keys.

## Scope

Tests cover generated boundary cases and selected public acquisitions, not every
camera/microscope brand, firmware, huge recording or damaged/proprietary variant.
No speed comparison against other applications was performed. Preservation files
and complete readback checks consume additional disk space, RAM and time.

Keep originals. For analysis, prefer full numeric/recording exports and their
metadata; validate representative files from the actual instrument before changing
a research workflow. See [FORMATS.md](FORMATS.md) for supported readers and limits.
