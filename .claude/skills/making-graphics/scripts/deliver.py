"""Deliver renders into an output folder: <code>-<n>.<ext>, results.json, kaynaklar.txt.

A delivered file is never replaced (the B-roll skill may already have placed it in Resolve): numbering continues
past every existing <code>-<n> file, and results.json / kaynaklar.txt are merged, not overwritten.
"""
import json
import os
import re
import shutil
from pathlib import Path

_FOLD = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u",
                       "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u", "Â": "a", "Î": "i",
                       "Û": "u"})


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.translate(_FOLD).lower()).strip("-")
    return s[:40].rstrip("-") or "grafik"


def load_results(out):
    path = Path(out) / "results.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"created": None, "notes": [], "renders": []}


def _next_number(out, results, code):
    pat = re.compile(re.escape(code) + r"-(\d+)")
    used = [int(m.group(1)) for r in results["renders"] if (m := pat.fullmatch(r["code"]))]
    if Path(out).is_dir():
        used += [int(m.group(1)) for p in Path(out).iterdir() if (m := pat.fullmatch(p.stem))]
    return max(used, default=0) + 1


def _link(src, dest):
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def add(out, results, code, entry, file):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = _next_number(out, results, code)
    name = f"{code}-{n}{Path(file).suffix}"
    _link(file, out / name)
    entry = {"code": f"{code}-{n}", "file": name, **entry}
    results["renders"].append(entry)
    return entry


def save(out, results, notes, now):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if not results.get("created"):
        results["created"] = now.isoformat()
    results["notes"].extend(notes)
    tmp = out / "results.json.tmp"
    tmp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out / "results.json")
    lines = []
    for r in results["renders"]:
        for s in r.get("sources") or []:
            if s not in lines:
                lines.append(s)
    (out / "kaynaklar.txt").write_text("".join(f"{x}\n" for x in lines), encoding="utf-8")
