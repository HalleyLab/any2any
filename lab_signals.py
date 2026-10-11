"""Calibrated electrophysiology, EEG/LFP and flow-cytometry data exports."""
from pathlib import Path
import csv
import json
import math
import inspect
from contextlib import closing

NEO = {"abf": "AxonIO", "smr": "Spike2IO", "rhd": "IntanIO", "rhs": "IntanIO",
       "plx": "PlexonIO", "nex": "NeuroExplorerIO", "wcp": "WinWcpIO", "edr": "WinEdrIO",
       "trc": "MicromedIO", "ibw": "IgorIO", "pxp": "IgorIO", "axgd": "AxographIO", "axgx": "AxographIO", "nwb": "NWBIO",
       **{f"ns{i}": "BlackrockIO" for i in range(1, 7)}, "nev": "BlackrockIO",
       **{ext: "NeuralynxIO" for ext in ("ncs", "nse", "ntt")},
       **{ext: "OpenEphysIO" for ext in ("continuous", "openephys", "spikes", "events")}}
MNE = {"fif": "fif", "vhdr": "brainvision", "set": "eeglab", "cnt": "cnt", "gdf": "gdf",
       "egi": "egi", "snirf": "snirf", "nedf": "nedf"}
EXPORTS = ["h5", "npz", "mat", "csv", "tsv"]
INPUTS = {"Electrophysiology and EEG": " ".join([*NEO, *MNE, "edf", "bdf"]), "Flow cytometry": "fcs"}
OUTPUTS = {"Electrophysiology and EEG": "h5 npz mat csv tsv edf bdf fif", "Flow cytometry": "csv tsv h5 npz mat"}

def targets(path):
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "nex" and path.is_file():
        with path.open("rb") as stream:
            if stream.read(4) != b"NEX1":
                return []
    if suffix in NEO or suffix in MNE or suffix in ("edf", "bdf"):
        return EXPORTS + (["edf", "bdf"] if suffix in MNE or suffix in ("edf", "bdf") else []) + (["fif"] if suffix in MNE else [])
    if suffix == "fcs":
        return EXPORTS
    return []

def handles(path, ext):
    return ext in targets(path)

