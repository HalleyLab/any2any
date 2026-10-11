"""Chemical structures, biological sequences and triangle mesh conversion."""
from pathlib import Path

CHEM_INPUTS = "mol sdf sd smi smiles can mol2 pdb pdbqt pqr xyz cif gro hin alc car mop mopout g03 g09 g16 gam gamout out log nwo molden txyz exyz".split()
CHEM_OUTPUTS = "sdf mol smi can mol2 pdb pdbqt pqr xyz cif gro hin alc mop gjf nw exyz".split()
SEQUENCES = {
    "fasta": "fasta", "fa": "fasta", "fas": "fasta", "fna": "fasta", "faa": "fasta",
    "fastq": "fastq", "fq": "fastq", "gb": "genbank", "gbk": "genbank", "genbank": "genbank",
    "embl": "embl", "pir": "pir", "nexus": "nexus", "nex": "nexus", "phy": "phylip",
    "phylip": "phylip", "stockholm": "stockholm", "aln": "clustal", "seqxml": "seqxml",
    "abi": "abi", "ab1": "abi", "abif": "abi", "sff": "sff",
    "dna": "snapgene", "xdna": "xdna", "gck": "gck", "ape": "genbank",
    "gbff": "genbank", "gbs": "genbank", "gbank": "genbank", "fsa": "fasta",
    "tab": "tab", "p1": "pir", "maf": "maf", "msf": "msf",
}
SEQ_OUTPUTS = "fasta fa fastq fq gb gbk embl pir nexus phy stockholm aln seqxml xdna".split()
MESH_INPUTS = "stl ply obj off glb gltf 3mf dae".split()
MESH_OUTPUTS = "stl ply obj off glb".split()
INPUTS = {"Chemical structures": " ".join(CHEM_INPUTS), "Biological sequences": " ".join(SEQUENCES),
          "3D meshes": " ".join(MESH_INPUTS)}
OUTPUTS = {"Chemical structures": " ".join(CHEM_OUTPUTS), "Biological sequences": " ".join(SEQ_OUTPUTS),
           "3D meshes": " ".join(MESH_OUTPUTS)}

def targets(path):
    ext = Path(path).suffix.lower().lstrip(".")
    if ext in CHEM_INPUTS:
        return CHEM_OUTPUTS
    if ext in SEQUENCES:
        if ext == "nex" and Path(path).is_file():
            with Path(path).open("rb") as stream:
                if stream.read(4) == b"NEX1":
                    return []
        return [target for target in SEQ_OUTPUTS if target not in ("fastq", "fq") or ext in ("fastq", "fq", "abi", "ab1", "abif", "sff")] + ["svg", "png", "pdf"]
    if ext in MESH_INPUTS:
        return MESH_OUTPUTS
    return []

def handles(path, ext):
    return ext in targets(path)


def babel():
    import os
    import openbabel
    data = Path(openbabel.__file__).parent / "bin" / "data"
    if data.is_dir():
        os.environ["BABEL_DATADIR"] = str(data)
    from openbabel import pybel
    return pybel


def molecules(source, ext, folder, check):
    pybel = babel()
    src = source.suffix.lower().lstrip(".")
    src = {"smiles": "smi", "sd": "sdf"}.get(src, src)
    if src not in pybel.informats or ext not in pybel.outformats:
        raise ValueError("This chemical format is unavailable in the installed Open Babel build.")
    count = 0
    for count, molecule in enumerate(pybel.readfile(src, str(source)), 1):
        check()
        if not molecule.atoms:
            raise ValueError("The input contains an empty or invalid molecule.")
        if ext in ("xyz", "pdb", "pdbqt", "pqr", "gro", "g96", "gjf", "nw", "mop", "exyz") and molecule.dim == 0:
            # shortcut: limit automatic geometry to 200 atoms; add explicit geometry controls for larger structures.
            if len(molecule.atoms) > 200:
                raise ValueError("This structure has no coordinates. Generate geometry in your chemistry software first.")
            molecule.make3D(steps=20)
        if ext == "cif":
            try:
                molecule.unitcell
            except AttributeError:
                raise ValueError("CIF output needs crystal unit-cell data. Use MOL/SDF for a non-periodic molecule.") from None
        target = folder / f"{source.stem}_{count:04d}.{ext}"
        molecule.write(ext, str(target), overwrite=False)
        if ext in pybel.informats:
            restored = next(pybel.readfile(ext, str(target)), None)
            expected = sum(atom.atomicnum > 1 for atom in molecule)
            if restored is None or sum(atom.atomicnum > 1 for atom in restored) != expected:
                raise ValueError("Chemical output failed the heavy-atom count check.")
    if not count:
        raise ValueError("No valid chemical structures were found.")

