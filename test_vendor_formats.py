"""Public instrument fixtures: hash-verified acquisition samples and export fidelity."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import tempfile
import urllib.request

import h5py
import numpy as np
import tifffile
from scipy.io import loadmat
import any2any as a
import imaging_formats as imaging
import lab_signals as lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download missing public fixtures (about 21 MB).")
    args = parser.parse_args()
    cache = a.ROOT / "tools/vendor-fixtures"
    manifest = json.loads((a.ROOT / "fixtures/vendor-samples.json").read_text(encoding="utf-8"))
    for entry in manifest:
        file = cache / entry["name"]
        if not file.exists():
            if not args.download:
                print("SKIP public instrument suite: run test_vendor_formats.py --download first.")
                return
            cache.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(entry["url"], timeout=90) as response:
                data = response.read(entry["size"] + 1)
            assert len(data) == entry["size"] and hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]
            file.write_bytes(data)
        assert file.stat().st_size == entry["size"] and hashlib.sha256(file.read_bytes()).hexdigest() == entry["sha256"], entry["name"]
    conversions = series_count = record_count = sample_count = 0
    for name in ("lif-xz.lif", "lif-wavelength.lif"):
        source = cache / name
        images = list(imaging.read_images(source, lambda: None))
        assert len(images) == 3
        if name == "lif-xz.lif":
            assert [image.shape for image, _, _ in images] == [(20, 2, 128, 128), (23, 2, 128, 128), (2, 512, 512)]
            np.testing.assert_array_equal(images[0][0][0, 0], tifffile.imread(cache / "lif-reference-c0t0.tif"))
            np.testing.assert_array_equal(images[0][0][8, 1], tifffile.imread(cache / "lif-reference-c1t8.tif"))
        else:
            assert [image.shape for image, _, _ in images] == [(20, 1, 64, 64), (15, 1, 64, 64), (2, 10, 11, 1, 64, 64)]
        series_count += len(images)
        for ext in imaging.EXPORTS:
            with tempfile.TemporaryDirectory(prefix="any2any-vendor-") as folder:
                out = Path(folder) / "output"
                results = a.convert(source, ext, out)
                assert all(file.is_file() for file in out.iterdir())
                sidecars = [json.loads(file.read_text(encoding="utf-8")) for file in out.glob("*.json")]
                assert len(sidecars) == len(images) and all(item["leica_xml"] for item in sidecars)
                if ext in ("tiff", "npy", "npz", "h5"):
                    assert len(results) == len(images)
                    for file, (expected, axes, _) in zip(sorted(results), images):
                        if ext == "tiff":
                            with tifffile.TiffFile(file) as image:
                                actual = image.asarray()
                                assert image.series[0].axes == axes
                        elif ext == "npy":
                            actual = np.load(file, allow_pickle=False)
                        elif ext == "npz":
                            with np.load(file, allow_pickle=False) as archive:
                                actual = archive["image"]
                        else:
                            with h5py.File(file) as archive:
                                actual = archive["image"][()]
                        np.testing.assert_array_equal(actual, expected)
                elif ext == "jpg":
                    for sidecar, (expected, _, _) in zip(sorted(sidecars, key=lambda item: item["series_index"]), images):
                        with np.load(out / sidecar["preserved_files"][0]["file"], allow_pickle=False) as archive:
                            np.testing.assert_array_equal(archive["image"], expected)
                else:
                    from PIL import Image
                    planes = [plane for image, axes, _ in images for plane in imaging.planes(image, axes)]
                    assert len(results) == len(planes)
                    for file, expected in zip(sorted(results), planes):
                        with Image.open(file) as image:
                            actual = np.array(image)
                            image.close()
                            if actual.ndim == expected.ndim + 1:
                                expected = np.repeat(expected[..., None], actual.shape[-1], axis=-1)
                            np.testing.assert_array_equal(actual, expected)
                conversions += 1
                print(f"PASS public {name} -> {ext}", flush=True)
    for name in ("abf1-tags.abf", "abf2-four.abf", "spike2.smr", "plexon.plx", "intan.rhd", "nex.nex"):
        source = cache / name
        expected = list(lab.records(source, lambda: None))
        assert expected
        if source.suffix == ".abf":
            try:
                import pyabf
            except ImportError:
                print("SKIP independent pyABF comparison: development-only pyabf is not installed.")
            else:
                abf = pyabf.ABF(str(source))
                analog = {key: (values, info) for key, values, info in expected if info["kind"] == "analog"}
                assert len(analog) == abf.sweepCount * abf.channelCount
                for sweep in range(abf.sweepCount):
                    for channel in range(abf.channelCount):
                        abf.setSweep(sweep, channel=channel)
                        values, info = analog[f"block_000_segment_{sweep:03d}_analog_{channel:04d}"]
                        np.testing.assert_allclose(values[:, 0], abf.sweepY, rtol=8 * np.finfo("float32").eps, atol=1e-6)
                        assert info["sampling_rate_hz"] == abf.dataRate
        record_count += len(expected)
        sample_count += sum(values.size for _, values, _ in expected)
        for ext in lab.EXPORTS:
            with tempfile.TemporaryDirectory(prefix="any2any-vendor-") as folder:
                out = Path(folder) / "output"
                results = a.convert(source, ext, out)
                assert all(file.is_file() for file in out.iterdir())
                metadata_file, = out.glob("*.json")
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                assert set(metadata) == {key for key, _, _ in expected}
                archive = h5py.File(results[0]) if ext == "h5" else np.load(results[0], allow_pickle=False) if ext == "npz" else loadmat(results[0]) if ext == "mat" else None
                try:
                    for key, values, info in expected:
                        assert metadata[key]["kind"] == info["kind"]
                        assert metadata[key]["units"] == info["units"]
                        for field in ("sampling_rate_hz", "t_start_s", "left_sweep_s", "labels"):
                            if field in info:
                                assert metadata[key][field] == info[field]
                        if archive is not None:
                            actual = archive[key][()] if ext == "h5" else archive[key]
                            np.testing.assert_array_equal(actual.reshape(values.shape), values)
                        else:
                            file, = [file for file in results if file.stem.endswith("_" + key)]
                            with file.open(encoding="utf-8", newline="") as stream:
                                rows = list(csv.reader(stream, delimiter="," if ext == "csv" else "\t"))
                            width = int(np.prod(values.shape[1:])) if values.ndim > 1 else 1
                            actual = np.asarray(rows[1:], dtype=float).reshape(len(values), width + (info["kind"] == "analog"))
                            if info["kind"] == "analog":
                                np.testing.assert_array_equal(actual[:, 0], info["t_start_s"] + np.arange(len(values)) / info["sampling_rate_hz"])
                                actual = actual[:, 1:]
                            np.testing.assert_array_equal(actual.reshape(values.shape), values)
                finally:
                    if hasattr(archive, "close"):
                        archive.close()
                conversions += 1
                print(f"PASS public {name} -> {ext}", flush=True)
    for entry in manifest:
        assert hashlib.sha256((cache / entry["name"]).read_bytes()).hexdigest() == entry["sha256"]
    print(f"SUCCESS: {conversions} public instrument conversions; {series_count} image series, {record_count} signal/event/waveform arrays, {sample_count} recording values.", flush=True)


if __name__ == "__main__":
    main()
