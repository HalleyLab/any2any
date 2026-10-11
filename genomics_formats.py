"""Read alignments, genomic annotations and nanopore signals without running analysis."""
from pathlib import Path
import csv
import gzip
import json
import struct
from contextlib import closing

GENOMIC = "sam bam vcf gff gff3 gtf bed bedgraph".split()
NANOPORE = "fast5 pod5".split()
INPUTS = {"Genomic records": " ".join(GENOMIC), "Nanopore signals": " ".join(NANOPORE), "Compressed sequences": "gz"}
OUTPUTS = {"Genomic records": "sam fasta fastq csv tsv jsonl", "Nanopore signals": "h5 npz csv", "Compressed sequences": "fasta fastq gb gbk"}

def sequence_gzip(path):
    return Path(path).suffix.lower() == ".gz" and Path(path).with_suffix("").suffix.lower() in (".fa", ".fasta", ".fna", ".faa", ".fq", ".fastq", ".gb", ".gbk")

def targets(path):
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in ("sam", "bam"):
        return ["sam", "fasta", "fastq", "csv", "tsv", "jsonl"]
    if suffix in GENOMIC:
        return ["csv", "tsv", "jsonl"]
    if suffix in NANOPORE:
        return ["h5", "npz", "csv"]
    if sequence_gzip(path):
        import research_formats
        return research_formats.targets(Path(path).with_suffix(""))
    return []

def handles(path, ext):
    return ext in targets(path)

def sam_tags(raw):
    """Serialize BAM auxiliary fields, preserving array subtypes and missing qualities."""
    name_size = struct.unpack_from("<I", raw, 12)[0] & 255
    cigar_count = struct.unpack_from("<I", raw, 16)[0] & 65535
    sequence_len = struct.unpack_from("<i", raw, 20)[0]
    offset = 36 + name_size + 4 * cigar_count + (sequence_len + 1) // 2 + sequence_len
    tags = []
    types = {"c": "b", "C": "B", "s": "h", "S": "H", "i": "i", "I": "I", "f": "f"}
    while offset < len(raw):
        tag, kind = bytes(raw[offset:offset + 2]).decode("ascii"), chr(raw[offset + 2])
        offset += 3
        if kind in ("Z", "H"):
            end = raw.index(0, offset)
            value = bytes(raw[offset:end]).decode("ascii")
            offset = end + 1
        elif kind == "A":
            value = chr(raw[offset])
            offset += 1
        elif kind == "B":
            subtype = chr(raw[offset])
            count = struct.unpack_from("<I", raw, offset + 1)[0]
            offset += 5
            fmt = "<" + str(count) + types[subtype]
            values = struct.unpack_from(fmt, raw, offset)
            offset += struct.calcsize(fmt)
            value = subtype + "," + ",".join(map(str, values))
        else:
            fmt = "<" + types[kind]
            value = struct.unpack_from(fmt, raw, offset)[0]
            offset += struct.calcsize(fmt)
            if kind != "f":
                kind = "i"
        tags.append(f"{tag}:{kind}:{value}")
    return "".join("\t" + tag for tag in tags)

def sam_lines(source, check):
    if source.suffix.lower() == ".bam":
        import bamnostic
        with bamnostic.AlignmentFile(str(source), "rb", require_index=False) as stream:
            header = str(stream.header).rstrip()
            if header.startswith("@"):
                yield from header.splitlines()
            else:
                for name, length in zip(stream.references, stream.lengths):
                    yield f"@SQ\tSN:{name}\tLN:{length}"
            for record in stream:
                check()
                mate = "*" if record.next_refID < 0 else "=" if record.next_refID == record.refID else stream.references[record.next_refID]
                qual = "*" if record.qual == "*" or set(record._raw_qual) == {255} else record.qual
                fields = [record.read_name, record.flag, record.reference_name or "*", record.pos + 1, record.mapq,
                          record.cigarstring or "*", mate, record.next_pos + 1, record.tlen, record.seq or "*", qual]
                yield "\t".join(map(str, fields)) + sam_tags(record._raw_stream)
    else:
        with source.open(encoding="utf-8-sig") as stream:
            for line in stream:
                check()
                yield line.rstrip("\r\n")

