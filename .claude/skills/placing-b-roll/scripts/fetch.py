"""broll.py fetch: media for every request of the rows found in the frozen chapters -> broll/fetched.json.

fetched.json: {"units": "frames", "rows": {"<key>": [Asset, ...]}}, one Asset per request, in request order:
  {"tag", "kind": "stock"|"graphic"|"kaynak"|"placeholder", "request_hash", "track": 2|3,
   "files": [{"file": abs path, "code", "frames": int|null (null = still), "credit": str|null}],
   "hold": abs path|null, "hold_from": int|null, "note": str|null, "code": str|null}
code: the request's code for the tools (R005, G005, R005b ...): stable per request, never shared by two requests
of a row; null for placeholder requests.
hold/hold_from: set only when the row is longer than the template maximum; the graphic plays [0, hold_from) and the
hold still (frame hold_from) covers the rest of the row, so the outro never plays.
A request is fetched again only when its request_hash (sha1 of the canonical request JSON, plus the row's
coverage frames for graphics) changes. Delivered files are never deleted. A placeholder's note starts with its
reason ("aday bulunamadı", "geçersiz istek: ...", "arşiv", ...). A placeholder caused by a tool crash or a
page that did not open gets request_hash null, so the next fetch tries again.
"""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reqs  # noqa: E402
import rows as rows_mod  # noqa: E402
import stills  # noqa: E402

SKILLS = HERE.parents[1]
REPO = SKILLS.parents[1]
FIND_STOCK = SKILLS / "finding-stock-footage" / "scripts" / "find_stock.py"
MAKE_GRAPHIC = SKILLS / "making-graphics" / "scripts" / "make_graphic.py"
BASE_FPS = 25  # make_graphic.py --list gives frame limits at 25 fps
# A graphic held past its template maximum is held from this point (the graphic is fully built, before its outro):
# make_graphic.py:50 POSTER_AT, the frame the graphics skill takes as the poster.
POSTER_AT = 0.7
NOT_FOUND = "aday bulunamadı"
INVALID = "geçersiz istek"
GRAPHIC_FAILED = "grafik üretilemedi"


class FetchError(Exception):
    """A missing input or a tool that can't run at all; Turkish, fit to show the editor."""


@dataclass
class Summary:
    fetched: int = 0                      # requests fetched this run
    cached: int = 0                       # requests reused from fetched.json
    archive: int = 0                      # files the tools took from their cache/archive
    placeholders: Counter = field(default_factory=Counter)  # reason -> count, all current rows
    not_found: list = field(default_factory=list)            # row ids align could not place
    notes: list = field(default_factory=list)

    def lines(self):
        out = [f"{self.fetched} istek getirildi, {self.cached} istek önceki getirmeden; "
               f"önbellek/arşivden {self.archive} dosya"]
        if self.placeholders:
            out.append("Yer tutucular: " + ", ".join(f"{r}: {n}" for r, n in sorted(self.placeholders.items())))
        if self.not_found:
            out.append("Bölümde bulunamayan satırlar (getirilmedi): " + ", ".join(self.not_found))
        out += [f"Not: {n}" for n in self.notes]
        return out


def request_hash(req, cov):
    s = json.dumps(req, sort_keys=True, ensure_ascii=False)
    if req.get("kind") == "graphic":
        s += f"|{cov}"
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def stock_count(cov, fps):
    return max(3, math.ceil(cov / (5 * fps)))


def _number(row_id):
    m = re.search(r"\d+", row_id)
    return m.group(0) if m else row_id


def _suffixed(base, i):
    """the i-th (0-based) request of a row: base, base + b, base + c, ..."""
    return base if i == 0 else base + chr(ord("a") + i)


def _base(req, row_id):
    return {"stock": row_id, "graphic": "G" + _number(row_id), "kaynak": row_id}.get(req.get("kind"))


