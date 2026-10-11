# Fidelity validation

Validated on Windows with the pinned dependencies, 2026-10-11.

**Not every supported conversion is lossless.** Opening a result proves readability,
not numerical, annotation or layout fidelity. The checks below use generated files;
they are not a certification of every vendor format, model or version.

## Results

Run `RunTests.bat` to repeat the four suites. They cover 441 successful conversions,
31 refused-loss cases, and additional cancellation, collision and interface checks.
All generated source files remain unchanged. Existing outputs are not overwritten;
failed conversions publish no partial files.

| Area | What was checked | Limits |
| --- | --- | --- |
| Numeric arrays | Exact float64/complex128/int64/uint64/logical values, non-finite values, dtype and multidimensional shapes; HDF5 group/dataset attributes and NetCDF calibration/dimensions | MAT represents scalars as 1x1 and 1D vectors as columns. NetCDF boolean storage differs. Object/reference arrays and linked HDF5 objects are rejected. |
| Research tables | Nullable integers above 2^53, unsigned 64-bit values, leading-zero IDs, literal NA/NULL text, floating-point precision, row labels, worksheets and common statistical labels | CSV has no type schema and may merge empty strings with missing cells. Statistical formats can normalize names or omit unsupported metadata. Workbook formulas/styles/charts do not survive data-only exports. |
| Lab images | Exact rendered uint16 samples and float64 stacks, dimensions, axes, calibration sidecars; generated DNG/CZI/OME-TIFF/MRC/Imaris fixtures | RAW export is a rendered sRGB image, not preserved sensor data. Vendor projects, pyramid levels, ROIs and every acquisition field are not reconstructed. |
| Ordinary images | Exact representative RGBA PNG samples, PNG text, ICC bytes and resolution; animation frame counts and PDF page counts | JPEG/WebP/AVIF/HEIC compression, palette conversion, transparency flattening, resized icons and rasterized PDF are not lossless. Metadata is not universal across image formats. |
| Recordings | Calibrated ABF/EEG/FIF/NWB/FCS samples, sample rates, units, event labels/times, first sample, available spike-waveform offset; FAST5/POD5 ADC counts and current calibration | Export keeps parsed signals and metadata, not every experiment/project object. Basecalls, proprietary analyses, EEG processing state and all vendor metadata are not universally reproduced. |
| EDF/BDF | Channel counts, sample counts/rates, calibration tolerance and event labels/times | Samples are quantized within 1.1 digital steps; annotation times are checked within 0.1 ms. This is not exact float preservation. |
| Sequences/plasmids | FASTQ qualities and sequence case; representative GenBank/EMBL feature locations, strand, qualifiers and circular topology; BAM/SAM tags and read orientation | FASTA drops qualities/features. Alignment-to-reads exports primary alignments only. Rich annotations depend on parser/writer support; some formats normalize sequence case. Maps are pictures, not sequence archives. |
| Chemistry | Representative SDF/MOL/SMILES bond orders, aromaticity, formal charge and stereochemistry | Coordinate-only formats, residues, crystal/calculate metadata and generated geometry are not universally preserved. Runtime validation of other chemistry outputs checks heavy-atom count only. |
| Meshes | Representative triangle counts and coordinates within float32 tolerance | Some formats reduce coordinate precision. Textures, materials, units, scene structure and topology are not guaranteed. Runtime validation checks geometry bounds. |
| Code/structured text | Representative source round trips, notebook language/source, escaped output, structured values and no input-code execution | Languages are not translated. Notebook rich outputs, formatting, comments and XML scalar types do not universally survive. |
| Documents/PDF/LaTeX | Office/PDF readability, representative text/pages, asset references and rollback. Both LaTeX modes previously compiled on a generated two-page sample; layout output was rendered and compared | Office/Pandoc can change fonts, layout, formulas and special features. Editable LaTeX does not recover equation source, tables or vectors. Layout mode embeds PDF pages and preserves appearance, not editable document structure. |
| Audio/video | Exact decoded PCM24/32 and float32/64 audio, original channel counts and sample rates for WAV/AIFF/AU; exact FLAC where representable; media readability and extracted frame counts | Existing lossy input cannot be restored. Video and compressed-audio exports remain lossy and select the first tracks. Full visual equality of every long-video frame was not checked. |

## Bugs fixed during validation

- Prevented rounding of nullable large integers during CSV, JSON and SQLite import.
- Rejected table-to-array casts that would round integers when mixing numeric types.
- Added exact value readback for scientific table-to-XLSX output. Precision loss rejects
  the conversion instead of saving the rounded workbook; this check does not cover
  every legacy Office-to-Office conversion.
- Retained meaningful table row labels as columns and MAT logical arrays as booleans.
- Prevented small-integer overflow during packing scale/offset arithmetic; rejected
  packed large-integer exports that cannot safely become floating-point values.
- Preserved HDF5 groups, empty groups and their attributes. Soft/external links and
  hard-link aliases are rejected instead of silently disappearing.
- Added JSON sidecars for scientific source attributes, table schema, array shapes
  and dtype. These preserve parsed source metadata, not complete project files; not
  every reverse converter automatically reapplies them. Keep sidecars with outputs.
- Preserved available spike-waveform left-sweep timing and removed integer-to-float
  coercion when adding time columns to recording CSV/TSV output.
- Added EDF/BDF sampling-rate and event readback checks.
- Rejected FASTQ quality clipping and PHYLIP identifier truncation; checked FASTQ
  qualities and FASTA/FASTQ letter case after writing.
- Preserved static PNG text/resolution metadata.
- Removed forced stereo/16-bit conversion for WAV/AIFF/AU/FLAC. PCM codecs follow
  decoded input precision and channel count. Full decoded-sample SHA-256 comparisons
  reject changes; floating-point or unrepresentable FLAC exports fail safely.
  Hash validation decodes both complete streams and adds time for large audio files.

## Scope

Use `test_fidelity.py` for adversarial cases, `test_extra_formats.py` for research/code,
`test_lab_formats.py` for lab formats and `test_any2any.py` for core/UI behavior.
The supported-extension list describes available readers and writers, not a guarantee
that every pair retains every input field. Read the limits in [FORMATS.md](FORMATS.md).

No real files from every camera/microscope/electrophysiology vendor, very large
recordings, every Office equation/layout, or all corrupt/proprietary variants were
tested. Keep originals; use numeric array/recording exports for analysis, retain their
metadata, and check representative files from the actual instrument before replacing
a research workflow.