def table_rows(source, check, metadata):
    suffix = source.suffix.lower().lstrip(".")
    columns = None
    if suffix in ("sam", "bam"):
        columns = "QNAME FLAG RNAME POS MAPQ CIGAR RNEXT PNEXT TLEN SEQ QUAL TAGS".split()
        stream = sam_lines(source, check)
    else:
        stream = source.open(encoding="utf-8-sig")
    try:
        for line in stream:
            check()
            line = line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith(("#", "@", "track ", "browser ")):
                metadata["headers"].append(line)
                if suffix == "vcf" and line.startswith("#CHROM\t"):
                    columns = line[1:].split("\t")
                continue
            fields = line.split("\t")
            if suffix in ("sam", "bam"):
                if len(fields) < 11:
                    raise ValueError("SAM records require at least eleven tab-separated fields.")
                fields = fields[:11] + ["\t".join(fields[11:])]
            if columns is None:
                if suffix in ("gff", "gff3", "gtf"):
                    columns = "seqid source type start end score strand phase attributes".split()
                elif suffix == "vcf":
                    raise ValueError("VCF requires a #CHROM header.")
                elif suffix == "bedgraph":
                    columns = ["chrom", "start", "end", "value"]
                else:
                    columns = ["chrom", "start", "end", "name", "score", "strand", "thickStart", "thickEnd", "itemRgb", "blockCount", "blockSizes", "blockStarts"][:len(fields)]
                    columns += [f"field_{i + 1}" for i in range(len(columns), len(fields))]
            if len(fields) != len(columns):
                raise ValueError("Inconsistent genomic column counts. Normalize the file before conversion.")
            yield dict(zip(columns, fields))
    finally:
        if hasattr(stream, "close"):
            stream.close()

def genomic(source, ext, folder, check):
    from Bio.Seq import Seq
    target = folder / f"{source.stem}.{ext}"
    if ext == "sam":
        count = 0
        with target.open("w", encoding="utf-8", newline="\n") as output, closing(sam_lines(source, check)) as lines:
            for line in lines:
                if line:
                    output.write(line + "\n")
                    count += not line.startswith("@")
        if not count:
            raise ValueError("No alignment records were found.")
        return
    if ext in ("fasta", "fastq"):
        count = 0
        with target.open("w", encoding="utf-8", newline="\n") as output, closing(sam_lines(source, check)) as lines:
            for line in lines:
                if not line or line.startswith("@"):
                    continue
                fields = line.split("\t")
                if len(fields) < 11:
                    raise ValueError("Invalid SAM alignment record.")
                flag = int(fields[1])
                if flag & (0x100 | 0x800):
                    continue
                seq, qual = fields[9:11]
                if seq == "*":
                    raise ValueError("This alignment omits sequence data.")
                if flag & 0x10:
                    seq, qual = str(Seq(seq).reverse_complement()), qual[::-1]
                name = fields[0] + ("/1" if flag & 0x40 else "/2" if flag & 0x80 else "")
                if ext == "fastq":
                    if qual == "*" or len(qual) != len(seq):
                        raise ValueError("FASTQ needs stored quality scores; scores are never invented.")
                    if any(not 33 <= ord(value) <= 126 for value in qual):
                        raise ValueError("Sanger FASTQ requires PHRED scores from 0 to 93; quality clipping is not allowed.")
                    output.write(f"@{name}\n{seq}\n+\n{qual}\n")
                else:
                    output.write(f">{name}\n{seq}\n")
                count += 1
        if not count:
            raise ValueError("No primary read sequences were found.")
        return
    metadata = {"source_format": source.suffix, "headers": [], "values": "Original field strings; coordinate conventions are unchanged."}
    count = 0
    with target.open("w", encoding="utf-8", newline="") as output:
        writer = None
        for row in table_rows(source, check, metadata):
            if ext == "jsonl":
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                if writer is None:
                    writer = csv.DictWriter(output, fieldnames=list(row), delimiter="," if ext == "csv" else "\t")
                    writer.writeheader()
                writer.writerow(row)
            count += 1
    if not count:
        raise ValueError("No genomic data records were found.")
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

