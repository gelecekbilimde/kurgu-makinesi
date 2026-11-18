"""Review tooling: render every sample of a template and lay their posters out on one contact sheet."""
import math
from pathlib import Path

import deliver
import hf

TILE = 320
COLS = 4


def samples(template, rows, render_fn):
    """Render each samples.json row (a batch row without "template"), always fresh; returns the results entries."""
    entries = []
    for i, row in enumerate(rows, 1):
        row = {k: v for k, v in row.items() if k != "label"} | {
            "template": template, "fresh": True,
            "code": f"{i:02d}-{deliver.slugify(row.get('label') or 'ornek')}"}
        entries.append(render_fn(row))
    return entries


def contact_sheet(posters, dest, run=hf.run):
    """One PNG grid of the posters, each fitted into a TILE square on dark grey so transparent posters show."""
    n = len(posters)
    cols = min(COLS, n)
    rows = math.ceil(n / cols)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for p in posters:
        cmd += ["-i", str(p)]
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]scale={TILE}:{TILE}:force_original_aspect_ratio=decrease,format=rgba[s{i}];"
                     f"color=c=0x202020:s={TILE}x{TILE}:d=1[b{i}];"
                     f"[b{i}][s{i}]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1[t{i}]")
    parts.append("".join(f"[t{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,"
                 f"tile={cols}x{rows}:padding=8:margin=8:color=0x101010[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-frames:v", "1", str(dest)]
    r = run(cmd, Path(dest).parent)
    if r.returncode != 0:
        raise hf.ToolError(f"temas sayfası oluşturulamadı: {hf.last_line(r.stderr)}")
    return Path(dest)
