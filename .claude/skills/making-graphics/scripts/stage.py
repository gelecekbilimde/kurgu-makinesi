"""Build a temporary HyperFrames project for one render.

dest/            the template's files (without template.json / samples.json)
dest/design/     the design without design.md and reference/, plus variant.css (the chosen variant, or empty)
dest/kit/        hf-kit.js
dest/vars.json   {field: string}; lists and numbers JSON-encoded, decoded by the kit using <script id="kit-types">

The composition root gets its length, fps and size written in here: HyperFrames variables can't change the root's
data-duration, so templates never hold a length.
"""
import json
import re
import shutil
from pathlib import Path

import designs

KIT = Path(__file__).resolve().parents[1] / "kit" / "hf-kit.js"
TEMPLATE_META = ("template.json", "samples.json")
FRAME = (1920, 1080)


def _num(x):
    return f"{x:.6f}".rstrip("0").rstrip(".")


def _set_attrs(tag, attrs):
    for k, v in attrs.items():
        pattern = re.compile(rf'\s{re.escape(k)}=("[^"]*"|\'[^\']*\')')
        new = f" {k}={v}" if v.startswith("'") else f' {k}="{v}"'
        if pattern.search(tag):
            tag = pattern.sub(lambda _: new, tag, count=1)
        else:
            tag = re.sub(r"\s*(/?)>$", lambda m: new + m.group(1) + ">", tag, count=1)
    return tag


def _rewrite(html, root_attrs, variables, types):
    m = re.search(r"<[a-zA-Z][^>]*\sdata-composition-id=[^>]*>", html)
    if not m:
        raise ValueError("index.html içinde data-composition-id taşıyan bir kök öğe yok")
    html = html[:m.start()] + _set_attrs(m.group(0), root_attrs) + html[m.end():]
    decl = json.dumps(variables, ensure_ascii=False).replace("'", "&apos;")
    h = re.search(r"<html\b[^>]*>", html)
    if not h:
        raise ValueError("index.html içinde <html> etiketi yok")
    html = html[:h.start()] + _set_attrs(h.group(0), {"data-composition-variables": f"'{decl}'"}) + html[h.end():]
    script = f'<script id="kit-types" type="application/json">{json.dumps(types)}</script>\n'
    if "</head>" in html:
        return html.replace("</head>", script + "</head>", 1)
    return re.sub(r"(<body\b[^>]*>)", lambda mm: mm.group(1) + "\n" + script, html, count=1)


def _encode(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def stage(t, design, variant, values, vertical, frames, fps, dest):
    designs.check_variant(design, variant)
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(t.dir, dest, ignore=lambda d, names: [n for n in names if Path(d) == t.dir and n in TEMPLATE_META])
    shutil.copytree(design, dest / "design",
                    ignore=lambda d, names: [n for n in names if Path(d) == Path(design) and n in designs.DOC_PARTS])
    src = Path(design) / "variants" / f"{variant}.css" if variant else None
    (dest / "design" / "variant.css").write_text(src.read_text(encoding="utf-8") if src else "", encoding="utf-8")
    (dest / "kit").mkdir()
    shutil.copy(KIT, dest / "kit" / "hf-kit.js")

    if t.fixed_canvas:
        w, h = t.canvas["width"], t.canvas["height"]
    else:
        w, h = (FRAME[1], FRAME[0]) if vertical else FRAME
    attrs = {"data-duration": _num(frames / fps), "data-fps": str(fps), "data-width": str(w), "data-height": str(h)}
    variables = [{"id": f.name, "type": "string", "label": f.help or f.name, "default": ""} for f in t.fields]
    types = {f.name: f.type for f in t.fields}
    index = dest / "index.html"
    index.write_text(_rewrite(index.read_text(encoding="utf-8"), attrs, variables, types), encoding="utf-8")
    (dest / "vars.json").write_text(json.dumps({k: _encode(v) for k, v in values.items()}, ensure_ascii=False),
                                    encoding="utf-8")
    return dest
