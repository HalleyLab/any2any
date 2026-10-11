"""Scientific tables and numeric arrays. Imports stay lazy to keep the GUI small and fast."""
from pathlib import Path
from contextlib import closing
import csv
import json
import re
import sqlite3
import xml.etree.ElementTree as ET

ARRAYS = "npy npz mat h5 hdf5 hdf nc nc4 netcdf".split()
TABLES = "csv tsv dat asc xlsx parquet pq feather arrow json jsonl ndjson sav zsav por dta xpt rds rda rdata sqlite sqlite3 db".split()
READ_ONLY = "sas7bdat pzfx".split()
OFFICE = "xls xlsm xlsb ods fods".split()
INPUTS = {"Scientific data": " ".join(dict.fromkeys(ARRAYS + TABLES + READ_ONLY))}
OUTPUTS = {"Scientific data": " ".join(ARRAYS + TABLES)}

def targets(path):
    suffix = Path(path).suffix.lower().lstrip(".")
    return ARRAYS + TABLES if suffix in ARRAYS + TABLES + READ_ONLY + OFFICE else []

def handles(path, ext):
    suffix = Path(path).suffix.lower().lstrip(".")
    if ext not in targets(path):
        return False
    if suffix in OFFICE + ["xlsx"] and ext == "xlsx":
        return False
    return True


def needs_office(source):
    ext = source.suffix.lower().lstrip(".")
    if ext in OFFICE:
        return True
    if ext == "xlsx":
        import zipfile
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    with archive.open(name) as sheet:
                        for _, element in ET.iterparse(sheet, events=("end",)):
                            if element.tag.rsplit("}", 1)[-1] == "f":
                                return True
                            element.clear()
    return False


def checked_array(value):
    import numpy as np
    value = np.asanyarray(value)
    if value.dtype.kind == "O" and all(isinstance(item, str) for item in value.flat):
        value = value.astype(str)
    if value.dtype.kind not in "biufcSU":
        raise ValueError("Only numeric, boolean and text arrays are supported; objects, structs and references need a specialist exporter.")
    return value

def read_arrays(source):
    import numpy as np
    ext = source.suffix.lower().lstrip(".")
    metadata = {"attrs": {}, "variables": {}, "groups": {}}
    if ext == "npy":
        arrays = {"data": np.load(source, allow_pickle=False)}
    elif ext == "npz":
        with np.load(source, allow_pickle=False) as archive:
            if len(archive.files) != len(set(archive.files)):
                raise ValueError("NPZ contains duplicate array names; no values were discarded.")
            arrays = {name: archive[name] for name in archive.files}
    elif ext in ("nc", "nc4", "netcdf"):
        import netCDF4
        arrays = {}
        with netCDF4.Dataset(source) as dataset:
            if dataset.groups:
                raise ValueError("Grouped NetCDF data needs a specialist exporter; no groups were discarded.")
            metadata["attrs"] = {key: dataset.getncattr(key) for key in dataset.ncattrs()}
            for name, variable in dataset.variables.items():
                variable.set_auto_maskandscale(False)
                arrays[name] = variable[...]
                metadata["variables"][name] = {
                    "attrs": {key: variable.getncattr(key) for key in variable.ncattrs()},
                    "dims": variable.dimensions,
                }
    else:
        import h5py
        if ext == "mat" and not h5py.is_hdf5(source):
            from scipy.io import loadmat, whosmat
            logical = {key for key, _, kind in whosmat(source) if kind == "logical"}
            arrays = {key: value.astype(bool) if key in logical else value
                      for key, value in loadmat(source).items() if not key.startswith("__")}
        else:
            arrays = {}
            with h5py.File(source, "r") as dataset:
                metadata["attrs"] = dict(dataset.attrs)
                def visit(name, item):
                    if isinstance(item, h5py.Group):
                        metadata["groups"][name] = dict(item.attrs)
                    if isinstance(item, h5py.Dataset):
                        if name.startswith("#refs#"):
                            raise ValueError("MATLAB cell/reference arrays need a specialist exporter.")
                        strings = h5py.check_string_dtype(item.dtype)
                        value = np.asarray(item.asstr()[()], dtype=str) if strings and strings.encoding == "utf-8" and strings.length is None else item[()]
                        if ext == "mat" and "MATLAB_class" in item.attrs:
                            if item.attrs["MATLAB_class"] in (b"cell", b"struct", b"char"):
                                raise ValueError("MATLAB v7.3 cells, structs and characters are not supported.")
                            value = np.transpose(value)
                        arrays[name] = value
                        attrs = dict(item.attrs)
                        dims = attrs.pop("__any2any_dims__", None)
                        metadata["variables"][name] = {"attrs": attrs}
                        if dims is not None:
                            metadata["variables"][name]["dims"] = json.loads(dims)
                seen = set()
                def check_link(name, link):
                    if not isinstance(link, h5py.HardLink):
                        return "HDF5 soft/external links need a specialist exporter; no links were discarded."
                    address = h5py.h5o.get_info(dataset[name].id).addr
                    if address in seen:
                        return "HDF5 hard-link aliases need a specialist exporter; no aliases were discarded."
                    seen.add(address)
                issue = dataset.visititems_links(check_link)
                if issue:
                    raise ValueError(issue)
                dataset.visititems(visit)
    if not arrays:
        raise ValueError("No supported arrays were found.")
    return {key: checked_array(value) for key, value in arrays.items()}, metadata