def sequences(source, ext, folder, check):
    import hashlib
    import re
    from Bio import SeqIO
    source_format = SEQUENCES[source.suffix.lower().lstrip(".")]
    with SeqIO.parse(str(source), source_format) as parser:
        original = hashlib.sha256()
        count = 0

        def update(digest, record):
            sequence = str(record.seq).upper().encode("ascii")
            digest.update(str(len(sequence)).encode("ascii") + b":" + sequence)

        def records():
            nonlocal count
            for record in parser:
                check()
                if not record.seq:
                    raise ValueError("Empty sequence records cannot be converted.")
                if "molecule_type" not in record.annotations:
                    suffix = source.suffix.lower()
                    alphabet = set(str(record.seq).upper()) - set("-?")
                    if suffix == ".faa":
                        kind = "protein"
                    elif suffix == ".fna" or alphabet <= set("ACGTNRYSWKMBDHV"):
                        kind = "DNA"
                    elif alphabet <= set("ACGUNRYSWKMBDHV"):
                        kind = "RNA"
                    else:
                        kind = "protein"
                    record.annotations["molecule_type"] = kind
                if ext in ("fastq", "fq") and "phred_quality" not in record.letter_annotations and "solexa_quality" not in record.letter_annotations:
                    raise ValueError("FASTQ output needs measured quality scores. Scores are never invented.")
                if record.id.startswith("<unknown"):
                    record.id = re.sub(r"[^A-Za-z0-9_.-]", "_", source.stem) + f"_{count + 1}"
                    record.name = record.id
                count += 1
                update(original, record)
                yield record
            if not count:
                raise ValueError("No sequence records were found.")

        if ext in ("svg", "png", "pdf"):
            import plasmid_maps
            plasmid_maps.export(records(), source, ext, folder, check)
            return
        restored = hashlib.sha256()
        if ext == "xdna":
            for index, record in enumerate(records(), 1):
                target = folder / f"{source.stem}_{index:04d}.{ext}"
                SeqIO.write([record], str(target), "xdna")
                update(restored, SeqIO.read(str(target), "xdna"))
        else:
            target = folder / f"{source.stem}.{ext}"
            SeqIO.write(records(), str(target), SEQUENCES[ext])
            for record in SeqIO.parse(str(target), SEQUENCES[ext]):
                check()
                update(restored, record)
        if original.digest() != restored.digest():
            raise ValueError("Sequence output failed the sequence-content check.")


def meshes(source, ext, folder, check):
    import numpy as np
    import trimesh
    scene = trimesh.load_scene(source, allow_remote=False)
    if not scene.geometry or any(not isinstance(geometry, trimesh.Trimesh) or not len(geometry.faces) for geometry in scene.geometry.values()):
        raise ValueError("Only non-empty triangle meshes are supported, without curves or point-cloud objects.")
    check()
    target = folder / f"{source.stem}.{ext}"
    if ext == "glb":
        target.write_bytes(scene.export(file_type="glb"))
    else:
        mesh = scene.to_mesh()
        options = {"include_texture": False} if ext == "obj" else {}
        payload = mesh.export(file_type=ext, **options)
        target.write_bytes(payload.encode("utf-8") if isinstance(payload, str) else payload)
    check()
    restored = trimesh.load_scene(target, allow_remote=False)
    if not restored.geometry or not np.allclose(scene.bounds, restored.bounds, rtol=1e-5, atol=1e-6):
        raise ValueError("Mesh output failed the geometry bounds check.")

def convert(source, ext, folder, check):
    src = source.suffix.lower().lstrip(".")
    if src in CHEM_INPUTS:
        molecules(source, ext, folder, check)
    elif src in SEQUENCES:
        sequences(source, ext, folder, check)
    else:
        meshes(source, ext, folder, check)
    check()
