"""Review tooling: render every sample of a template and lay their posters out on one contact sheet."""
import html
import json
import math
import shutil
from pathlib import Path

import deliver
import designs
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


def web_video(mov, run=hf.run):
    """A browser-playable copy of an alpha .mov (VP9 with alpha in WebM) for the showcase page."""
    dest = Path(mov).with_suffix(".webm")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(mov), "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0",
           "-crf", "32", "-an", str(dest)]
    r = run(cmd, Path(mov).parent)
    if r.returncode != 0:
        raise hf.ToolError(f"web videosu üretilemedi: {hf.last_line(r.stderr)}")
    return dest


PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="design/tokens.css">
<style>
 * {{ box-sizing: border-box; margin: 0; }}
 body {{ background: var(--page); color: var(--ink); font-family: var(--font-head); padding: 48px 5vw 120px; }}
 h1 {{ font-weight: var(--head-weight); font-size: 48px; }}
 .sub {{ font: var(--label-weight) 13px var(--font-label); letter-spacing: var(--label-tracking); color: var(--label);
   text-transform: uppercase; margin: 10px 0 40px; }}
 .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 36px; }}
 .card video, .card img {{ width: 100%; display: block; border-radius: 6px; outline: 1px solid var(--rule);
   background: repeating-conic-gradient(#151515 0 25%, #1d1d1d 0 50%) 0 0 / 24px 24px; }}
 .card h2 {{ font: var(--label-weight) 14px var(--font-label); letter-spacing: var(--label-tracking);
   text-transform: uppercase; margin: 14px 0 4px; }}
 .card p {{ color: var(--body); font-size: 16px; line-height: 1.4; }}
 .card code {{ font: 12px var(--font-label); color: var(--dim); }}
</style></head>
<body>
<h1>{design}</h1>
<div class="sub">{sub}</div>
<div class="grid">
{cards}
</div>
</body></html>
"""


def showcase(root, design, out, render_fn, run=hf.run):
    """Render the first sample of every template of a design at 1080p and write out/index.html showing them all."""
    out = Path(out)
    ddir = designs.design_dir(root, design)
    if (out / "design").exists():
        shutil.rmtree(out / "design")
    shutil.copytree(ddir, out / "design", ignore=lambda d, names: [n for n in names if Path(d) == ddir
                                                                    and n in designs.DOC_PARTS])
    cards = []
    for t in designs.templates(root, design):
        path = t.dir / "samples.json"
        rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        if not rows:
            continue
        row = {k: v for k, v in rows[0].items() if k != "label"} | {
            "template": t.name, "code": t.name, "resolution": "1080p"}
        e = render_fn(row)
        media = Path(e["file"])
        full = out / "media" / media
        if full.suffix == ".mov":
            media = media.with_suffix(".webm")
            web_video(full, run=run)
        src = "media/" + media.as_posix()
        tag = (f'<img src="{src}" alt="">' if media.suffix == ".png"
               else f'<video src="{src}" autoplay loop muted playsinline></video>')
        fields = ", ".join(f.name + ("*" if f.required else "") for f in t.fields)
        cards.append(f'<div class="card">{tag}<h2>{html.escape(t.name)} · {html.escape(t.status)}</h2>'
                     f'<p>{html.escape(t.description)}</p><code>{html.escape(fields)}</code></div>')
    sub = ("başlangıç örneği · kanalın onaylı tasarımı değil · " if design == "starter" else "") + \
        f"{len(cards)} şablon"
    page = out / "index.html"
    page.write_text(PAGE.format(title=html.escape(design) + " · şablonlar", design=html.escape(design), sub=sub,
                                cards="\n".join(cards)), encoding="utf-8")
    return page
