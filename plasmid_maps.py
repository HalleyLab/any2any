"""Simple annotation maps; sequence files remain the authoritative feature data."""
import html
import math


def svg(record):
    size = len(record.seq)
    if not size:
        raise ValueError("Cannot draw an empty sequence.")
    unit = "aa" if record.annotations.get("molecule_type") == "protein" else "nt" if record.annotations.get("molecule_type") == "RNA" else "bp"
    circular = record.annotations.get("topology", "linear") == "circular"
    features = [feature for feature in record.features if feature.location is not None and feature.type != "source"]
    height = 520 + 22 * len(features)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{height}" viewBox="0 0 760 {height}">',
             '<rect width="100%" height="100%" fill="white"/>', '<g font-family="sans-serif" fill="#17232d">',
             f'<text x="32" y="32" font-size="22">{html.escape(record.id)}</text>',
             f'<text x="32" y="58" font-size="14">{size:,} {unit} / {"circular" if circular else "linear"}</text>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#17232d"/></marker></defs>']
    if circular:
        parts.append('<circle cx="380" cy="282" r="180" fill="none" stroke="#a8b3bc" stroke-width="3"/>')
    else:
        parts.append('<path d="M 40 280 H 720" stroke="#a8b3bc" stroke-width="3"/>')
    colors = ["#2377b5", "#d76729", "#369454", "#9159b5", "#b43c65", "#2b929c"]
    for index, feature in enumerate(features):
        color = colors[index % len(colors)]
        label = next((feature.qualifiers[key][0] for key in ("label", "gene", "product", "note") if feature.qualifiers.get(key)), feature.type)
        label = html.escape(str(label))
        for location in feature.location.parts:
            start, end = int(location.start), int(location.end)
            if not 0 <= start <= end <= size:
                raise ValueError("Feature coordinates are outside the sequence.")
            if start == end:
                continue
            strand = location.strand
            arrow = ' marker-end="url(#arrow)"' if strand in (-1, 1) else ""
            if circular:
                radius = 180 - index % 6 * 13
                # Split a complete-circle feature into two arcs, since SVG arcs need distinct endpoints.
                positions = [(start, end)] if end - start < size else [(start, size / 2), (size / 2, end)]
                for a, b in positions:
                    if strand == -1:
                        a, b = b, a
                    angles = [(value / size * 2 * math.pi - math.pi / 2) for value in (a, b)]
                    points = [(380 + radius * math.cos(angle), 282 + radius * math.sin(angle)) for angle in angles]
                    large, sweep = int(abs(b - a) > size / 2), int(strand != -1)
                    path = f'M {points[0][0]:.3f} {points[0][1]:.3f} A {radius} {radius} 0 {large} {sweep} {points[1][0]:.3f} {points[1][1]:.3f}'
                    parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="8"{arrow}/>')
            else:
                x1, x2 = 40 + 680 * start / size, 40 + 680 * end / size
                if strand == -1:
                    x1, x2 = x2, x1
                y = 280 - index % 6 * 15
                parts.append(f'<path d="M {x1:.3f} {y} H {x2:.3f}" stroke="{color}" stroke-width="8"{arrow}/>')
        coordinates = html.escape(str(feature.location))
        parts.append(f'<rect x="32" y="{502 + index * 22}" width="12" height="12" fill="{color}"/>')
        parts.append(f'<text x="52" y="{513 + index * 22}" font-size="13">{label} / {html.escape(feature.type)} / {coordinates}</text>')
    if not features:
        parts.append('<text x="32" y="500" font-size="14">No annotated features. No genes were inferred.</text>')
    parts.append('</g></svg>')
    return "\n".join(parts)


def export(records, source, ext, folder, check):
    import pymupdf
    for index, record in enumerate(records, 1):
        check()
        payload = svg(record).encode("utf-8")
        target = folder / f"{source.stem}_{index:04d}.{ext}"
        if ext == "svg":
            target.write_bytes(payload)
        else:
            with pymupdf.open(stream=payload, filetype="svg") as document:
                if ext == "pdf":
                    target.write_bytes(document.convert_to_pdf())
                else:
                    document[0].get_pixmap(dpi=150).save(target)