def nanopore_reads(source, check):
    import numpy as np
    if source.suffix.lower() == ".pod5":
        import pod5
        with pod5.Reader(source) as reader:
            for read in reader.reads():
                check()
                yield read.signal, {"read_id": str(read.read_id), "sample_rate_hz": read.run_info.sample_rate,
                                    "calibration_offset": read.calibration.offset, "calibration_scale_pA": read.calibration.scale,
                                    "channel": read.pore.channel, "start_sample": read.start_sample, "unit": "ADC counts",
                                    "conversion_to_pA": "(signal + calibration_offset) * calibration_scale_pA"}
    else:
        import h5py
        import vbz_h5py_plugin
        with h5py.File(source, "r") as reader:
            names = []
            reader.visititems(lambda name, item: names.append(name) if isinstance(item, h5py.Dataset) and name.endswith("/Signal") else None)
            for name in names:
                check()
                dataset = reader[name]
                top = name.split("/")[0]
                channel = reader.get(top + "/channel_id") or reader.get("UniqueGlobalKey/channel_id")
                attrs = dict(channel.attrs) if channel is not None else {}
                raw_attrs = dict(dataset.parent.attrs)
                yield dataset[()], {"read_id": raw_attrs.get("read_id", name), "sample_rate_hz": attrs.get("sampling_rate"),
                                    "calibration_offset": attrs.get("offset"), "calibration_scale_pA": float(attrs["range"]) / float(attrs["digitisation"]) if attrs.get("digitisation") else None,
                                    "channel": attrs.get("channel_number"), "start_sample": raw_attrs.get("start_time"),
                                    "unit": "ADC counts", "conversion_to_pA": "(signal + calibration_offset) * calibration_scale_pA"}

def nanopore(source, ext, folder, check):
    import numpy as np
    import h5py
    from imaging_formats import json_default
    count, metadata = 0, {}
    output = h5py.File(folder / f"{source.stem}.h5", "w") if ext == "h5" else None
    reads = nanopore_reads(source, check)
    try:
        for count, (signal, info) in enumerate(reads, 1):
            key = f"read_{count:06d}"
            metadata[key] = info
            if ext == "h5":
                dataset = output.create_dataset(key, data=signal, chunks=True)
                dataset.attrs["metadata_json"] = json.dumps(info, default=json_default)
            elif ext == "npz":
                np.savez(folder / f"{source.stem}_{key}.npz", signal=signal, metadata_json=np.array(json.dumps(info, default=json_default)))
            else:
                target = folder / f"{source.stem}_{key}.csv"
                with target.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["sample_index", "adc_counts"])
                    for start in range(0, len(signal), 100000):
                        check()
                        writer.writerows(zip(range(start, min(start + 100000, len(signal))), signal[start:start + 100000]))
            check()
    finally:
        reads.close()
        if output is not None:
            output.close()
    if not count:
        raise ValueError("No raw nanopore signal reads were found. Basecalling is not performed.")
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2, default=json_default), encoding="utf-8")

def convert(source, ext, folder, check):
    if sequence_gzip(source):
        import research_formats
        unpacked = folder / ("input" + source.with_suffix("").suffix)
        try:
            with gzip.open(source, "rb") as reader, unpacked.open("wb") as output:
                while chunk := reader.read(1024 * 1024):
                    check()
                    output.write(chunk)
            temporary = folder / "converted"
            temporary.mkdir()
            research_formats.sequences(unpacked, ext, temporary, check)
            for result in temporary.iterdir():
                stem = source.name.rsplit(".", 2)[0]
                result.rename(folder / (stem + result.name[len("input"):] if result.name.startswith("input") else result.name))
        finally:
            unpacked.unlink(missing_ok=True)
        return
    if source.suffix.lower().lstrip(".") in NANOPORE:
        nanopore(source, ext, folder, check)
    else:
        genomic(source, ext, folder, check)
    check()