def default(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

def materialize(value):
    return value.load() if hasattr(value, "load") else value

def neo_records(reader, check):
    import numpy as np
    kwargs = {"signal_group_mode": "split-all"} if hasattr(reader, "header") else {}
    blocks = reader.read(lazy=reader.support_lazy and type(reader).__name__ != "NWBIO", **kwargs)
    for bi, block in enumerate(blocks):
        for si, segment in enumerate(block.segments):
            for kind, entries in (("analog", segment.analogsignals), ("irregular", segment.irregularlysampledsignals),
                                  ("spikes", segment.spiketrains), ("events", segment.events), ("epochs", segment.epochs)):
                for index, proxy in enumerate(entries):
                    check()
                    obj = proxy.load(load_waveforms=True) if kind == "spikes" and hasattr(proxy, "load") and "load_waveforms" in inspect.signature(proxy.load).parameters else materialize(proxy)
                    key = f"block_{bi:03d}_segment_{si:03d}_{kind}_{index:04d}"
                    meta = {"kind": kind, "name": obj.name, "annotations": obj.annotations,
                            "array_annotations": obj.array_annotations, "block_annotations": block.annotations,
                            "segment_annotations": segment.annotations, "units": str(obj.units)}
                    if kind == "analog":
                        values = obj.magnitude
                        meta.update(sampling_rate_hz=float(obj.sampling_rate.rescale("Hz")), t_start_s=float(obj.t_start.rescale("s")))
                    elif kind == "irregular":
                        values = np.column_stack((obj.times.rescale("s").magnitude, obj.magnitude))
                        meta.update(time_column=0, time_unit="s")
                    else:
                        values = obj.times.rescale("s").magnitude.reshape(-1, 1)
                        meta["units"] = "s"
                        if kind in ("events", "epochs"):
                            meta["labels"] = obj.labels.tolist()
                        if kind == "epochs":
                            values = np.column_stack((values, obj.durations.rescale("s").magnitude))
                        if kind == "spikes":
                            meta.update(t_start_s=float(obj.t_start.rescale("s")), t_stop_s=float(obj.t_stop.rescale("s")))
                            if obj.waveforms is not None:
                                yield key + "_waveforms", obj.waveforms.magnitude, {"kind": "waveforms", "units": str(obj.waveforms.units),
                                                                                  "sampling_rate_hz": float(obj.sampling_rate.rescale("Hz")), "spike_times_key": key}
                    yield key, values, meta

def records(source, check):
    import numpy as np
    suffix = source.suffix.lower().lstrip(".")
    if suffix in ("edf", "bdf"):
        import pyedflib
        with pyedflib.EdfReader(str(source)) as reader:
            header = reader.getHeader()
            onset, duration, labels = reader.readAnnotations()
            if len(onset):
                yield "events", np.column_stack((onset, duration)), {"kind": "events", "units": "s", "labels": labels.tolist()}
            for channel in range(reader.signals_in_file):
                check()
                meta = reader.getSignalHeader(channel)
                meta.update(kind="analog", name=meta["label"], channels=[meta["label"]], units=meta["dimension"],
                            sampling_rate_hz=float(reader.getSampleFrequency(channel)), t_start_s=0., header=header)
                yield f"channel_{channel:04d}", reader.readSignal(channel).reshape(-1, 1), meta
    elif suffix in MNE:
        import mne
        reader = getattr(mne.io, "read_raw_" + MNE[suffix])(source, preload=False, verbose="ERROR")
        try:
            for channel, name in enumerate(reader.ch_names):
                check()
                kind = reader.get_channel_types(picks=[channel])[0]
                unit = {107: "V", 112: "T", 201: "T/m", 6: "mol"}.get(int(reader.info["chs"][channel]["unit"]), "SI or dimensionless; see original_unit_code")
                yield f"channel_{channel:04d}", reader.get_data(picks=[channel]).T, {"kind": "analog", "name": name, "channels": [name],
                    "channel_type": kind, "units": unit, "sampling_rate_hz": float(reader.info["sfreq"]), "t_start_s": 0.,
                    "original_unit_code": int(reader.info["chs"][channel]["unit"]), "first_sample": int(reader.first_samp),
                    "measurement_date": reader.info.get("meas_date"), "bad_channels": reader.info["bads"],
                    "channel_location": reader.info["chs"][channel]["loc"], "description": reader.info.get("description")}
            if len(reader.annotations):
                yield "events", np.column_stack((reader.annotations.onset - reader.first_time, reader.annotations.duration)), {
                    "kind": "events", "units": "s", "labels": reader.annotations.description.tolist(), "orig_time": reader.annotations.orig_time}
        finally:
            reader.close()
    elif suffix == "fcs":
        import flowio
        for index, reader in enumerate(flowio.read_multiple_data_sets(str(source))):
            check()
            values = np.asarray(reader.events).reshape(reader.event_count, reader.channel_count)
            yield f"events_{index:04d}", values, {"kind": "cytometry", "channels": [reader.channels[i].get("PnN", f"channel_{i}") for i in sorted(reader.channels)],
                "channel_metadata": reader.channels, "fcs_text": reader.text,
                "units": "stored values; no compensation, gating or logarithmic transformation applied"}

    else:
        import neo.io
        neuralynx_nev = False
        if suffix == "nev":
            with source.open("rb") as header:
                neuralynx_nev = header.read(8) == b"########"
        cls = neo.io.NeuralynxIO if neuralynx_nev else getattr(neo.io, NEO[suffix])
        if neuralynx_nev or suffix in ("ncs", "nse", "ntt"):
            reader = cls(dirname=str(source.parent), include_filenames=[source.name])
        elif suffix in ("continuous", "openephys", "spikes", "events"):
            reader = cls(dirname=str(source.parent))
        else:
            reader = cls(filename=str(source))
        try:
            yield from neo_records(reader, check)
        finally:
            if hasattr(reader, "close"):
                reader.close()
            elif hasattr(reader, "__del__"):
                reader.__del__()

def export_data(source, ext, folder, check):
    import numpy as np
    import h5py
    from scipy.io import savemat
    arrays, metadata, count = {}, {}, 0
    output = h5py.File(folder / f"{source.stem}.h5", "w") if ext == "h5" else None
    items = records(source, check)
    try:
        for key, values, info in items:
            check()
            count += 1
            values = np.asarray(values)
            metadata[key] = info
            if output is not None:
                dataset = output.create_dataset(key, data=values, chunks=True if values.size else None)
                dataset.attrs["metadata_json"] = json.dumps(info, default=default)
            elif ext in ("npz", "mat"):
                arrays[key] = values
            else:
                # Waveforms retain all dimensions through named sample columns in text exports.
                flat = values.reshape(values.shape[0], -1) if values.ndim > 1 and values.size else values.reshape(len(values), -1 if len(values) else 1)
                target = folder / f"{source.stem}_{key}.{ext}"
                with target.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream, delimiter="," if ext == "csv" else "\t")
                    has_time = info["kind"] == "analog"
                    names = info.get("channels")
                    if not isinstance(names, list) or len(names) != flat.shape[1]:
                        names = [f"value_{index + 1}" for index in range(flat.shape[1])]
                    writer.writerow((["time_s"] if has_time else []) + [str(name) for name in names])
                    for start in range(0, len(flat), 100000):
                        check()
                        chunk = flat[start:start + 100000]
                        if has_time:
                            times = info["t_start_s"] + np.arange(start, start + len(chunk)) / info["sampling_rate_hz"]
                            chunk = np.column_stack((times, chunk))
                        writer.writerows(chunk)
                    if info["kind"] == "waveforms":
                        info["original_shape"] = values.shape
        if not count:
            raise ValueError("No supported signals, events or spike trains were found.")
        encoded = json.dumps(metadata, indent=2, default=default)
        if ext == "npz":
            np.savez(folder / f"{source.stem}.npz", **arrays, metadata_json=np.array(encoded))
        elif ext == "mat":
            savemat(folder / f"{source.stem}.mat", {**arrays, "metadata_json": encoded}, oned_as="column")
        (folder / "metadata.json").write_text(encoded, encoding="utf-8")
    finally:
        items.close()
        if output is not None:
            output.close()