def write_arrays(arrays, metadata, ext, folder, stem, check):
    import numpy as np
    arrays = {key: checked_array(value) for key, value in arrays.items()}
    target = folder / f"{stem}.{ext}"
    if ext == "npy":
        for index, (name, value) in enumerate(arrays.items(), 1):
            check()
            path = target if len(arrays) == 1 else folder / f"{stem}_{index:04d}_{safe_name(name)}.npy"
            np.save(path, value, allow_pickle=False)
    elif ext == "npz":
        import zipfile
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, value in arrays.items():
                check()
                if "\x00" in name:
                    raise ValueError("NPZ array names cannot contain a null character.")
                with archive.open(name + ".npy", "w", force_zip64=True) as stream:
                    np.lib.format.write_array(stream, value, allow_pickle=False)
    elif ext == "mat":
        from scipy.io import savemat
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", key) for key in arrays):
            raise ValueError("MATLAB variable names must start with a letter and contain only letters, digits and underscores. Use NPZ or HDF5 for other names.")
        savemat(target, arrays, appendmat=False, long_field_names=True, oned_as="column")
    elif ext in ("nc", "nc4", "netcdf"):
        import netCDF4
        with netCDF4.Dataset(target, "w", format="NETCDF4") as dataset:
            for key, value in metadata.get("attrs", {}).items():
                if key not in ("_NCProperties",):
                    dataset.setncattr(key, value)
            for index, (name, value) in enumerate(arrays.items()):
                check()
                if "/" in name or value.dtype.kind in "cS":
                    raise ValueError("NetCDF output supports flat names and real numeric or Unicode arrays. Use HDF5/NPZ for this data.")
                info = metadata.get("variables", {}).get(name, {})
                dims = info.get("dims", [f"v{index}_d{axis}" for axis in range(value.ndim)])
                for dim, size in zip(dims, value.shape):
                    if dim not in dataset.dimensions:
                        dataset.createDimension(dim, size)
                    elif len(dataset.dimensions[dim]) != size:
                        raise ValueError("Conflicting NetCDF dimension sizes.")
                attrs = dict(info.get("attrs", {}))
                fill = attrs.pop("_FillValue", None)
                dtype = str if value.dtype.kind == "U" else ("i1" if value.dtype.kind == "b" else "f4" if value.dtype == np.float16 else value.dtype)
                variable = dataset.createVariable(name, dtype, dims, fill_value=fill)
                variable.set_auto_maskandscale(False)
                variable[...] = value
                for key, attr in attrs.items():
                    variable.setncattr(key, attr)
    else:
        import h5py
        with h5py.File(target, "w") as dataset:
            for key, value in metadata.get("attrs", {}).items():
                dataset.attrs[key] = value
            for name, attrs in metadata.get("groups", {}).items():
                group = dataset.require_group(name)
                for key, value in attrs.items():
                    group.attrs[key] = value
            for name, value in arrays.items():
                check()
                data = value.astype(object) if value.dtype.kind == "U" else value
                dtype = h5py.string_dtype("utf-8") if value.dtype.kind == "U" else None
                variable = dataset.create_dataset(name, data=data, dtype=dtype)
                info = metadata.get("variables", {}).get(name, {})
                for key, attr in info.get("attrs", {}).items():
                    if key not in ("DIMENSION_LIST", "REFERENCE_LIST"):
                        variable.attrs[key] = attr
                if "dims" in info:
                    variable.attrs["__any2any_dims__"] = json.dumps(list(info["dims"]))

    if ext == "npy":
        restored = {}
        for index, (name, value) in enumerate(arrays.items(), 1):
            path = target if len(arrays) == 1 else folder / f"{stem}_{index:04d}_{safe_name(name)}.npy"
            restored[name] = np.load(path, allow_pickle=False)
    else:
        restored, _ = read_arrays(target)
    if set(restored) != set(arrays):
        raise ValueError("Array output changed variable names or counts.")
    for name, value in arrays.items():
        check()
        actual = restored[name]
        shape_ok = actual.shape == value.shape or (ext == "mat" and value.ndim <= 1 and actual.size == value.size)
        kind_ok = actual.dtype.kind == value.dtype.kind or (ext in ("nc", "nc4", "netcdf") and value.dtype.kind == "b" and actual.dtype.kind == "i")
        values_ok = False
        if shape_ok:
            actual = actual.reshape(value.shape)
            components = ((actual.real, value.real), (actual.imag, value.imag)) if value.dtype.kind == "c" else ((actual, value),)
            values_ok = all(np.array_equal(before, after, equal_nan=before.dtype.kind == "f") and
                (before.dtype.kind != "f" or np.array_equal(np.signbit(before[before == 0]), np.signbit(after[before == 0])))
                for before, after in components)
        if not shape_ok or not kind_ok or not values_ok:
            raise ValueError("Array output changed samples, strings or dimensions. Use NPY/NPZ/HDF5 for this data.")


