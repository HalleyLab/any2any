"""Boundary/cross-format matrix and recoverable preservation companions."""
from pathlib import Path
import gzip
import hashlib
import json
import tempfile

import h5py
import nbformat
import numpy as np
import pandas as pd
import tifffile
from PIL import Image
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, CompoundLocation, SimpleLocation, BeforePosition, AfterPosition
from Bio.SeqRecord import SeqRecord
import any2any as a
import scientific as s
from test_lab_formats import make_dng


def main():
    conversions = refused = 0
    with tempfile.TemporaryDirectory(prefix="any2any-coverage-") as folder:
        root = Path(folder)
        def convert(source, ext, out=None):
            nonlocal conversions
            out = out or root / f"output_{conversions:04d}"
            before = hashlib.sha256(source.read_bytes()).digest()
            result = a.convert(source, ext, out)
            assert hashlib.sha256(source.read_bytes()).digest() == before
            assert result and all(file.parent == out for file in result)
            assert all(file.is_file() for file in out.iterdir())
            conversions += 1
            return result

        def preserved(result):
            out = result[0].parent
            return [(out / item["file"], item) for file in out.glob("*.json")
                    for item in json.loads(file.read_text(encoding="utf-8")).get("preserved_files", [])]

        for dtype in ("bool", "int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float16", "float32", "float64", "complex64", "complex128", "U6", "S6"):
            kind = np.dtype(dtype).kind
            if kind in "iu":
                bounds = np.iinfo(dtype)
                values = np.array([bounds.min, bounds.max, 0, 1, 2, 3], dtype=dtype)
            elif kind in "fc":
                values = np.array([0., -0., np.nextafter(np.array(0, dtype=dtype), np.array(1, dtype=dtype)) if kind == "f" else 1 + 2j, np.nan, np.inf, -np.inf], dtype=dtype)
            elif kind == "b":
                values = np.array([False, True] * 3)
            elif kind == "U":
                values = np.array(["alpha", "beta", "", "NA", "007", "line"], dtype=dtype)
            else:
                values = np.array([b"alpha", b"\xff", b"", b"a\x00b", b"007", b"line"], dtype=dtype)
            for shape in ((), (6,), (2, 3), (1, 2, 3), (0, 3)):
                expected = values[:1].reshape(()) if not shape else np.empty(shape, dtype=dtype) if 0 in shape else values.reshape(shape)
                source = root / f"matrix_{dtype}_{len(shape)}_{expected.size}.npy"
                np.save(source, expected, allow_pickle=False)
                for ext in ("npy", "npz", "mat", "h5", "nc"):
                    out = root / f"output_{conversions:04d}"
                    should_refuse = (ext == "nc" and kind in "cS") or (ext == "mat" and kind in "US")
                    try:
                        result = convert(source, ext, out)
                    except (ValueError, TypeError, RuntimeError) as error:
                        if not should_refuse:
                            raise AssertionError(f"Unexpected refusal: {dtype} {shape} -> {ext}: {error}") from error
                        assert not list(out.iterdir())
                        refused += 1
                        continue
                    if should_refuse:
                        raise AssertionError(f"Expected an incompatible format to be refused: {dtype} {shape} -> {ext}")
                    arrays, _ = s.read_arrays(result[0])
                    actual, = arrays.values()
                    assert actual.size == expected.size
                    np.testing.assert_array_equal(actual.reshape(shape), expected)
                    if kind == "f":
                        np.testing.assert_array_equal(np.signbit(actual.reshape(shape)[expected == 0]), np.signbit(expected[expected == 0]))
                    back = convert(result[0], "npz")[0]
                    restored, _ = s.read_arrays(back)
                    np.testing.assert_array_equal(next(iter(restored.values())).reshape(shape), expected)
            print(f"PASS cross-format matrix {dtype}", flush=True)

        for names in (("file", "allow_pickle"), ("group/value", "root")):
            source = root / "names.h5"
            with h5py.File(source, "w") as file:
                for index, name in enumerate(names):
                    file.create_dataset(name, data=np.arange(6).reshape(2, 3) + index)
            result = convert(source, "npz")[0]
            arrays, _ = s.read_arrays(result)
            assert set(arrays) == set(names)
            for index, name in enumerate(names):
                np.testing.assert_array_equal(arrays[name], np.arange(6).reshape(2, 3) + index)
        import io
        import warnings
        import zipfile
        duplicate_npz = root / "duplicate.npz"
        buffer = io.BytesIO()
        np.save(buffer, np.arange(3), allow_pickle=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate_npz, "w") as archive:
                archive.writestr("same.npy", buffer.getvalue())
                archive.writestr("same.npy", buffer.getvalue())
        try:
            convert(duplicate_npz, "h5")
        except ValueError as error:
            assert "duplicate" in str(error).lower()
            refused += 1
        else:
            raise AssertionError("Duplicate NPZ variables must not be silently discarded")
        print("PASS NPZ reserved names and nested array paths", flush=True)

        frame = pd.DataFrame({"id": pd.array(["007", "8", "NA", "", None], dtype="string"),
            "integer": pd.array([2**53 + 1, None, -5, 0, 2**53 + 3], dtype="Int64"),
            "flag": pd.array([True, False, None, True, False], dtype="boolean"),
            "value": [.1, np.nan, np.nextafter(1., 2.), -0., 1e100]})
        source = root / "typed.parquet"
        frame.to_parquet(source, index=False)
        for ext in ("csv", "tsv", "json", "jsonl", "sqlite", "feather", "parquet"):
            result = convert(source, ext)
            backups = preserved(result)
            if backups:
                assert len(backups) == 1
                pd.testing.assert_frame_equal(pd.read_parquet(backups[0][0]), frame, check_exact=True)
            else:
                pd.testing.assert_frame_equal(next(iter(s.read_tables(result[0]).values())), frame, check_exact=True)
        duplicate = root / "duplicate.csv"
        duplicate.write_text("same,same\n1,2\n", encoding="utf-8")
        try:
            convert(duplicate, "parquet")
        except ValueError as error:
            assert "duplicate" in str(error).lower()
            refused += 1
        else:
            raise AssertionError("Duplicate column names must not be renamed silently")
        print("PASS typed table companions: nulls, empty text, large integers, booleans and precise floats", flush=True)

        source = root / "rich.ipynb"
        notebook = nbformat.v4.new_notebook(metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}, "experiment": {"run": 42}})
        notebook.cells = [nbformat.v4.new_markdown_cell("![plot](attachment:plot.png)", attachments={"plot.png": {"image/png": "YWJj"}}),
            nbformat.v4.new_code_cell("path = 'preserved_notebook.ipynb'\nprint(1)", execution_count=7, outputs=[nbformat.v4.new_output("display_data", data={"text/plain": "sample", "application/json": {"value": 2**53 + 1}}, metadata={"run": 7})])]
        nbformat.write(notebook, source)
        for ext in ("py", "md", "html", "pdf", "txt"):
            result = convert(source, ext)
            backup, = result[0].parent.glob("*.ipynb")
            assert nbformat.read(backup, as_version=4) == notebook
            if ext in ("md", "html"):
                assert "preserved_notebook.ipynb" in result[0].read_text(encoding="utf-8")
        print("PASS complete Notebook metadata, outputs and attachments alongside exports", flush=True)
        for src, text, extensions in (("json", '{"root": {"value": 9007199254740993, "flag": true}}', ("xml", "yaml", "toml", "json")),
                                      ("yaml", "# preserve comment\\nroot:\\n  value: 42\\n", ("json", "yaml"))):
            source = root / ("structured." + src)
            source.write_text(text.replace("\\n", "\n"), encoding="utf-8")
            for ext in extensions:
                result = convert(source, ext)
                backups = [file for file in result[0].parent.iterdir() if file not in result and file.suffix == source.suffix]
                assert len(backups) == 1 and backups[0].read_bytes() == source.read_bytes()
        source = root / "user_metadata.json"
        source.write_text('{"preserved_files": [{"file": "untouched"}]}', encoding="utf-8")
        result = convert(source, "yaml")
        backup, = result[0].parent.glob("*.json")
        assert backup.read_bytes() == source.read_bytes()
        source = root / "preserved_source.json"
        source.write_text('{"value": 42}', encoding="utf-8")
        result = convert(source, "json")
        assert len(result) == 1 and json.loads(result[0].read_text(encoding="utf-8")) == {"value": 42}
        backup, = [file for file in result[0].parent.glob("*.json") if file not in result]
        assert backup.read_bytes() == source.read_bytes()
        print("PASS original structured-source bytes including comments and scalar types", flush=True)


        records = [SeqRecord(Seq("ACGTACGT"), id=f"plasmid_{index}", name=f"plasmid_{index}", description="annotated circular DNA") for index in range(2)]
        for record in records:
            record.annotations.update(molecule_type="DNA", topology="circular", organism="synthetic construct")
            record.features = [SeqFeature(CompoundLocation([SimpleLocation(BeforePosition(1), 3, strand=-1), SimpleLocation(5, AfterPosition(7), strand=-1)]), type="CDS", qualifiers={"label": ["marker"], "note": ["preserve annotation"]})]
        source = root / "plasmids.gb"
        SeqIO.write(records, source, "genbank")
        result = convert(source, "fasta")
        backup, = result[0].parent.glob("*.jsonl")
        original = [json.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()]
        assert len(original) == 2 and original[0]["annotations"]["topology"] == "circular"
        assert original[0]["features"][0]["location_genbank"] == "complement(join(6..>7,<2..3))"
        zipped = root / "plasmids.gb.gz"
        zipped.write_bytes(gzip.compress(source.read_bytes()))
        for ext in ("xdna", "svg", "png", "pdf"):
            result = convert(zipped, ext)
            assert len(result) == 2
            backup, = result[0].parent.glob("*.jsonl")
            assert len(backup.read_text(encoding="utf-8").splitlines()) == 2
        read = SeqRecord(Seq("AcgT"), id="quality", letter_annotations={"phred_quality": [0, 40, 60, 93]})
        fastq = root / "quality.fastq"
        SeqIO.write(read, fastq, "fastq")
        result = convert(fastq, "fasta")
        backup, = result[0].parent.glob("*.jsonl")
        data = json.loads(backup.read_text(encoding="utf-8"))
        assert data["sequence"] == "AcgT" and data["letter_annotations"]["phred_quality"] == [0, 40, 60, 93]
        print("PASS sequence annotation/quality companions and compressed multi-record maps", flush=True)

        for dtype in ("uint16", "float64"):
            values = np.arange(2 * 8 * 10, dtype=dtype).reshape(2, 8, 10)
            if dtype == "float64":
                values = values / 19
                values[0, 0, :3] = [np.nan, np.inf, -np.inf]
            source = root / f"stack_{dtype}.tiff"
            tifffile.imwrite(source, values, photometric="minisblack", metadata={"axes": "ZYX"})
            for ext in ("jpg", "webp", "bmp") + (("png",) if dtype == "float64" else ()):
                result = convert(source, ext)
                backup, = preserved(result)
                with np.load(backup[0], allow_pickle=False) as archive:
                    np.testing.assert_array_equal(archive["image"], values)
        camera = root / "camera.dng"
        make_dng(camera)
        import rawpy
        with rawpy.imread(str(camera)) as raw:
            sensor = raw.raw_image_visible.copy()
            pattern = raw.raw_pattern.copy()
        for ext in ("tiff", "png", "npz", "h5"):
            result = convert(camera, ext)
            backup, = preserved(result)
            with np.load(backup[0], allow_pickle=False) as archive:
                np.testing.assert_array_equal(archive["sensor_visible"], sensor)
                np.testing.assert_array_equal(archive["raw_pattern"], pattern)
        pyramid = root / "pyramid.tiff"
        values = np.arange(64, dtype="uint16").reshape(8, 8)
        with tifffile.TiffWriter(pyramid) as writer:
            writer.write(values, subifds=1, photometric="minisblack")
            writer.write(values[::2, ::2], subfiletype=1, photometric="minisblack")
        result = convert(pyramid, "tiff")
        backup, = preserved(result)
        with np.load(backup[0], allow_pickle=False) as archive:
            np.testing.assert_array_equal(archive["pyramid_1"], values[::2, ::2])
        print("PASS exact microscopy preview companions, visible RAW mosaic and TIFF pyramids", flush=True)

        rgba = np.arange(8 * 10 * 4, dtype="uint8").reshape(8, 10, 4)
        rgba[0, :, 3] = 0
        source = root / "rgba.png"
        Image.fromarray(rgba).save(source)
        result = convert(source, "webp")
        with Image.open(result[0]) as image:
            np.testing.assert_array_equal(np.asarray(image), rgba)
        out = root / "collisions"
        out.mkdir()
        (out / "rgba_asset_1.npy").write_bytes(b"existing file")
        for ext in ("jpg", "ico", "bmp", "pdf", "gif"):
            result = convert(source, ext, out)
            candidates = [entry for entry in preserved(result) if entry[0].suffix == ".npy"]
            for file, _ in candidates:
                np.testing.assert_array_equal(np.load(file, allow_pickle=False), rgba)
        assert (out / "rgba_asset_1.npy").read_bytes() == b"existing file"
        print("PASS lossless transparent WebP and collision-safe decoded-pixel companions", flush=True)
        frames = [Image.fromarray(np.roll(rgba, index, axis=1)) for index in range(3)]
        animation = root / "animation.png"
        frames[0].save(animation, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=2)
        for ext in ("webp", "png", "tiff", "gif", "jpg"):
            result = convert(animation, ext)
            if ext in ("webp", "png", "tiff"):
                with Image.open(result[0]) as image:
                    assert image.n_frames == 3
                    for index in range(3):
                        image.seek(index)
                        expected = np.roll(rgba, index, axis=1)
                        actual = np.asarray(image)
                        if ext == "webp":
                            np.testing.assert_array_equal(actual[..., 3], expected[..., 3])
                            np.testing.assert_array_equal(actual[expected[..., 3] != 0], expected[expected[..., 3] != 0])
                        else:
                            np.testing.assert_array_equal(actual, expected)
                        if ext in ("webp", "png"):
                            assert image.info["duration"] == [100, 200, 300][index] and image.info["loop"] == 2
                    image.close()
            if ext in ("webp", "gif", "jpg"):
                assert len(preserved(result)) == 3
                for file, item in preserved(result):
                    np.testing.assert_array_equal(np.load(file, allow_pickle=False), np.roll(rgba, item["frame"], axis=1))
        high = root / "high.png"
        high_values = np.arange(80, dtype="uint16").reshape(8, 10) * 800
        Image.fromarray(high_values).save(high)
        result = convert(high, "webp")
        backup, = preserved(result)
        np.testing.assert_array_equal(np.load(backup[0], allow_pickle=False), high_values)
        print("PASS animation pixels/timing and 16-bit PNG preview preservation", flush=True)

        document = root / "report.md"
        tokens = ["ParagraphMarkerA", "TableMarkerB", "001230045", "9007199254740993", "0.12345678901234567", "CaptionMarkerC"]
        Image.new("RGB", (40, 30), "red").save(root / "figure.png")
        document.write_text("# Content audit\\n\\n" + tokens[0] + "\\n\\n| Sample | Value |\\n|---|---|\\n| " + tokens[1] + " | " + tokens[2] + " |\\n| " + tokens[3] + " | " + tokens[4] + " |\\n\\n![" + tokens[5] + "](figure.png)\\n", encoding="utf-8")
        document.write_text(document.read_text(encoding="utf-8").replace("\\n", "\n"), encoding="utf-8")
        docx = convert(document, "docx")[0]
        for ext in ("docx", "odt", "rtf", "pdf", "html", "txt", "md", "tex"):
            result = convert(docx, ext)[0]
            if ext == "pdf":
                import pymupdf
                with pymupdf.open(result) as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
            elif ext in ("docx", "odt"):
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(result) as archive:
                    text = " ".join(ET.fromstring(archive.read("word/document.xml" if ext == "docx" else "content.xml")).itertext())
            elif ext == "rtf":
                text = a.run_command([a.pypandoc.get_pandoc_path(), result, "--to", "plain"])
            else:
                text = result.read_text(encoding="utf-8")
            assert all(token in text for token in tokens), (ext, [token for token in tokens if token not in text])
        print("PASS document paragraphs, table text, exact numeric text and image captions across eight outputs", flush=True)
        a.close_office()

        print(f"SUCCESS: {conversions} extended conversions and {refused} safe refusals.", flush=True)


if __name__ == "__main__":
    main()
