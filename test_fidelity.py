"""Adversarial fidelity checks: exact samples, metadata, and refused lossy casts."""
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
import csv
import hashlib
import json
import re
import subprocess
import tempfile

import h5py
import numpy as np
import pandas as pd
import tifffile
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import any2any as a
import scientific as s
import lab_signals as lab


def main():
    conversions = refused = 0
    with tempfile.TemporaryDirectory(prefix="any2any-fidelity-") as name:
        root, out = Path(name), Path(name) / "output"
        out.mkdir()
        def convert(source, ext):
            nonlocal conversions
            digest = hashlib.sha256(source.read_bytes()).digest()
            result = a.convert(source, ext, out)
            assert result and all(file.parent == out for file in result)
            assert hashlib.sha256(source.read_bytes()).digest() == digest
            assert all(file.is_file() for file in out.iterdir())
            conversions += 1
            return result

        def reject(source, ext):
            nonlocal refused
            before = {file: hashlib.sha256(file.read_bytes()).digest() for file in out.iterdir()}
            digest = hashlib.sha256(source.read_bytes()).digest()
            try:
                a.convert(source, ext, out)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError(f"Lossy conversion was accepted: {source.name} -> {ext}")
            assert {file: hashlib.sha256(file.read_bytes()).digest() for file in out.iterdir()} == before
            assert hashlib.sha256(source.read_bytes()).digest() == digest
            refused += 1

        huge = root / "nullable.csv"
        huge.write_text("id,value\n9007199254740993,0.1\n,0.2\n9007199254740995,0.3\n", encoding="utf-8")
        expected = [9007199254740993, None, 9007199254740995]
        def ids(frame):
            return [None if pd.isna(value) else int(value) for value in frame["id"].tolist()]
        assert ids(s.read_tables(huge)["data"]) == expected
        for ext in ("csv", "tsv", "dat", "asc", "parquet", "feather", "json", "jsonl", "sqlite"):
            result = convert(huge, ext)[0]
            assert ids(next(iter(s.read_tables(result).values()))) == expected, ext
        reject(huge, "xlsx")
        for ext in s.ARRAYS:
            reject(huge, ext)
        mixed = root / "mixed.parquet"
        pd.DataFrame({"id": np.array([2**53 + 1, 2**53 + 3], dtype="int64"), "value": [.25, .75]}).to_parquet(mixed, index=False)
        for ext in s.ARRAYS:
            reject(mixed, ext)
        reject(mixed, "xlsx")
        precise = root / "precise.parquet"
        pd.DataFrame({"value": [1.2345678901234567, np.nextafter(1., 2.)]}).to_parquet(precise, index=False)
        reject(precise, "xlsx")
        labels = root / "labels.csv"
        labels.write_text("id,label\n001,NA\n002,NULL\n003,nan\n", encoding="utf-8")
        result = convert(labels, "xlsx")[0]
        got = next(iter(s.read_tables(result).values()))
        assert got["label"].tolist() == ["NA", "NULL", "nan"] and got["id"].tolist() == ["001", "002", "003"]
        unsigned = root / "unsigned.jsonl"
        unsigned.write_text('{"id":18446744073709551615}\n{"id":null}\n', encoding="utf-8")
        assert ids(s.read_tables(unsigned)["data"]) == [2**64 - 1, None]
        assert s.json_frame([{"id": 2**53 + 1}, {"id": .25}])["id"].tolist() == [2**53 + 1, .25]
        print("PASS nullable/big integers, float precision, mixed-array rejection and literal NA text", flush=True)

        grouped = root / "groups.h5"
        with h5py.File(grouped, "w") as h:
            h.attrs["title"] = "calibration"
            h.create_group("empty").attrs["note"] = "retained"
            g = h.create_group("run")
            g.attrs["sample_rate_hz"] = 1234.5
            d = g.create_dataset("signal", data=np.array([1, -2, 3], dtype="int64"))
            d.attrs["units"] = "mV"
        result = convert(grouped, "h5")[0]
        with h5py.File(result) as h:
            assert h["run"].attrs["sample_rate_hz"] == 1234.5 and h["empty"].attrs["note"] == "retained"
            assert h["run/signal"].attrs["units"] == "mV"
            np.testing.assert_array_equal(h["run/signal"][:], [1, -2, 3])
        result = convert(grouped, "npz")[0]
        manifests = [json.loads(file.read_text()) for file in out.glob("*.json")]
        assert any(item.get("source_metadata", {}).get("groups", {}).get("run", {}).get("sample_rate_hz") == 1234.5 for item in manifests)
        for kind in ("soft", "hard", "external"):
            source = root / f"{kind}.h5"
            with h5py.File(source, "w") as h:
                h.create_dataset("data", data=[1, 2])
                h["alias"] = h5py.SoftLink("/data") if kind == "soft" else h5py.ExternalLink("missing.h5", "/data") if kind == "external" else h["data"]
            reject(source, "h5")
        for label, value in (("special", np.array([[np.nan, np.inf], [-np.inf, np.nextafter(1., 2.)]])),
                             ("u64", np.array([[2**63 + 1, 2**64 - 1]], dtype="uint64")),
                             ("complex", np.array([[1 + 2j, 3 - 4j]], dtype="complex128")),
                             ("logical", np.array([[True, False]], dtype=bool))):
            source = root / f"{label}.npy"
            np.save(source, value)
            for ext in ("npy", "npz", "mat", "h5"):
                result = convert(source, ext)[0]
                got = next(iter(s.read_arrays(result)[0].values()))
                np.testing.assert_array_equal(got, value)
                assert got.dtype == value.dtype
        scalar = root / "scalar.npy"
        np.save(scalar, np.array(42, dtype="int64"))
        result = convert(scalar, "mat")[0]
        assert next(iter(s.read_arrays(result)[0].values())).shape == (1, 1)
        packed = root / "packed.h5"
        with h5py.File(packed, "w") as h:
            d = h.create_dataset("signal", data=np.array([65535], dtype="uint16"))
            d.attrs["scale_factor"] = 2
            d.attrs["add_offset"] = 3
        result = convert(packed, "npz")[0]
        assert s.read_arrays(result)[0]["signal"].tolist() == [131073.]
        with h5py.File(packed, "w") as h:
            d = h.create_dataset("signal", data=np.array([2**53 + 1], dtype="int64"))
            d.attrs["scale_factor"] = .5
        reject(packed, "npz")
        indexed = root / "indexed.parquet"
        pd.DataFrame({"value": [1.25, 2.5]}, index=pd.Index(["cell_A", "cell_B"], name="sample")).to_parquet(indexed)
        result = convert(indexed, "csv")[0]
        assert s.read_tables(result)["data"]["sample"].tolist() == ["cell_A", "cell_B"]
        named = root / "metadata.csv"
        named.write_text("value\n1\n2\n", encoding="utf-8")
        assert len(convert(named, "json")) == 1
        assert len(convert(named, "json")) == 1
        print("PASS packing arithmetic, preserved row labels and JSON-sidecar collisions", flush=True)
        print("PASS exact arrays, MAT logical type, HDF5 group attributes, sidecars and blocked links", flush=True)

        pixels = np.arange(2 * 3 * 7 * 9, dtype="float64").reshape(2, 3, 7, 9) / 13
        pixels[0, 0, 0, :3] = [np.nan, np.inf, -np.inf]
        image = root / "float_stack.tiff"
        tifffile.imwrite(image, pixels, photometric="minisblack", metadata={"axes": "TZYX"})
        for ext in ("tiff", "npy", "npz", "h5"):
            result = convert(image, ext)[0]
            if ext == "tiff":
                got = tifffile.imread(result)
            elif ext == "npy":
                got = np.load(result)
            elif ext == "npz":
                with np.load(result) as archive:
                    got = archive["image"]
            else:
                with h5py.File(result) as h:
                    got = h["image"][:]
            np.testing.assert_array_equal(got, pixels)
            assert got.dtype == pixels.dtype
        print("PASS float64 microscopy stacks including non-finite pixels and all dimensions", flush=True)

        fastq = root / "mask.fastq"
        fastq.write_text("@read1 description\naCGt\n+\n!I~J\n", encoding="ascii")
        original = SeqIO.read(fastq, "fastq")
        for ext in ("fastq", "fq", "fasta", "fa"):
            result = convert(fastq, ext)[0]
            got = SeqIO.read(result, "fastq" if ext in ("fastq", "fq") else "fasta")
            assert str(got.seq) == str(original.seq) and got.id == original.id
            if ext in ("fastq", "fq"):
                assert got.letter_annotations == original.letter_annotations
        invalid = SeqRecord(Seq("ACGT"), id="bad", letter_annotations={"phred_quality": [0, 40, 93, 94]})
        real_parse = SeqIO.parse
        def parse(source, format):
            return nullcontext(iter([invalid])) if Path(source) == fastq else real_parse(source, format)
        with patch("Bio.SeqIO.parse", side_effect=parse):
            reject(fastq, "fastq")
        fasta = root / "long.fasta"
        fasta.write_text(">identifier_long_1\nACGT\n>identifier_long_2\nACGA\n", encoding="ascii")
        reject(fasta, "phy")
        sam = root / "quality.sam"
        sam.write_text("@SQ\tSN:chr1\tLN:100\nread\t0\tchr1\t1\t60\t4M\t*\t0\t0\tACGT\tIII" + chr(127) + "\n", encoding="utf-8")
        reject(sam, "fastq")
        from Bio.SeqFeature import SeqFeature, SimpleLocation, CompoundLocation
        annotated = root / "annotated.gb"
        record = SeqRecord(Seq("ACGT" * 20), id="plasmid1", name="plasmid1", description="test plasmid",
                           annotations={"molecule_type": "DNA", "topology": "circular"})
        record.features = [SeqFeature(CompoundLocation([SimpleLocation(70, 80, strand=-1), SimpleLocation(0, 8, strand=-1)]),
                                      type="CDS", qualifiers={"gene": ["abc"], "note": ["functional annotation"], "translation": ["MKK"]})]
        SeqIO.write(record, annotated, "genbank")
        for ext in ("gb", "embl"):
            got = SeqIO.read(convert(annotated, ext)[0], "genbank" if ext == "gb" else "embl")
            assert str(got.seq) == str(record.seq)
            assert got.features[0].location == record.features[0].location
            assert got.features[0].qualifiers == record.features[0].qualifiers
            assert got.annotations["topology"] == "circular"
        print("PASS representative plasmid feature locations, strand, topology and qualifiers", flush=True)
        print("PASS sequence case and quality scores; refuse score clipping and PHYLIP identifier truncation", flush=True)
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        rgba = np.random.default_rng(4).integers(0, 256, (17, 19, 4), dtype="uint8")
        photo = root / "metadata.png"
        metadata = PngInfo()
        metadata.add_text("Acquisition", "calibrated fixture")
        Image.fromarray(rgba).save(photo, pnginfo=metadata, dpi=(300, 300), icc_profile=b"synthetic-icc-fixture")
        with Image.open(convert(photo, "png")[0]) as got, Image.open(photo) as original:
            np.testing.assert_array_equal(np.asarray(got), rgba)
            assert got.info["Acquisition"] == "calibrated fixture"
            assert got.info["icc_profile"] == original.info["icc_profile"] and got.info["dpi"] == original.info["dpi"]
        print("PASS RGBA samples, PNG text, ICC bytes and resolution metadata", flush=True)
        import research_formats as research
        pybel = research.babel()
        for index, smiles in enumerate(("C[C@H](O)C(=O)[O-]", "c1ccccc1", "C[N+](C)(C)C")):
            molecule = pybel.readstring("smi", smiles)
            molecule.make3D(steps=20)
            source = root / f"chemical{index}.sdf"
            molecule.write("sdf", str(source))
            expected = next(pybel.readfile("sdf", str(source))).write("can").split()[0]
            for ext in ("sdf", "mol", "smi", "can"):
                got = next(pybel.readfile(ext, str(convert(source, ext)[0]))).write("can").split()[0]
                assert got == expected, (smiles, ext, got, expected)
        print("PASS representative bond orders, aromaticity, formal charges and stereochemistry in SDF/MOL/SMILES", flush=True)
        import trimesh
        mesh = trimesh.creation.icosphere(subdivisions=1, radius=1.123456789)
        source = root / "geometry.off"
        mesh.export(source)
        for ext in research.MESH_OUTPUTS:
            restored = trimesh.load_scene(convert(source, ext)[0], allow_remote=False).to_mesh()
            assert len(restored.faces) == len(mesh.faces)
            before = mesh.triangles.reshape(-1, 3)
            after = restored.triangles.reshape(-1, 3)
            before = before[np.lexsort(before.T[::-1])]
            after = after[np.lexsort(after.T[::-1])]
            np.testing.assert_allclose(after, before, rtol=1e-6, atol=1e-7)
        print("PASS representative mesh triangle counts and coordinates within float32 tolerance", flush=True)


        # Test the shared CSV writer directly with an integer-valued calibrated signal.
        signal = root / "integer.abf"
        signal.write_bytes(b"generated writer-boundary fixture")
        values = np.array([[2**53 + 1], [2**53 + 3]], dtype="int64")
        def integer_records(source, check):
            yield "signal", values, {"kind": "analog", "units": "counts", "sampling_rate_hz": 2., "t_start_s": .5}
        with patch.object(lab, "records", integer_records):
            for ext in ("csv", "tsv"):
                result = convert(signal, ext)[0]
                with result.open(newline="") as stream:
                    rows = list(csv.reader(stream, delimiter="," if ext == "csv" else "\t"))
                assert rows[1:] == [["0.5", str(2**53 + 1)], ["1.0", str(2**53 + 3)]]
        import neo
        import quantities as pq
        block = neo.Block(name="experiment")
        segment = neo.Segment(name="trial")
        train = neo.SpikeTrain([.2, .4] * pq.s, t_stop=1 * pq.s,
                              waveforms=np.arange(12).reshape(2, 1, 6) * pq.uV,
                              sampling_rate=20000 * pq.Hz, left_sweep=.001 * pq.s)
        segment.spiketrains.append(train)
        block.segments.append(segment)
        reader = SimpleNamespace(support_lazy=False, read=lambda **kwargs: [block])
        items = list(lab.neo_records(reader, lambda: None))
        waveform = next((value, info) for key, value, info in items if info["kind"] == "waveforms")
        assert waveform[1]["left_sweep_s"] == .001 and waveform[1]["sampling_rate_hz"] == 20000
        np.testing.assert_array_equal(waveform[0], train.waveforms.magnitude)
        import mne
        import pyedflib
        raw = mne.io.RawArray(np.sin(np.arange(201))[None, :] * 1e-5,
                             mne.create_info(["EEG"], 100.5, "eeg"), first_samp=1005, verbose="ERROR")
        raw.set_annotations(mne.Annotations([.1234], [.25], ["stimulus"]))
        source = root / "fractional_raw.fif"
        raw.save(source, fmt="double", overwrite=True, verbose="ERROR")
        result = convert(source, "npz")[0]
        with np.load(result) as archive:
            np.testing.assert_array_equal(archive["channel_0000"].T, raw.get_data())
            np.testing.assert_allclose(archive["events"][0], [.1234, .25], atol=1e-12, rtol=0)
        before = set(out.iterdir())
        try:
            result = convert(source, "edf")[0]
        except (ValueError, RuntimeError):
            assert set(out.iterdir()) == before
            refused += 1
        else:
            with pyedflib.EdfReader(str(result)) as reader:
                assert reader.getSampleFrequency(0) == 100.5
                assert reader.getNSamples().tolist() == [201]
                assert reader.readAnnotations()[2].tolist() == ["stimulus"]
        print("PASS integer signal text, spike-waveform timing, EEG start sample, fractional rates and annotations", flush=True)

        ffmpeg = a.imageio_ffmpeg.get_ffmpeg_exe()
        def audio(name, values, sample_format, codec, channels):
            data = root / f"{name}.raw"
            data.write_bytes(values.tobytes())
            source = root / f"{name}.wav"
            a.run_command([ffmpeg, "-v", "error", "-f", sample_format, "-ar", "12000", "-ac", str(channels), "-i", data, "-c:a", codec, source])
            return source
        def decode(source, sample_format, dtype):
            data = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(source), "-map", "0:a:0", "-f", sample_format, "-"],
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return np.frombuffer(data, dtype=dtype)
        values = (np.arange(7200, dtype="int32") - 3600) * 256
        source = audio("six_channel_24bit", values, "s32le", "pcm_s24le", 6)
        for ext in ("wav", "aiff", "au", "flac"):
            result = convert(source, ext)[0]
            np.testing.assert_array_equal(decode(result, "s32le", "<i4"), values)
            info = a.run_command([ffmpeg, "-hide_banner", "-i", result, "-af", "ashowinfo", "-frames:a", "1", "-f", "null", "-"])
            assert re.search(r"channels:6 .*?rate:12000", info)
        for dtype, fmt, codec in (("<f4", "f32le", "pcm_f32le"), ("<f8", "f64le", "pcm_f64le")):
            values = np.array([.1, -.2, np.nextafter(1., 2.), -.12345678901234567] * 100, dtype=dtype)
            source = audio("float" + fmt, values, fmt, codec, 2)
            for ext in ("wav", "aiff", "au"):
                result = convert(source, ext)[0]
                np.testing.assert_array_equal(decode(result, fmt, dtype), values)
            reject(source, "flac")
        values = np.arange(600, dtype="int32") * 10001
        source = audio("integer32", values, "s32le", "pcm_s32le", 1)
        for ext in ("wav", "aiff", "au"):
            np.testing.assert_array_equal(decode(convert(source, ext)[0], "s32le", "<i4"), values)
        reject(source, "flac")
        print("PASS exact PCM24/32 and float32/64 samples, original channel counts and sample rates; refuse lossy FLAC", flush=True)
        print(f"SUCCESS: {conversions} adversarial conversions and {refused} refused-loss checks.", flush=True)


if __name__ == "__main__":
    main()
