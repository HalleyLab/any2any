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
    metadata = {"attrs": {}, "variables": {}}
    if ext == "npy":
        arrays = {"data": np.load(source, allow_pickle=False)}
    elif ext == "npz":
        with np.load(source, allow_pickle=False) as archive:
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
            from scipy.io import loadmat
            arrays = {key: value for key, value in loadmat(source).items() if not key.startswith("__")}
        else:
            arrays = {}
            with h5py.File(source, "r") as dataset:
                metadata["attrs"] = dict(dataset.attrs)
                def visit(name, item):
                    if isinstance(item, h5py.Dataset):
                        if name.startswith("#refs#"):
                            raise ValueError("MATLAB cell/reference arrays need a specialist exporter.")
                        strings = h5py.check_string_dtype(item.dtype)
                        value = np.asarray(item.asstr()[()], dtype=str) if strings else item[()]
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
        np.savez(target, **arrays)
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
                dtype = str if value.dtype.kind == "U" else ("i1" if value.dtype.kind == "b" else value.dtype)
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
            if mask.any() and value.dtype.kind in "iu" and (np.abs(value.astype(object)) > 2**53).any():
                raise ValueError("Missing-value export would lose precision in large integers. Keep NetCDF or HDF5.")
            if str(attrs.get("_Unsigned", "")).lower() == "true" and value.dtype.kind == "i":
                value = value.view(np.dtype(value.dtype.str.replace("i", "u")))
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
    frame = pd.read_csv(source, sep=sep, engine="python" if sep == r"\s+" else "c",
                        header=header, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if header is None:
        frame.columns = [f"column_{index + 1}" for index in range(len(frame.columns))]
    for column in frame:
        values = frame[column]
        if values.str.match(r"^[+-]?0\d+").any():
            continue
        try:
            numeric = pd.to_numeric(values.replace("", None), errors="raise")
            frame[column] = values.replace("", None).to_numpy(dtype=float) if pd.api.types.is_float_dtype(numeric.dtype) else numeric
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

def read_tables(source):
    import pandas as pd
    ext = source.suffix.lower().lstrip(".")
    if ext in ("csv", "tsv", "dat", "asc"):
        result = {"data": read_delimited(source, ext)}
    elif ext == "xlsx":
        result = {name: frame.infer_objects() for name, frame in pd.read_excel(source, sheet_name=None, engine="openpyxl", dtype=object).items()}
    elif ext in ("parquet", "pq"):
        result = {"data": pd.read_parquet(source)}
    elif ext in ("feather", "arrow"):
        result = {"data": pd.read_feather(source)}
    elif ext in ("json", "jsonl", "ndjson"):
        if ext == "json":
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            result = {"data": pd.read_json(source, orient="table", precise_float=True)} if isinstance(data, dict) and "schema" in data and "data" in data else {"data": pd.DataFrame(data)}
        else:
            result = {"data": pd.read_json(source, orient="records", lines=True, dtype=False, convert_dates=False, precise_float=True)}
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
            result = {name: pd.read_sql_query('SELECT * FROM "' + name.replace('"', '""') + '"', connection) for name in names}
    elif ext == "pzfx":
        result = read_prism(source)
    else:
        raise ValueError("Unsupported scientific table input.")
    if not result or any(not isinstance(frame, pd.DataFrame) or len(frame.columns) == 0 for frame in result.values()):
        raise ValueError("No supported rectangular data tables were found.")
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
        if ext in ARRAYS:
            arrays = {}
            for name, frame in tables.items():
                if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
                    raise ValueError("Array exports require numeric table columns. Use Parquet, Excel or statistical formats for mixed data.")
                arrays[name] = frame.to_numpy()
            write_arrays(arrays, {}, ext, folder, source.stem, check)
        else:
            write_tables(tables, ext, folder, source.stem, check)
    check()