def unpack_arrays(arrays, metadata):
    import numpy as np
    result = {}
    for name, value in arrays.items():
        attrs = metadata.get("variables", {}).get(name, {}).get("attrs", {})
        mask = np.zeros(value.shape, dtype=bool)
        for key in ("_FillValue", "missing_value"):
            if key in attrs:
                mask |= np.isin(value, np.atleast_1d(attrs[key]))
        if value.dtype.kind in "biufc":
            if str(attrs.get("_Unsigned", "")).lower() == "true" and value.dtype.kind == "i":
                value = value.view(np.dtype(value.dtype.str.replace("i", "u")))
            packed = "scale_factor" in attrs or "add_offset" in attrs
            if (mask.any() or packed) and value.dtype.kind in "iu" and (np.abs(value.astype(object)) > 2**53).any():
                raise ValueError("Packing/missing-value export would lose precision in large integers. Keep NetCDF or HDF5.")
            if packed:
                value = value.astype(np.result_type(value.dtype, np.float64))
            if "scale_factor" in attrs:
                value = value * attrs["scale_factor"]
            if "add_offset" in attrs:
                value = value + attrs["add_offset"]
            if mask.any():
                value = value.astype(complex if value.dtype.kind == "c" else float)
                value[mask] = np.nan
        result[name] = value
    return result


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:48] or "data"

