"""Camera RAW and multidimensional microscopy image export."""
from pathlib import Path
import json
import itertools
from contextlib import closing

RAW = "3fr arw bay cap cr2 cr3 crw dcr dcs dng erf fff iiq k25 kdc mef mos mrw nef nrw orf pef ptx pxn raf raw rdc rw2 rwl sr2 srf srw x3f".split()
MICRO = "czi nd2 lif mrc mrcs map rec stk lsm ims gel scn svs bif ndpi vms vmu".split()
TIFF = ("tif", "tiff")
EXPORTS = "tiff png jpg webp bmp npy npz h5".split()
INPUTS = {"Camera RAW": " ".join(RAW), "Microscopy": " ".join(MICRO)}
OUTPUTS = {"Camera RAW": " ".join(EXPORTS), "Microscopy": " ".join(EXPORTS)}

def targets(path):
    ext = Path(path).suffix.lower().lstrip(".")
    return EXPORTS if ext in RAW + MICRO + list(TIFF) else []

def handles(path, ext):
    return ext in targets(path)

def json_default(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "_asdict"):
        return value._asdict()
    return str(value)

def read_images(source, check):
    import numpy as np
    ext = source.suffix.lower().lstrip(".")
    if ext in RAW:
        import rawpy
        with rawpy.imread(str(source)) as raw:
            check()
            rgb = raw.postprocess(use_camera_wb=True, output_bps=16)
            metadata = {"decoder": "LibRaw", "libraw_version": rawpy.libraw_version,
                        "rendering": "Demosaiced sRGB, camera white balance, 16-bit; not raw sensor values.",
                        "black_level_per_channel": raw.black_level_per_channel, "white_level": raw.white_level}
            yield rgb, "YXS", metadata
    elif ext == "nd2":
        import nd2
        with nd2.ND2File(source) as image:
            check()
            yield image.asarray(), "".join(image.sizes), {"voxel_size_um": image.voxel_size(),
                                                          "metadata": image.metadata, "sizes": image.sizes}
    elif ext == "czi":
        import czifile
        with czifile.CziFile(source) as image:
            check()
            for scene_index, scene in image.scenes.items():
                check()
                yield scene.asarray(), "".join(scene.dims), {"scene": scene_index, "zeiss_xml": image.metadata(),
                    "coord_scales": scene.coord_scales, "coord_units": scene.coord_units, "channels": scene.channels}
    elif ext == "lif":
        from readlif.reader import LifFile
        image_file = LifFile(str(source))
        for image in image_file.get_iter_image():
            check()
            shape = (image.dims.m, image.dims.t, image.dims.z, image.channels, image.dims.y, image.dims.x)
            frames = []
            for m, t, z, c in itertools.product(*(range(dim) for dim in shape[:4])):
                check()
                frames.append(np.asarray(image.get_frame(z=z, t=t, c=c, m=m)))
            yield np.stack(frames).reshape(shape), "PTZCYX", {"name": image.name, "scale": image.scale,
                                                             "scale_units": "pixels per micrometer; time scale per second", "bit_depth": image.bit_depth}
    elif ext in ("mrc", "mrcs", "map", "rec"):
        import mrcfile
        with mrcfile.open(source, permissive=False) as image:
            check()
            data = image.data.copy()
            yield data, "ZYX" if data.ndim == 3 else "YX", {"voxel_size_angstrom": image.voxel_size.tolist(),
                                                           "origin": image.header.origin.tolist(), "header": str(image.header)}
    elif ext == "ims":
        import h5py
        with h5py.File(source, "r") as image:
            root = image["DataSet/ResolutionLevel 0"]
            times = sorted(root, key=lambda key: int(key.split()[-1]))
            channels = sorted(root[times[0]], key=lambda key: int(key.split()[-1]))
            shape = root[times[0]][channels[0]]["Data"].shape
            data = np.stack([root[t][c]["Data"][()] for t in times for c in channels]).reshape(len(times), len(channels), *shape)
            yield data, "TCZYX", {"imaris_info": {key: dict(group.attrs) for key, group in image.get("DataSetInfo", {}).items()}}
    else:
        import tifffile
        with tifffile.TiffFile(source) as image:
            for series in image.series:
                check()
                yield series.asarray(), series.axes, {"description": series.pages[0].description,
                                                     "ome_xml": image.ome_metadata, "lsm_metadata": image.lsm_metadata,
                                                     "resolution": {tag: series.pages[0].tags[tag].value for tag in ("XResolution", "YResolution", "ResolutionUnit") if tag in series.pages[0].tags}}

