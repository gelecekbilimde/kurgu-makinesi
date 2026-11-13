"""Deliver picked clips into an output folder: <code>-<n>_<source>-<id>.mp4, results.json, kaynaklar.txt.

A delivered file is never replaced or renamed (the B-roll skill may already have placed it in Resolve), so a
re-run continues the numbering of its code and results.json / kaynaklar.txt are merged, not overwritten.
"""
import json
import os
import re
import shutil

_FOLD = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u",
                       "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u", "Â": "a", "Î": "i",
                       "Û": "u"})
CANDIDATE_FIELDS = ("source", "id", "page_url", "creator", "licence", "credit", "width", "height", "fps",
                    "duration_s", "orientation", "warnings", "third_party")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.translate(_FOLD).lower()).strip("-")
    return s[:40].rstrip("-") or "stok"


def _safe(part):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", part).strip("-") or "x"


def load_results(out):
    path = out / "results.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"created": None, "notes": [], "requests": []}


def _request(results, code):
    return next((r for r in results["requests"] if r["code"] == code), None)


def delivered(results, code):
    r = _request(results, code)
    return {(c["source"], c["id"]) for c in r["candidates"]} if r else set()


def _next_number(request):
    numbers = [int(m.group(1)) for c in request["candidates"]
               if (m := re.fullmatch(re.escape(request["code"]) + r"-(\d+)", c["code"]))]
    return max(numbers, default=0) + 1


def _link(src, dest):
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def add_request(out, results, query, code, orientation, picks, notes):
    out.mkdir(parents=True, exist_ok=True)
    request = _request(results, code)
    if request is None:
        request = {"query": query, "code": code, "orientation": orientation, "notes": [], "candidates": []}
        results["requests"].append(request)
    request["notes"].extend(notes)
    n = _next_number(request)
    for pick in picks:
        e = pick.entry
        name = f"{code}-{n}_{_safe(e['source'])}-{_safe(e['id'])}.mp4"
        dest = out / name
        if not dest.exists():
            _link(pick.path, dest)
        cand = {"code": f"{code}-{n}", "file": name, **{k: e.get(k) for k in CANDIDATE_FIELDS},
                "from_cache": pick.from_cache}
        cand["warnings"] = list(cand["warnings"] or [])
        cand["third_party"] = bool(cand["third_party"])
        request["candidates"].append(cand)
        n += 1
    return request


def save(out, results, notes, now):
    out.mkdir(parents=True, exist_ok=True)
    if not results.get("created"):
        results["created"] = now.isoformat()
    results["notes"].extend(notes)
    tmp = out / "results.json.tmp"
    tmp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out / "results.json")
    lines = []
    for r in results["requests"]:
        for c in r["candidates"]:
            line = f"{c['credit']}: {c['page_url']}"
            if line not in lines:
                lines.append(line)
    (out / "kaynaklar.txt").write_text("".join(f"{x}\n" for x in lines), encoding="utf-8")