def _codes(row_id, reqs_, hits):
    """One code per request of a row, stable and unique: a reused asset keeps its stored code; any other request
    gets the code of its index in the row (R005, R005b, ...), moved on to the next free suffix if a reused
    asset of another request already holds it. Placeholder requests get None."""
    codes, taken = [None] * len(reqs_), set()
    for i, req in enumerate(reqs_):
        if hits[i] is not None and _base(req, row_id):
            codes[i] = hits[i].get("code") or _suffixed(_base(req, row_id), i)
            taken.add(codes[i])
    for i, req in enumerate(reqs_):
        base = _base(req, row_id)
        if hits[i] is None and base:
            n = i
            while _suffixed(base, n) in taken:
                n += 1
            codes[i] = _suffixed(base, n)
            taken.add(codes[i])
    return codes


def _read(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _tool(runner, script, *args):
    cmd = [sys.executable, str(script), *map(str, args)]
    try:
        return runner(cmd, cwd=str(REPO), capture_output=True, text=True)
    except FileNotFoundError as err:
        raise FetchError(f"çalıştırılamadı: {err}") from None


def _last(text):
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    return lines[-1] if lines else ""


class _Fetch:
    def __init__(self, ep, runner):
        self.ep, self.runner, self.fps = ep, runner, ep.fps
        self.broll = ep.path("broll")
        self._templates = None

    # ---- inputs -------------------------------------------------------------------------------------------
    def templates(self):
        if self._templates is None:
            p = _tool(self.runner, MAKE_GRAPHIC, "--list", "--json")
            if p.returncode != 0:
                raise FetchError(f"şablon listesi alınamadı (make_graphic.py --list --json): {_last(p.stderr)}")
            self._templates = {t["name"]: t for t in json.loads(p.stdout)}
        return self._templates

    def limits(self, t):
        return tuple(round(t["frames"][k] * self.fps / BASE_FPS) for k in ("min", "max"))

    def background(self, req):
        t = self.templates().get(req.get("template"))
        return bool(req.get("background", bool(t) and t.get("output") == "fullscreen"))

    def track(self, req):
        if req.get("kind") in ("stock", "kaynak"):
            return 2
        if req.get("kind") == "graphic" and req.get("template") in self.templates():
            return 2 if self.background(req) else 3
        if "background" in req:
            return 2 if req["background"] else 3
        return 3 if req.get("tag") == "YAZI" else 2

    # ---- assets -------------------------------------------------------------------------------------------
    @staticmethod
    def asset(req, h, kind, track, files, hold=None, note=None, hold_from=None):
        return {"tag": req.get("tag"), "kind": kind, "request_hash": h, "track": track, "files": files,
                "hold": hold, "hold_from": hold_from, "note": note}

    def placeholder(self, job, note, retry=False):
        req, row = job["req"], job["row"]
        track = self.track(req)
        tag = req.get("tag") or "?"
        tag_slug = re.sub(r"[^A-Za-z0-9]+", "", tag.translate(str.maketrans("İŞĞÜÖÇ", "ISGUOC"))) or "x"
        out = Path(self.broll, "stills", f"{row['id']}-{job['i'] + 1}-{tag_slug}-{job['hash'][:8]}.png")
        text = (job["visual"] or "").strip()
        if req.get("kind") == "kaynak" and req.get("url"):
            text = f"{text} ({req['url']})".strip()
        if not out.exists():
            stills.placeholder(out, row["id"], tag, text, track == 3, runner=self.runner)
        files = [{"file": str(out), "code": row["id"], "frames": None, "credit": None}]
        return self.asset(req, None if retry else job["hash"], "placeholder", track, files, note=note)

    def run_stock(self, jobs, summary):
        if not jobs:
            return
        out = Path(self.broll, "stok")
        before = {c["code"] for r in _read(str(out / "results.json"), {"requests": []})["requests"]
                  for c in r["candidates"]}
        batch = [{"code": j["code"], "query": j["req"]["query"], "orientation": "horizontal",
                  "count": stock_count(j["cov"], self.fps)} for j in jobs]
        bp = Path(self.broll, "stok-batch.json")
        _write(str(bp), batch)
        p = _tool(self.runner, FIND_STOCK, "--batch", bp, "--out", out)
        if p.returncode not in (0, 2):
            summary.notes.append(f"stok aracı: {_last(p.stderr) or p.returncode}")
        res = {r["code"]: r for r in _read(str(out / "results.json"), {"requests": []})["requests"]}
        for j in jobs:
            new = [c for c in res.get(j["code"], {}).get("candidates", []) if c["code"] not in before]
            if not new:
                j["asset"] = (self.placeholder(j, NOT_FOUND) if p.returncode in (0, 2) else
                              self.placeholder(j, f"stok aracı hata verdi: {_last(p.stderr)}", retry=True))
                continue
            summary.archive += sum(1 for c in new if c.get("from_cache"))
            files = [{"file": str(out / c["file"]), "code": c["code"],
                      "frames": math.floor(c["duration_s"] * self.fps) if c.get("duration_s") is not None else None,
                      "credit": c.get("credit")} for c in new]
            j["asset"] = self.asset(j["req"], j["hash"], "stock", 2, files)

    def run_graphic(self, jobs, summary):
        if not jobs:
            return
        out = Path(self.broll, "grafik")
        old = _read(str(out / "results.json"), {"notes": [], "renders": []})
        before, n_notes = {r["code"] for r in old["renders"]}, len(old["notes"])
        batch = []
        for j in jobs:
            req, t = j["req"], self.templates()[j["req"]["template"]]
            lo, hi = self.limits(t)
            j["frames"], j["max"] = min(max(j["cov"], lo), hi), hi
            row = {"template": req["template"], "code": j["code"], "fields": req.get("fields") or {},
                   "frames": j["frames"], "background": self.background(req)}
            if req.get("variant"):
                row["variant"] = req["variant"]
            if self.fps != BASE_FPS:
                row["fps"] = self.fps
            batch.append(row)
        bp = Path(self.broll, "grafik-batch.json")
        _write(str(bp), batch)
        p = _tool(self.runner, MAKE_GRAPHIC, "--batch", bp, "--out", out)
        res = _read(str(out / "results.json"), {"notes": [], "renders": []})
        notes = res["notes"][n_notes:]
        for j in jobs:
            pat = re.compile(re.escape(j["code"]) + r"-\d+")
            new = [r for r in res["renders"] if r["code"] not in before and pat.fullmatch(r["code"])]
            if not new:
                mine = [n.split(": ", 1)[1] for n in notes if n.startswith(j["code"] + ": ")]
                if mine:
                    j["asset"] = self.placeholder(j, f"{GRAPHIC_FAILED}: " + "; ".join(mine))
                else:
                    j["asset"] = self.placeholder(j, f"{GRAPHIC_FAILED}: {_last(p.stderr) or 'sonuç yok'}",
                                                  retry=True)
                continue
            r = new[-1]
            summary.archive += bool(r.get("from_archive"))
            video = out / r["file"]
            still = r.get("output") == "still"
            hold, hold_from, note = None, None, None
            if not still and j["cov"] > j["max"]:
                n = round(r["frames"] * POSTER_AT)
                hp = Path(self.broll, "stills", f"{r['code']}-hold-{n}.png")
                if hp.exists() or stills.frame_at(video, n, hp, runner=self.runner):
                    hold, hold_from = str(hp), n
                else:
                    note = "bekletme karesi alınamadı"
            files = [{"file": str(video), "code": r["code"], "frames": None if still else r["frames"],
                      "credit": "; ".join(r.get("sources") or []) or None}]
            track = 2 if r.get("background", self.background(j["req"])) else 3
            j["asset"] = self.asset(j["req"], j["hash"], "graphic", track, files, hold, note, hold_from)

    def run_kaynak(self, jobs):
        used = set()
        for j in jobs:
            base, n = j["code"], 1
            out = Path(self.broll, "kaynak", f"{base}.png")
            while out.exists() or out in used:  # never replace a delivered screenshot
                n += 1
                out = Path(self.broll, "kaynak", f"{base}-{n}.png")
            used.add(out)
            note = stills.screenshot(j["req"]["url"], out, runner=self.runner)
            if note:  # a page that did not open may open next time; a blocked one stays blocked
                j["asset"] = self.placeholder(j, note, retry=note == stills.FAILED)
                continue
            files = [{"file": str(out), "code": out.stem, "frames": None, "credit": j["req"]["url"]}]
            j["asset"] = self.asset(j["req"], j["hash"], "kaynak", 2, files)


def run(ep, runner=subprocess.run):
    rows_path, req_path = ep.path("broll", "rows.json"), ep.path("broll", "requests.json")
    if not os.path.exists(rows_path):
        raise FetchError(f"{rows_path} yok: önce 'broll.py align' çalıştırın")
    rows_json = _read(rows_path, {})
    requests = reqs.load(req_path).get("rows", {})
    fetched_path = ep.path("broll", "fetched.json")
    fetched = _read(fetched_path, {"units": "frames", "rows": {}})
    fetched["units"] = "frames"
    script_rows = {r.key: r for r in rows_mod.load(ep)}
    f = _Fetch(ep, runner)
    summary = Summary()

    jobs, current = [], []
    chapters = [rows_json["chapters"][n] for n in sorted(rows_json.get("chapters", {}), key=int)]
    for ch in chapters:
        for key, row in ch.get("rows", {}).items():
            if row is None:
                summary.not_found.append(script_rows[key].id if key in script_rows else key)
                continue
            current.append(key)
            old = list(fetched["rows"].get(key, []))
            cov = row["end"] - row["start"]
            row_reqs = requests.get(key, [])
            hashes = [request_hash(req, cov) for req in row_reqs]
            hits = []
            for h in hashes:
                hit = next((a for a in old if a.get("request_hash") == h), None)
                if hit is not None:
                    old.remove(hit)
                hits.append(hit)
            codes = _codes(row["id"], row_reqs, hits)
            for i, req in enumerate(row_reqs):
                job = {"key": key, "i": i, "req": req, "row": row, "cov": cov, "hash": hashes[i],
                       "code": codes[i], "visual": script_rows[key].visual if key in script_rows else "",
                       "asset": hits[i]}
                jobs.append(job)
                if hits[i] is not None:
                    hits[i]["code"] = codes[i]
                    summary.cached += 1
                    continue
                kind = req.get("kind")
                problems = reqs.validate(req, f.templates() if kind == "graphic" else {})
                job["todo"] = f"{INVALID}: " + "; ".join(problems) if problems else kind

    todo = [j for j in jobs if j["asset"] is None]
    try:
        for j in todo:
            t = j["todo"]
            if t.startswith(INVALID):
                j["asset"] = f.placeholder(j, t)
            elif t == "placeholder":
                req = j["req"]
                j["asset"] = f.placeholder(j, req["reason"] + (f": {req['need']}" if req.get("need") else ""))
        f.run_stock([j for j in todo if j["todo"] == "stock"], summary)
        f.run_graphic([j for j in todo if j["todo"] == "graphic"], summary)
        f.run_kaynak([j for j in todo if j["todo"] == "kaynak"])
    finally:  # rows done so far keep what they got, even when a later step fails
        for j in todo:
            if j["asset"] is not None:
                j["asset"]["code"] = j["code"]
        for key in current:
            assets = [j["asset"] for j in jobs if j["key"] == key]
            if all(a is not None for a in assets):
                fetched["rows"][key] = assets
        _write(fetched_path, fetched)
    summary.fetched = len(todo)
    for key in current:
        for a in fetched["rows"][key]:
            if a["kind"] == "placeholder":
                summary.placeholders[(a["note"] or "?").split(": ", 1)[0]] += 1
    return summary