def planes(data, axes):
    import numpy as np
    if data.ndim != len(axes) or "Y" not in axes or "X" not in axes:
        raise ValueError(f"Cannot identify image axes: {axes}, shape {data.shape}.")
    rgb = "S" in axes and data.shape[axes.index("S")] in (3, 4)
    end = [axes.index("Y"), axes.index("X")] + ([axes.index("S")] if rgb else [])
    start = [index for index in range(data.ndim) if index not in end]
    ordered = np.transpose(data, start + end)
    for index in np.ndindex(ordered.shape[:len(start)]):
        yield ordered[index]

def preview(data, limits):
    import numpy as np
    if data.dtype == np.uint8:
        return data
    low, high = limits
    scaled = (data.astype(np.float64) - low) / (high - low) if high > low else np.zeros(data.shape)
    return np.rint(np.clip(np.nan_to_num(scaled), 0, 1) * 255).astype(np.uint8)

def convert(source, ext, folder, check):
    import numpy as np
    import tifffile
    from PIL import Image
    count = 0
    with closing(read_images(source, check)) as images:
        for count, (data, axes, metadata) in enumerate(images, 1):
            check()
            if not data.size or data.dtype.kind not in "buif":
                raise ValueError("Only non-empty real numeric image arrays can be exported.")
            stem = f"{source.stem}_{count:04d}"
            metadata.update(axes=axes, shape=data.shape, dtype=str(data.dtype), source_format=source.suffix, series_index=count)
            target = folder / f"{stem}.{ext}"
            if ext == "tiff":
                # Preserve the full array; a shaped TIFF supports axes beyond OME's five dimensions.
                tifffile.imwrite(target, data, photometric="rgb" if axes.endswith("YXS") and data.shape[-1] in (3, 4) else "minisblack",
                                 metadata={"axes": axes}, bigtiff=data.nbytes > 2**32 - 2**25)
                with tifffile.TiffFile(target) as restored:
                    if restored.series[0].shape != data.shape or restored.series[0].dtype != data.dtype:
                        raise ValueError("TIFF output changed the image dimensions or bit depth.")
            elif ext == "npy":
                np.save(target, data, allow_pickle=False)
            elif ext == "npz":
                np.savez(target, image=data, metadata_json=np.array(json.dumps(metadata, default=json_default)))
            elif ext == "h5":
                import h5py
                with h5py.File(target, "w") as output:
                    dataset = output.create_dataset("image", data=data, chunks=True)
                    dataset.attrs["axes"] = axes
                    dataset.attrs["metadata_json"] = json.dumps(metadata, default=json_default)
            else:
                low, high = float("inf"), float("-inf")
                flattened = data.reshape(-1)
                for start in range(0, data.size, 1000000):
                    check()
                    chunk = flattened[start:start + 1000000]
                    finite = chunk[np.isfinite(chunk)]
                    if finite.size:
                        low, high = min(low, float(finite.min())), max(high, float(finite.max()))
                limits = (low, high) if low <= high else (0., 0.)
                metadata["preview_range"] = limits
                for number, plane in enumerate(planes(data, axes), 1):
                    check()
                    result = folder / f"{stem}_{number:04d}.{ext}"
                    if ext == "png" and plane.dtype in (np.dtype("uint8"), np.dtype("uint16")):
                        import imagecodecs
                        result.write_bytes(imagecodecs.png_encode(np.ascontiguousarray(plane)))
                        if not np.array_equal(imagecodecs.png_decode(result.read_bytes()), plane):
                            raise ValueError("PNG output changed the image samples.")
                    else:
                        image = Image.fromarray(preview(plane, limits))
                        if ext in ("jpg", "bmp") and image.mode == "RGBA":
                            image = image.convert("RGB")
                        image.save(result, **({"quality": 95} if ext in ("jpg", "webp") else {}))
                        with Image.open(result) as restored:
                            restored.load()
            (folder / f"{stem}.json").write_text(json.dumps(metadata, indent=2, default=json_default), encoding="utf-8")
            check()
    if not count:
        raise ValueError("No image series were found.")