def read_delimited(source, ext):
    import pandas as pd
    sep = "\t" if ext in ("tsv", "dat", "asc") else ","
    with source.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        if ext in ("dat", "asc"):
            try:
                sep = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
            except csv.Error:
                sep = r"\s+" if any(" " in line.strip() for line in sample.splitlines()[:2]) else "\t"
        stream.seek(0)
        first = re.split(r"\s+", stream.readline().strip()) if sep == r"\s+" else next(csv.reader(stream, delimiter=sep), [])
    header = "infer"
    if first:
        try:
            for value in first:
                float(value)
            header = None
        except ValueError:
            pass
    if header is not None and len(first) != len(set(first)):
        raise ValueError("Delimited input has duplicate column names; no columns were renamed or discarded.")
    frame = pd.read_csv(source, sep=sep, engine="python" if sep == r"\s+" else "c",
                        header=header, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if header is None:
        frame.columns = [f"column_{index + 1}" for index in range(len(frame.columns))]
    for column in frame:
        values = frame[column]
        if values.str.match(r"^[+-]?0\d+").any():
            continue
        present = values[values != ""]
        if len(present) and present.str.fullmatch(r"[+-]?\d+").all():
            integers = [int(value) for value in present]
            if min(integers) >= -(2**63) and max(integers) < 2**63:
                frame[column] = pd.array(values.replace("", None), dtype="Int64")
            elif min(integers) >= 0 and max(integers) < 2**64:
                frame[column] = pd.array(values.replace("", None), dtype="UInt64")
            continue
        try:
            numeric = pd.to_numeric(values.replace("", None), errors="raise")
            if pd.api.types.is_float_dtype(numeric.dtype):
                converted = values.replace("", None).to_numpy(dtype=float)
                if any(re.fullmatch(r"[+-]?\d+", raw) and int(raw) != float(value)
                       for raw, value in zip(values, converted)):
                    continue
                frame[column] = converted
            else:
                frame[column] = numeric
        except (ValueError, TypeError):
            pass
    return frame

def read_prism(source):
    import pandas as pd
    tree = ET.parse(source)
    result = {}
    for index, table in enumerate(tree.getroot().iter()):
        tag = table.tag.rsplit("}", 1)[-1]
        if tag not in ("Table", "HugeTable"):
            continue
        columns = {}
        for number, column in enumerate(table):
            if column.tag.rsplit("}", 1)[-1] not in ("XColumn", "YColumn", "RowTitlesColumn"):
                continue
            title = next(("".join(item.itertext()) for item in column if item.tag.rsplit("}", 1)[-1] == "Title"), f"column_{number}")
            subcolumns = [item for item in column if item.tag.rsplit("}", 1)[-1] == "Subcolumn"]
            for subindex, sub in enumerate(subcolumns):
                name = f"{number}_{title}_{subindex + 1}"
                columns[name] = pd.Series(["".join(item.itertext()) or None for item in sub])
        if columns:
            title = next(("".join(item.itertext()) for item in table if item.tag.rsplit("}", 1)[-1] == "Title"), f"table_{index}")
            key = f"{len(result) + 1}_{title}"
            result[key] = pd.DataFrame(columns)
    if not result:
        raise ValueError("No Prism data tables were found. Binary Prism projects are not supported.")
    return result

def json_frame(data):
    import numpy as np
    import pandas as pd
    frame = pd.DataFrame(data, dtype=object)
    for column in frame:
        values = frame[column].tolist()
        present = [value for value in values if value is not None]
        if not present:
            continue
        if all(isinstance(value, bool) for value in present):
            frame[column] = pd.array(values, dtype="boolean")
        elif all(isinstance(value, int) and not isinstance(value, bool) for value in present):
            if min(present) >= -(2**63) and max(present) < 2**63:
                frame[column] = pd.array(values, dtype="Int64")
            elif min(present) >= 0 and max(present) < 2**64:
                frame[column] = pd.array(values, dtype="UInt64")
        elif all(isinstance(value, (int, float)) for value in present):
            converted = np.array([np.nan if value is None else value for value in values], dtype=float)
            if all(before is None or before == float(after) for before, after in zip(values, converted)):
                frame[column] = pd.array(converted, dtype="Float64")
    return frame


def read_tables(source):
    import pandas as pd
    ext = source.suffix.lower().lstrip(".")
    if ext in ("csv", "tsv", "dat", "asc"):
        result = {"data": read_delimited(source, ext)}
    elif ext == "xlsx":
        result = {name: frame.infer_objects() for name, frame in pd.read_excel(source, sheet_name=None, engine="openpyxl", dtype=object, keep_default_na=False).items()}
    elif ext in ("parquet", "pq"):
        result = {"data": pd.read_parquet(source)}
    elif ext in ("feather", "arrow"):
        result = {"data": pd.read_feather(source)}
    elif ext in ("json", "jsonl", "ndjson"):
        if ext == "json":
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "schema" in data and "data" in data:
                from pandas.io.json._table_schema import convert_json_field_to_pandas_type
                fields = data["schema"]["fields"]
                frame = pd.DataFrame(data["data"], columns=[field["name"] for field in fields], dtype=object)
                for field in fields:
                    dtype = convert_json_field_to_pandas_type(field)
                    if field["type"] == "datetime":
                        frame[field["name"]] = pd.to_datetime(frame[field["name"]], utc=bool(field.get("tz"))).astype(dtype)
                    else:
                        frame[field["name"]] = frame[field["name"]].astype(dtype)
                result = {"data": frame}
            else:
                result = {"data": json_frame(data)}
        else:
            data = [json.loads(line) for line in source.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            result = {"data": json_frame(data)}
    elif ext in ("sav", "zsav", "por", "dta", "xpt", "sas7bdat"):
        import pyreadstat
        reader = {"sav": pyreadstat.read_sav, "zsav": pyreadstat.read_sav, "por": pyreadstat.read_por,
                  "dta": pyreadstat.read_dta, "xpt": pyreadstat.read_xport, "sas7bdat": pyreadstat.read_sas7bdat}[ext]
        frame, meta = reader(str(source), apply_value_formats=False, user_missing=True) if ext in ("sav", "zsav", "dta") else reader(str(source))
        frame.attrs["column_labels"] = meta.column_names_to_labels
        frame.attrs["value_labels"] = meta.variable_value_labels
        frame.attrs["missing_ranges"] = meta.missing_ranges
        frame.attrs["missing_user_values"] = meta.missing_user_values
        frame.attrs["file_label"] = meta.file_label or ""
        result = {"data": frame}
    elif ext in ("rds", "rda", "rdata"):
        import pyreadr
        result = {str(key or "data"): frame for key, frame in pyreadr.read_r(str(source)).items()}
    elif ext in ("sqlite", "sqlite3", "db"):
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            result = {name: pd.read_sql_query('SELECT * FROM "' + name.replace('"', '""') + '"', connection, dtype_backend="numpy_nullable") for name in names}
    elif ext == "pzfx":
        result = read_prism(source)
    else:
        raise ValueError("Unsupported scientific table input.")
    if not result or any(not isinstance(frame, pd.DataFrame) or len(frame.columns) == 0 for frame in result.values()):
        raise ValueError("No supported rectangular data tables were found.")
    for name, frame in result.items():
        if frame.index.name is not None or not frame.index.equals(pd.RangeIndex(len(frame))):
            result[name] = frame.reset_index()
    return result

def write_tables(tables, ext, folder, stem, check):
    import pandas as pd
    target = folder / f"{stem}.{ext}"
    if ext == "xlsx":
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            for index, (name, frame) in enumerate(tables.items(), 1):
                check()
                sheet = re.sub(r"[\[\]:*?/\\]", "_", str(name))[:25]
                sheet_name = f"{index}_{sheet}"
                frame.to_excel(writer, sheet_name=sheet_name, index=False)
                for row in writer.sheets[sheet_name].iter_rows():
                    for cell in row:
                        if cell.data_type == "f":
                            cell.data_type = "s"
        restored = read_tables(target)
        for expected, actual in zip(tables.values(), restored.values()):
            try:
                pd.testing.assert_frame_equal(expected.reset_index(drop=True), actual.reset_index(drop=True),
                                              check_dtype=False, check_exact=True, check_names=False)
            except AssertionError as error:
                raise ValueError("Excel output changed table values or precision. Use Parquet or HDF5 instead.") from error
        return
    if ext in ("sqlite", "sqlite3", "db"):
        with closing(sqlite3.connect(target)) as connection:
            for index, (name, frame) in enumerate(tables.items(), 1):
                check()
                frame.to_sql(str(name), connection, index=False, if_exists="fail")
        return
    for index, (name, frame) in enumerate(tables.items(), 1):
        check()
        path = target if len(tables) == 1 else folder / f"{stem}_{index:04d}_{safe_name(name)}.{ext}"
        if ext in ("csv", "tsv", "dat", "asc"):
            frame.to_csv(path, sep="," if ext == "csv" else "\t", index=False, encoding="utf-8-sig")
        elif ext in ("json", "jsonl", "ndjson"):
            from pandas.io.json import build_table_schema
            records = frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
            def encode(value):
                if hasattr(value, "isoformat"):
                    return value.isoformat()
                raise TypeError("This table value cannot be represented in JSON.")
            if ext == "json":
                content = json.dumps({"schema": build_table_schema(frame, index=False), "data": records},
                                     ensure_ascii=False, allow_nan=False, default=encode)
            else:
                content = "\n".join(json.dumps(row, ensure_ascii=False, allow_nan=False, default=encode) for row in records) + "\n"
            path.write_text(content, encoding="utf-8")
        elif ext in ("parquet", "pq"):
            frame.to_parquet(path, index=False)
        elif ext in ("feather", "arrow"):
            frame.reset_index(drop=True).to_feather(path)
        elif ext in ("sav", "zsav", "por", "dta", "xpt"):
            import pyreadstat
            data = frame.copy()
            for column in data:
                if pd.api.types.is_integer_dtype(data[column]) and (data[column].dropna().abs() > 2**53).any():
                    raise ValueError("Statistical exports cannot exactly preserve integers above 2^53. Use Parquet or an array format.")
                if pd.api.types.is_string_dtype(data[column]):
                    data[column] = data[column].astype(object).where(data[column].notna(), None)
            labels = frame.attrs.get("column_labels")
            if ext in ("sav", "zsav"):
                pyreadstat.write_sav(data, str(path), compress=ext == "zsav", column_labels=labels,
                                    variable_value_labels=frame.attrs.get("value_labels"),
                                    missing_ranges=frame.attrs.get("missing_ranges"), file_label=frame.attrs.get("file_label", ""))
            elif ext == "dta":
                pyreadstat.write_dta(data, str(path), column_labels=labels, variable_value_labels=frame.attrs.get("value_labels"),
                                    missing_user_values=frame.attrs.get("missing_user_values"), file_label=frame.attrs.get("file_label", ""))
            elif ext == "por":
                pyreadstat.write_por(data, str(path), column_labels=labels)
            else:
                pyreadstat.write_xport(data, str(path), column_labels=labels, file_format_version=8)
        elif ext in ("rds", "rda", "rdata"):
            import pyreadr
            for column in frame:
                if pd.api.types.is_integer_dtype(frame[column]) and (frame[column].dropna().abs() > 2**53).any():
                    raise ValueError("R data-frame exports cannot exactly preserve integers above 2^53. Use Parquet or an array format.")
            if ext == "rds":
                pyreadr.write_rds(str(path), frame)
            else:
                pyreadr.write_rdata(str(path), frame, df_name=safe_name(name))
        else:
            raise ValueError("Unsupported scientific table output.")

def convert(source, ext, folder, check):
    import numpy as np
    import pandas as pd
    src_ext = source.suffix.lower().lstrip(".")
    check()
    if src_ext in ARRAYS:
        arrays, metadata = read_arrays(source)
        manifest = {"source_metadata": metadata, "arrays": {name: {"shape": value.shape, "dtype": str(value.dtype)}
                    for name, value in arrays.items()}, "note": "Non-HDF5/NetCDF exports unpack scale/offset and missing values; MAT uses column vectors."}
        if ext not in ("h5", "hdf5", "hdf", "nc", "nc4", "netcdf"):
            arrays = unpack_arrays(arrays, metadata)
        if ext in ARRAYS:
            write_arrays(arrays, metadata, ext, folder, source.stem, check)
        else:
            tables = {}
            for name, value in arrays.items():
                if value.ndim > 2 or value.dtype.kind == "c":
                    raise ValueError("Tables cannot preserve arrays above two dimensions or complex numbers. Use NPZ, MAT or HDF5.")
                frame = pd.DataFrame(np.atleast_1d(value))
                frame.columns = [f"column_{index + 1}" for index in range(len(frame.columns))]
                tables[name] = frame
            write_tables(tables, ext, folder, source.stem, check)
    else:
        tables = read_tables(source)
        if any(not frame.columns.is_unique for frame in tables.values()):
            raise ValueError("Duplicate table columns cannot be exported safely.")
        manifest = {"tables": {name: {"columns": list(frame.columns), "dtypes": [str(dtype) for dtype in frame.dtypes],
                                     "attrs": frame.attrs} for name, frame in tables.items()}}
        if ext in ARRAYS:
            arrays = {}
            for name, frame in tables.items():
                if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
                    raise ValueError("Array exports require numeric table columns. Use Parquet, Excel or statistical formats for mixed data.")
                dtype = np.result_type(*[getattr(dtype, "numpy_dtype", dtype) for dtype in frame.dtypes])
                if frame.isna().any().any() and dtype.kind in "biu":
                    dtype = np.dtype("float64")
                values = frame.to_numpy(dtype=dtype, na_value=np.nan)
                for index, column in enumerate(frame):
                    if any(before != after for before, after in zip(frame[column].dropna().tolist(),
                           values[frame[column].notna().to_numpy(), index].tolist())):
                        raise ValueError("Combining these columns would lose numeric precision. Use Parquet or separate arrays.")
                arrays[name] = values
            write_arrays(arrays, {}, ext, folder, source.stem, check)
        else:
            write_tables(tables, ext, folder, source.stem, check)
    if ext not in ARRAYS:
        files = [folder / f"{source.stem}.{ext}"] if ext in ("xlsx", "sqlite", "sqlite3", "db") or len(tables) == 1 else [
            folder / f"{source.stem}_{index:04d}_{safe_name(name)}.{ext}" for index, name in enumerate(tables, 1)]
        restored_tables = [frame for file in files for frame in read_tables(file).values()]
        if len(restored_tables) != len(tables):
            raise ValueError("Table output changed the number of tables.")
        manifest["preserved_files"] = []
        for index, ((name, frame), restored) in enumerate(zip(tables.items(), restored_tables), 1):
            check()
            try:
                pd.testing.assert_frame_equal(frame.reset_index(drop=True), restored.reset_index(drop=True), check_exact=True)
            except AssertionError:
                backup = folder / f"preserved_table_{index:04d}.parquet"
                while backup.exists():
                    backup = backup.with_stem(backup.stem + "_data")
                exact = frame.copy(deep=False)
                exact.attrs = {}
                exact.to_parquet(backup, index=False)
                pd.testing.assert_frame_equal(exact, pd.read_parquet(backup), check_exact=True)
                manifest["preserved_files"].append({"file": backup.name, "table": name,
                    "role": "Exact typed table; the selected target cannot retain every value, name or type."})
    def encode(value):
        if isinstance(value, bytes):
            return {"encoding": "hex", "value": value.hex()}
        if isinstance(value, complex):
            return {"real": value.real, "imag": value.imag}
        if hasattr(value, "tolist"):
            return value.tolist()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise TypeError("Unsupported scientific metadata type: " + type(value).__name__)
    sidecar = folder / "metadata.json"
    while sidecar.exists():
        sidecar = sidecar.with_stem(sidecar.stem + "_metadata")
    sidecar.write_text(json.dumps(manifest, indent=2, default=encode), encoding="utf-8")
    check()
    return sidecar
