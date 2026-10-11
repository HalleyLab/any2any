"""Value-based generated fixtures for research formats. No input code is executed."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import tempfile
import threading

import numpy as np
import pandas as pd
import any2any as a
import scientific as s
import source_formats as code
import research_formats as research

def main():
    checks = 0
    with tempfile.TemporaryDirectory(prefix="any2any-research-") as name:
        base = Path(name)
        out = base / "output"
        def convert(source, ext):
            nonlocal checks
            products = a.convert(source, ext, out)
            assert products and all(path.is_file() and path.stat().st_size and path.parent == out for path in products)
            assert all(path.is_file() for path in out.iterdir())
            checks += 1
            print(f"PASS research {source.suffix} -> {ext}", flush=True)
            return products

        mixed = base / "mixed.csv"
        mixed.write_text("SAMPLE,DOSE,LABEL\n00123,1.25,alpha\n00234,2.5,beta\n00345,3.75,gamma\n", encoding="utf-8")
        original = hashlib.sha256(mixed.read_bytes()).hexdigest()
        for ext in s.TABLES:
            result = convert(mixed, ext)[0]
            restored = next(iter(s.read_tables(result).values()))
            assert restored["SAMPLE"].astype(str).tolist() == ["00123", "00234", "00345"]
            assert np.allclose(restored["DOSE"].astype(float), [1.25, 2.5, 3.75])
        assert hashlib.sha256(mixed.read_bytes()).hexdigest() == original

        numeric = base / "numeric.csv"
        numeric.write_text("time,signal\n1,1.25\n2,2.5\n3,3.75\n", encoding="utf-8")
        matrix = np.array([[1, 1.25], [2, 2.5], [3, 3.75]])
        for ext in s.ARRAYS:
            result = convert(numeric, ext)[0]
            arrays, _ = s.read_arrays(result)
            assert np.allclose(next(iter(arrays.values())), matrix)
            if ext != "npy":
                returned = convert(result, "csv")
                assert any(np.allclose(next(iter(s.read_tables(path).values())).to_numpy(), matrix) for path in returned)

        single = base / "single.asc"
        single.write_text("signal\n1.25\n2.5\n", encoding="utf-8")
        result = convert(single, "npy")[0]
        assert s.read_arrays(result)[0]["data"].tolist() == [[1.25], [2.5]]
        raw_matrix = base / "raw.dat"
        raw_matrix.write_text("1 2.5\n3 4.5\n", encoding="utf-8")
        result = convert(raw_matrix, "npz")[0]
        assert s.read_arrays(result)[0]["data"].tolist() == [[1, 2.5], [3, 4.5]]

        tensor = base / "tensor.npz"
        tensor = base / "tensor.npz"
        np.savez(tensor, volume=np.arange(24).reshape(2, 3, 4), matrix=matrix)
        for ext in ("npz", "mat", "h5", "nc"):
            result = convert(tensor, ext)[0]
            restored, _ = s.read_arrays(result)
            assert np.array_equal(restored["volume"], np.arange(24).reshape(2, 3, 4))
            assert np.array_equal(restored["matrix"], matrix)
        assert len(convert(tensor, "npy")) == 2
        before = set(out.iterdir())
        try:
            a.convert(tensor, "csv", out)
            raise AssertionError("Tensor was silently flattened.")
        except ValueError:
            pass
        assert set(out.iterdir()) == before

        import netCDF4
        netcdf = base / "units.nc"
        with netCDF4.Dataset(netcdf, "w") as dataset:
            dataset.title = "Calibration"
            dataset.createDimension("sample", 3)
            value = dataset.createVariable("signal", "f8", ("sample",), fill_value=-999)
            value.units = "mV"
            value.scale_factor = 0.5
            value.set_auto_maskandscale(False)
            value[:] = [2, 4, -999]
        for ext in ("nc", "h5"):
            result = convert(netcdf, ext)[0]
            arrays, metadata = s.read_arrays(result)
            assert np.array_equal(arrays["signal"], [2, 4, -999])
            assert metadata["attrs"]["title"] == "Calibration"
            assert metadata["variables"]["signal"]["attrs"]["units"] == "mV"

        physical = convert(netcdf, "npz")[0]
        unpacked = s.read_arrays(physical)[0]["signal"]
        assert np.allclose(unpacked[:2], [1, 2]) and np.isnan(unpacked[2])
        intermediate = convert(netcdf, "h5")[0]
        returned = convert(intermediate, "nc")[0]
        with netCDF4.Dataset(returned) as dataset:
            assert dataset.variables["signal"].dimensions == ("sample",)
            assert np.allclose(dataset.variables["signal"][:2], [1, 2])

        precise = base / "precise.csv"
        precise.write_text("value\n0.30000000000000004\n1.2345678901234567\n", encoding="utf-8")
        for ext in ("json", "jsonl"):
            result = convert(precise, ext)[0]
            actual = next(iter(s.read_tables(result).values()))["value"].tolist()
            assert actual == [0.30000000000000004, 1.2345678901234567]

        import h5py
        text_array = base / "text.h5"
        with h5py.File(text_array, "w") as dataset:
            dataset.create_dataset("names", data=np.array(["café", "sample"], dtype=object), dtype=h5py.string_dtype())
        result = convert(text_array, "npz")[0]
        assert s.read_arrays(result)[0]["names"].tolist() == ["café", "sample"]
        boolean = base / "flags.npy"
        np.save(boolean, np.array([True, False]))
        result = convert(boolean, "npz")[0]
        assert s.read_arrays(result)[0]["data"].dtype == np.dtype(bool)
        complex_file = base / "complex.npz"
        np.savez(complex_file, values=np.array([[1 + 2j, 3 - 4j]]))
        for ext in ("mat", "h5", "npz"):
            result = convert(complex_file, ext)[0]
            assert np.array_equal(s.read_arrays(result)[0]["values"], [[1 + 2j, 3 - 4j]])

        mat73 = base / "mat73.mat"
        with h5py.File(mat73, "w") as dataset:
            value = dataset.create_dataset("matrix", data=matrix.T)
            value.attrs["MATLAB_class"] = np.bytes_("double")
        result = convert(mat73, "npz")[0]
        assert np.array_equal(s.read_arrays(result)[0]["matrix"], matrix)

        import pyreadstat
        labels = base / "labels.sav"
        pyreadstat.write_sav(pd.DataFrame({"group": [1.0, 2.0, 999.0]}), labels,
                            column_labels={"group": "Treatment group"},
                            variable_value_labels={"group": {1: "Control", 2: "Drug"}},
                            missing_ranges={"group": [999]})
        result = convert(labels, "zsav")[0]
        frame, meta = pyreadstat.read_sav(result, user_missing=True)
        assert frame["group"].tolist() == [1, 2, 999]
        assert meta.column_names_to_labels["group"] == "Treatment group"
        assert meta.variable_value_labels["group"][1] == "Control"
        assert meta.missing_ranges["group"]

        workbook = base / "multi.xlsx"
        with pd.ExcelWriter(workbook) as writer:
            pd.DataFrame({"x": [1, 2]}).to_excel(writer, sheet_name="First", index=False)
            pd.DataFrame({"y": [3, 4]}).to_excel(writer, sheet_name="Second", index=False)
        assert len(convert(workbook, "csv")) == 2
        database = convert(workbook, "sqlite")[0]
        assert len(s.read_tables(database)) == 2

        formula = base / "literal.csv"
        formula.write_text('value\n"=1+1"\n', encoding="utf-8")
        import openpyxl
        literal = convert(formula, "xlsx")[0]
        with_literal = openpyxl.load_workbook(literal, data_only=False)
        assert with_literal.active["A2"].value == "=1+1" and with_literal.active["A2"].data_type == "s"
        with_literal.close()

        prism = base / "prism.pzfx"
        prism.write_text('<GraphPadPrismFile><Table ID="T1"><Title>Assay</Title><XColumn><Title>Dose</Title><Subcolumn><d>1</d><d>2</d></Subcolumn></XColumn><YColumn><Title>Response</Title><Subcolumn><d>4.5</d><d>9</d></Subcolumn></YColumn></Table></GraphPadPrismFile>', encoding="utf-8")
        result = convert(prism, "csv")[0]
        assert np.allclose(next(iter(s.read_tables(result).values())).to_numpy().astype(float), [[1, 4.5], [2, 9]])

        pybel = research.babel()
        molecule = pybel.readstring("smi", "CCO")
        molecule.make3D(steps=5)
        chemical = base / "ethanol.mol"
        molecule.write("mol", str(chemical))
        for ext in research.CHEM_OUTPUTS:
            if ext != "cif":
                convert(chemical, ext)
        unitcell = pybel.ob.OBUnitCell()
        unitcell.SetData(10, 10, 10, 90, 90, 90)
        molecule.OBMol.CloneData(unitcell)
        crystal = base / "crystal.cif"
        molecule.write("cif", str(crystal))
        convert(crystal, "cif")
        multiple = base / "molecules.smi"
        multiple.write_text("CCO ethanol\nCC acetane\n", encoding="utf-8")
        assert len(convert(multiple, "mol")) == 2

        sequence = base / "reads.fastq"
        sequence.write_text("@seq1\nACGTACGT\n+\nIIIIIIII\n@seq2\nACGTACGA\n+\nHHHHHHHH\n", encoding="utf-8")
        for ext in research.SEQ_OUTPUTS:
            convert(sequence, ext)
        fasta = base / "sample.fasta"
        fasta.write_text(">sequence\nACGTACGT\n", encoding="utf-8")
        assert "fastq" not in a.targets(fasta)

        import trimesh
        scene = trimesh.Scene()
        scene.add_geometry(trimesh.creation.box(), node_name="one")
        moved = np.eye(4)
        moved[:3, 3] = [5, 2, 1]
        scene.add_geometry(trimesh.creation.box(), node_name="two", transform=moved)
        mesh = base / "scene.glb"
        mesh.write_bytes(scene.export(file_type="glb"))
        for ext in research.MESH_OUTPUTS:
            convert(mesh, ext)

        script = base / "analysis.py"
        marker = base / "must-not-exist"
        script.write_text('# %% [markdown]\n# Analysis notes\n# %%\nfrom pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\nvalue = "<script>alert(1)</script>"\nprint(value)\n', encoding="utf-8")
        for ext in ("py", "ipynb", "md", "rmd", "qmd", "html", "pdf", "txt"):
            result = convert(script, ext)[0]
            if ext == "ipynb":
                restored = convert(result, "py")[0]
                ast.parse(restored.read_text(encoding="utf-8"))
                assert "Analysis notes" in restored.read_text(encoding="utf-8")
                assert "js" not in a.targets(result)
            if ext == "html":
                assert "<script>alert" not in result.read_text(encoding="utf-8")
        assert not marker.exists()
        assert "js" not in a.targets(script)

        samples = {"r": "x <- 1\n", "jl": "x = 1\n", "m": "x = 1;\n", "js": "const x = 1;\n",
                   "ts": "const x: number = 1;\n", "cpp": "int x = 1;\n", "java": "class Sample {}\n",
                   "rs": "fn main() {}\n", "sql": "SELECT 1;\n", "f90": "program demo\nend program\n"}
        for ext, content in samples.items():
            source = base / f"program.{ext}"
            source.write_text(content, encoding="utf-8")
            notebook = convert(source, "ipynb")[0]
            restored = convert(notebook, ext)[0]
            assert content.strip() in restored.read_text(encoding="utf-8")

        for ext in ("c", "h", "hpp", "f", "fsx", "pyw", "cc", "cxx", "mjs", "cjs", "jsx", "tsx"):
            content = "print(1)\n" if ext == "pyw" else ("      END\n" if ext == "f" else "// Source sample\n")
            source = base / f"alias.{ext}"
            source.write_text(content, encoding="utf-8")
            notebook = convert(source, "ipynb")[0]
            assert ext in a.targets(notebook)
            restored = convert(notebook, ext)[0]
            assert content.strip() in restored.read_text(encoding="utf-8")

        malformed = base / "malformed.ipynb"
        malformed.write_text("[]", encoding="utf-8")
        assert "html" in a.targets(malformed)

        config = base / "config.json"
        config = base / "config.json"
        config.write_text('{"root":{"name":"sample","count":3,"enabled":true}}', encoding="utf-8")
        for ext in code.STRUCTURED:
            result = convert(config, ext)[0]
            returned = convert(result, "json")[0]
            data = json.loads(returned.read_text(encoding="utf-8"))
            assert str(data["root"]["name"]) == "sample"
            if ext != "xml":
                assert data["root"]["count"] == 3 and data["root"]["enabled"] is True

        object_file = base / "objects.npy"
        np.save(object_file, np.array([{"value": 1}], dtype=object), allow_pickle=True)
        before = set(out.iterdir())
        try:
            a.convert(object_file, "npz", out)
            raise AssertionError("Pickled object array accepted.")
        except ValueError:
            pass
        assert set(out.iterdir()) == before

        long_code = base / "long.py"
        long_code.write_text('value = "' + "x" * 4000 + 'END_MARKER"\nprint(value)\n', encoding="utf-8")
        result = convert(long_code, "pdf")[0]
        with a.pymupdf.open(result) as document:
            assert "END_MARKER" in "".join(page.get_text() for page in document)

        unsafe = base / "unsafe.yaml"
        unsafe.write_text("!!python/object/apply:os.system ['echo unsafe']", encoding="utf-8")
        before = set(out.iterdir())
        try:
            a.convert(unsafe, "json", out)
            raise AssertionError("Unsafe YAML accepted.")
        except Exception as error:
            assert not isinstance(error, AssertionError)
        assert set(out.iterdir()) == before
        cancel = threading.Event()
        cancel.set()
        try:
            a.convert(tensor, "mat", out, cancel)
            raise AssertionError("Cancellation ignored.")
        except a.Cancelled:
            pass
        print(f"SUCCESS: {checks} research/code conversions, value preservation and boundary checks.", flush=True)

if __name__ == "__main__":
    try:
        main()
    finally:
        a.close_office()