def export_edf(source, ext, folder, check):
    import numpy as np
    import pyedflib
    from pyedflib import highlevel
    samples, headers, metadata = [], [], {}
    annotations = []
    durations = []
    with closing(records(source, check)) as items:
        for key, values, info in items:
            check()
            metadata[key] = info
            if info["kind"] == "events":
                annotations.extend([float(row[0]), float(row[1]) if len(row) > 1 else -1., str(label)] for row, label in zip(values, info["labels"]))
                continue
            if info["kind"] != "analog" or values.shape[1] != 1:
                raise ValueError("EDF/BDF export requires single-channel continuous analog signals.")
            unit = info["units"]
            if unit == "V":
                values, unit = values * 1e6, "uV"
            if len(unit.encode("ascii", errors="strict")) > 8:
                raise ValueError("EDF physical units exceed eight ASCII characters. Use HDF5 or NPZ.")
            signal = values[:, 0]
            if not np.isfinite(signal).all() or not len(signal):
                raise ValueError("EDF/BDF cannot store missing or non-finite samples. Use HDF5 or NPZ.")
            lo, hi = float(signal.min()), float(signal.max())
            if hi <= lo:
                lo, hi = lo - 1., hi + 1.
            # Round outwards to EDF's eight-character physical-range fields.
            magnitude = max(abs(lo), abs(hi), 1.)
            for digits in range(5, 0, -1):
                step = 10 ** (math.floor(math.log10(magnitude)) - digits + 1)
                lower = float(f"{(math.floor(lo / step) - 1) * step:.{digits}g}")
                upper = float(f"{(math.ceil(hi / step) + 1) * step:.{digits}g}")
                if max(len(str(lower)), len(str(upper))) <= 8 and lower < lo and upper > hi:
                    lo, hi = lower, upper
                    break
            else:
                raise ValueError("The physical range does not fit EDF fields. Use HDF5 or NPZ.")
            name = str(info.get("name") or key)
            label = name.encode("ascii", errors="replace").decode()[:16]
            headers.append(highlevel.make_signal_header(label, dimension=unit, sample_frequency=info["sampling_rate_hz"],
                           physical_min=lo, physical_max=hi, digital_min=-32768 if ext == "edf" else -8388608,
                           digital_max=32767 if ext == "edf" else 8388607))
            samples.append(signal)
            durations.append(len(signal) / info["sampling_rate_hz"])
    if not samples or len({header["label"] for header in headers}) != len(headers):
        raise ValueError("EDF/BDF needs unique channel labels after its 16-character limit. Use HDF5 or NPZ.")
    if not np.allclose(durations, durations[0], rtol=0, atol=1e-9) or abs(durations[0] - round(durations[0])) > 1e-9:
        raise ValueError("EDF/BDF export requires equal channel durations in whole seconds to avoid padding. Use HDF5 or NPZ.")
    header = highlevel.make_header()
    header["annotations"] = annotations
    target = folder / f"{source.stem}.{ext}"
    check()
    highlevel.write_edf(str(target), samples, headers, header=header)
    with pyedflib.EdfReader(str(target)) as restored:
        for index, signal in enumerate(samples):
            check()
            tolerance = (restored.getPhysicalMaximum(index) - restored.getPhysicalMinimum(index)) / (restored.getDigitalMaximum(index) - restored.getDigitalMinimum(index)) * 1.1
            if restored.getNSamples()[index] != len(signal) or not np.allclose(restored.readSignal(index), signal, rtol=0, atol=tolerance):
                raise ValueError("EDF/BDF output exceeded its calibration quantization tolerance.")
    metadata["export_note"] = "EDF/BDF quantizes samples; names are ASCII and at most 16 characters. Original metadata is retained here."
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2, default=default), encoding="utf-8")

def convert(source, ext, folder, check):
    if ext in ("edf", "bdf"):
        export_edf(source, ext, folder, check)
    elif ext == "fif":
        import mne
        reader = getattr(mne.io, "read_raw_" + MNE[source.suffix.lower().lstrip(".")])(source, preload=False, verbose="ERROR")
        try:
            check()
            if reader.n_times * len(reader.ch_names) * 8 > 1900000000:
                raise ValueError("FIF output would require linked split files. Use HDF5 for this large recording.")
            reader.save(folder / f"{source.stem}.fif", fmt="double", split_size="2GB", overwrite=False, verbose="ERROR")
            check()
            if len(list(folder.glob("*.fif"))) != 1:
                raise ValueError("Linked split FIF output is not supported. Use HDF5.")
        finally:
            reader.close()
    else:
        export_data(source, ext, folder, check)
    check()
