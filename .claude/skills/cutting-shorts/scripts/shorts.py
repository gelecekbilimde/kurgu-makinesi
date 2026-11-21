#!/usr/bin/env python3
"""Shorts tools. Usage: shorts.py candidates EP | check EP | prepare EP [ID...] | freeze EP ID... | unfreeze EP ID...
candidates: sentences + script rows of the eligible chapters (needs shorts/layout/chN.json) for the candidate pass.
check: validate and snap shorts/candidates.json. prepare: face crop, teaser cut-out, graphics, captions and
shorts/<id>/assets.json of the accepted, not frozen candidates. freeze/unfreeze: a frozen candidate is never rebuilt."""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "placing-b-roll", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import align  # noqa: E402
import cands  # noqa: E402
import captions  # noqa: E402
import eligible  # noqa: E402
import episode  # noqa: E402
import graphics  # noqa: E402
import mapping  # noqa: E402
import rows as rows_mod  # noqa: E402
import stills  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
VENV_PY = os.path.join(REPO, ".venv", "bin", "python")
MEDIA = os.path.join(HERE, "shorts_media.py")
MAKE_GRAPHIC = os.path.join(HERE, "..", "..", "making-graphics", "scripts", "make_graphic.py")
REQS = ".claude/skills/cutting-shorts/requirements.txt"
VERTICAL = (1080, 1920)
NO_TITLE = "episode.json'da 'title' yok (bitiş kartı için gerekli)"


def _words(ep, chapters, raw=False):
    """{chapter: words} from shorts/layout/chN.json; FileNotFoundError names the missing layout."""
    out = {}
    for n in chapters:
        lp = ep.path("shorts", "layout", f"ch{n}.json")
        if not os.path.exists(lp):
            raise FileNotFoundError(lp)
        with open(lp, encoding="utf-8") as f:
            out[n] = align.chapter_words(ep, json.load(f), raw=raw)
    return out


def cmd_candidates(a):
    ep = episode.Episode(a.episode)
    chs = eligible.chapters(ep)
    if not chs:
        print("İmzalı bölüm yok: A-roll ve B-roll'u dondurulmuş bölüm gerekli.", file=sys.stderr)
        return 1
    try:
        words = _words(ep, chs, raw=True)
    except FileNotFoundError as err:
        print(f"{err} yok: önce bölümlerin yerleşimini Resolve'dan okuyun", file=sys.stderr)
        return 1
    sents = {"units": "frames", "chapters": {str(n): eligible.sentences(words[n], ep.fps) for n in chs}}
    path = ep.path("shorts", "sentences.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sents, f, ensure_ascii=False, indent=1)
    all_rows = rows_mod.load(ep)
    rows = {str(n): [{"id": r.id, "ses": r.ses, "visual": r.visual} for r in all_rows if r.chapter == n - 1]
            for n in chs}
    print(f"{sum(len(v) for v in sents['chapters'].values())} cümle -> {path}", file=sys.stderr)
    print(json.dumps({"sentences": sents, "rows": rows}, ensure_ascii=False, indent=1))
    return 0


def cmd_check(a):
    ep = episode.Episode(a.episode)
    path = ep.path("shorts", "candidates.json")
    if not os.path.exists(path):
        print(f"{path} yok", file=sys.stderr)
        return 1
    data = cands.load(path)
    chs = eligible.chapters(ep)
    need = sorted({p["chapter"] for c in data["candidates"] for p in c.get("pieces", []) if p["chapter"] in chs}
                  | {c["teaser"]["chapter"] for c in data["candidates"] if c.get("teaser", {}).get("chapter") in chs})
    try:
        words = _words(ep, need)
    except FileNotFoundError as err:
        print(f"{err} yok: önce bölümlerin yerleşimini Resolve'dan okuyun", file=sys.stderr)
        return 1
    data, notes, errors = cands.check(data, words, chs, ep.fps)
    cands.save(path, data)
    for n in notes:
        print(n, file=sys.stderr)
    for cid, msgs in errors.items():
        for m in msgs:
            print(f"{cid}: {m}", file=sys.stderr)
    print(f"{len(data['candidates'])} aday, {len(errors)} hatalı -> {path}", file=sys.stderr)
    return 1 if errors else 0


def cmd_freeze(a):
    ep = episode.Episode(a.episode)
    path = ep.path("shorts", "candidates.json")
    data = cands.load(path)
    by_id = {c.get("id"): c for c in data["candidates"]}
    bad = [i for i in a.ids if i not in by_id]
    if bad:
        print(f"Bilinmeyen aday: {', '.join(bad)}", file=sys.stderr)
        return 1
    for i in a.ids:
        by_id[i]["frozen"] = a.cmd == "freeze"
    cands.save(path, data)
    print("Dondurulmuş adaylar: " + ", ".join(c["id"] for c in data["candidates"] if c.get("frozen")), file=sys.stderr)
    return 0


def _read(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _last(text):
    return ((text or "").strip().splitlines() or [""])[-1]


def short_words(layout, words_by_ch, rows_by_ch):
    """The short's words in short frames ({"start","end","text"}), clamped to their segment, spelled as in the
    chapter's script rows (the transcript's own text, without its padding spaces, where unmatched).
    words_by_ch: {chapter: [(start, end, norm, raw)]} on the chapter timeline."""
    spelled = {}
    for ch, ws in words_by_ch.items():
        spelled[ch] = list(zip(ws, captions.spell([{"text": w[3].strip()} for w in ws], rows_by_ch.get(ch, []))))
    out = []
    for g in layout["segments"]:
        for (s, e, _n, _raw), text in spelled[g["chapter"]]:
            if s < g["ch_end"] and g["ch_start"] < e:
                out.append({"start": g["rec"] + max(s, g["ch_start"]) - g["ch_start"],
                            "end": g["rec"] + min(e, g["ch_end"]) - g["ch_start"], "text": text})
    return out


class Prep:
    """What prepare reads once for every short: chapters, words, script rows, templates, B-roll renders."""

    def __init__(self, ep, chapters, runner):
        self.ep, self.runner = ep, runner
        self.layouts, self.brolls = {}, {}
        for n in chapters:
            for kind, into in (("layout", self.layouts), ("broll", self.brolls)):
                p = ep.path("shorts", kind, f"ch{n}.json")
                if not os.path.exists(p):
                    raise FileNotFoundError(p)
                into[n] = _read(p, None)
        self.words = {n: align.chapter_words(ep, self.layouts[n], raw=True) for n in chapters}
        rows = rows_mod.load(ep)
        self.rows = {n: [r for r in rows if r.chapter == n - 1] for n in chapters}
        p = runner(["python3", MAKE_GRAPHIC, "--list", "--json"], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"şablon listesi alınamadı: {_last(p.stderr)}")
        self.templates = json.loads(p.stdout)
        self.archive = _read(ep.path("broll", "grafik", "results.json"), {"renders": []})
        fetched = _read(ep.path("broll", "fetched.json"), {"rows": {}})
        self.hold_from = {a["hold"]: a["hold_from"] for assets in fetched.get("rows", {}).values() for a in assets
                          if a.get("hold") and a.get("hold_from") is not None}
        self.clips = {c["clip"]: c for c in ep.clips(all_=True)}


def _media(prep, step, job):
    p = prep.runner([VENV_PY, MEDIA, step, job], capture_output=True, text=True)
    if p.returncode != 0:
        hint = f" (kurulum: .venv/bin/pip install -r {REQS})" if "ModuleNotFoundError" in (p.stderr or "") else ""
        raise RuntimeError(f"shorts_media.py {step}: {_last(p.stderr) or 'hata'}{hint}")


def _render(prep, d, rows):
    """Batch-render rows into d/grafik -> ({code: abs file}, notes)."""
    if not rows:
        return {}, []
    out = os.path.join(d, "grafik")
    before = {r["code"] for r in _read(os.path.join(out, "results.json"), {"renders": []})["renders"]}
    bp = os.path.join(d, "grafik-batch.json")
    _write(bp, [{k: v for k, v in r.items() if k not in ("replaces", "role", "range")} for r in rows])
    p = prep.runner(["python3", MAKE_GRAPHIC, "--batch", bp, "--out", out], capture_output=True, text=True)
    res = _read(os.path.join(out, "results.json"), {"renders": []})
    files, notes = {}, []
    for r in rows:
        pat = re.compile(re.escape(r["code"]) + r"-\d+")
        new = [x for x in res["renders"] if x["code"] not in before and pat.fullmatch(x["code"])]
        if new:
            files[r["code"]] = os.path.join(out, new[-1]["file"])
        else:
            notes.append(f"{r['code']} ({r['template']}) üretilemedi: {_last(p.stderr) or 'sonuç yok'}")
    return files, notes


def prepare_one(prep, cand):
    """Media, graphics, captions and assets.json of one short -> summary lines."""
    ep, fps = prep.ep, prep.ep.fps
    d = ep.path("shorts", cand["id"])
    os.makedirs(d, exist_ok=True)
    layout = mapping.short_layout(cand, prep.layouts, prep.brolls, fps, graphics.end_card_frames(fps))
    words = short_words(layout, {n: prep.words[n] for n in {g["chapter"] for g in layout["segments"]}}, prep.rows)
    cues = captions.cues(words, fps, avoid=[layout["teaser"], layout["end_card"]])
    srt = os.path.join(d, "captions.srt")
    with open(srt, "w", encoding="utf-8") as f:
        f.write(captions.srt(cues, fps))

    items = [dict(v, camera=prep.clips[v["clip"]]["camera"]) for v in layout["v1"]]
    teaser_items = [i for i, v in enumerate(items) if v["segment"] == 0]
    cutouts = [{"item": i, "file": os.path.join(d, "teaser-cutout.mov" if len(teaser_items) == 1
                                                 else f"teaser-cutout-{k}.mov")}
               for k, i in enumerate(teaser_items, 1)]
    job = os.path.join(d, "media.json")
    _write(job, {"units": "frames", "fps": fps, "items": items, "cutouts": cutouts})
    _media(prep, "faces", job)
    _media(prep, "matte", job)

    rows, placeholders, needed = graphics.requests(ep, cand, layout, prep.templates, prep.archive, words)
    files, notes = _render(prep, d, rows)
    replace = {}
    for r in rows:
        if "replaces" in r and r["code"] in files:  # a B-roll graphic re-rendered vertical
            replace[r["replaces"]] = files[r["code"]]
    n_vertical = len(replace)
    for it in layout["broll"]:  # Ruling 2: the vertical hold still of a re-rendered graphic, same frame
        if it["kind"] != "still" or it.get("hold_of") not in replace or it["file"] in replace:
            continue
        m = re.search(r"-hold-(\d+)\.png$", it["file"])
        n = prep.hold_from.get(it["file"], int(m.group(1)) if m else None)
        new = replace[it["hold_of"]]
        out = os.path.join(d, "stills", f"{os.path.splitext(os.path.basename(new))[0]}-hold-{n}.png")
        if n is not None and (os.path.exists(out) or stills.frame_at(new, n, out, runner=prep.runner)):
            replace[it["file"]] = out
        else:
            notes.append(f"{os.path.basename(it['file'])}: dikey bekletme karesi alınamadı")
    own = []
    for r in rows:
        if "role" in r and r["code"] in files:
            own.append({"role": r["role"], "file": files[r["code"]], "range": r["range"], "placeholder": False,
                        "vertical": bool(r.get("vertical"))})
        elif "role" in r:  # the template exists but the render failed: a placeholder keeps the slot visible
            placeholders.append({"template": r["template"], "role": r["role"], "range": r["range"],
                                 "overlay": r["role"] != "end-card", "text": r["template"]})
    for p in placeholders:
        out = os.path.join(d, "stills", f"{p['role']}.png")
        stills.placeholder(out, cand["id"], p["template"], p["text"], p["overlay"], runner=prep.runner,
                           size=VERTICAL)
        own.append({"role": p["role"], "file": out, "range": p["range"], "placeholder": True, "vertical": True})

    _write(os.path.join(d, "assets.json"), {
        "units": "frames", "id": cand["id"], "end_card_frames": graphics.end_card_frames(fps),
        "crop": os.path.join(d, "crop.json"), "captions": srt, "cues": cues,
        "teaser_cutout": [{"file": c["file"], "rec": items[c["item"]]["rec"],
                           "end": items[c["item"]]["rec"] + items[c["item"]]["src_out"] - items[c["item"]]["src_in"]}
                          for c in cutouts],
        "graphics": own, "replace": replace, "needed": needed})
    lines = [f"{cand['id']}: {len(items)} kamera parçası, {len(cues)} altyazı, {n_vertical} dikey B-roll grafiği, "
             f"{len(placeholders)} yer tutucu -> {os.path.join(d, 'assets.json')}"]
    return lines + [f"  Not: {n}" for n in notes], needed


def prepare(ep, ids, runner=subprocess.run):
    """prepare for the accepted, not frozen candidates (or the named ones) -> exit code."""
    if not ep.m.get("title"):
        print(NO_TITLE, file=sys.stderr)
        return 1
    data = cands.load(ep.path("shorts", "candidates.json"))
    by_id = {c.get("id"): c for c in data["candidates"]}
    bad = [i for i in ids if i not in by_id]
    if bad:
        print(f"Bilinmeyen aday: {', '.join(bad)}", file=sys.stderr)
        return 1
    rc, todo = 0, []
    chs = eligible.chapters(ep)
    for c in ([by_id[i] for i in ids] if ids else data["candidates"]):
        if c.get("frozen"):
            if ids:
                print(f"{c['id']}: dondurulmuş, atlandı", file=sys.stderr)
        elif not c.get("accepted"):
            if ids:
                print(f"{c['id']}: kabul edilmemiş (inceleme zaman çizelgesinde yeşil değil)", file=sys.stderr)
                rc = 1
        elif any(r["chapter"] not in chs for r in c["pieces"] + [c["teaser"]]):
            print(f"{c['id']}: imzalı olmayan bölüm kullanıyor (A-roll ve B-roll dondurulmuş olmalı)", file=sys.stderr)
            rc = 1
        else:
            todo.append(c)
    if not todo:
        print("Hazırlanacak short yok: kabul edilmiş, dondurulmamış aday gerekli.", file=sys.stderr)
        return rc or 1
    chapters = sorted({r["chapter"] for c in todo for r in c["pieces"] + [c["teaser"]]})
    try:
        prep = Prep(ep, chapters, runner)
    except FileNotFoundError as err:
        print(f"{err} yok: önce bölümlerin yerleşimini Resolve'dan okuyun", file=sys.stderr)
        return 1
    except RuntimeError as err:
        print(f"Hata: {err}", file=sys.stderr)
        return 1
    needs = []
    for c in todo:
        try:
            lines, needed = prepare_one(prep, c)
        except (RuntimeError, stills.StillError) as err:
            print(f"{c['id']}: hata: {err}", file=sys.stderr)
            rc = 1
            continue
        for line in lines:
            print(line, file=sys.stderr)
        needs += [n for n in needed if n not in needs]
    if needs:
        print("Gereken şablonlar:", file=sys.stderr)
        for n in needs:
            print(f"  - {n}", file=sys.stderr)
    else:
        print("Gereken şablonlar: yok", file=sys.stderr)
    return rc


def cmd_prepare(a):
    return prepare(episode.Episode(a.episode), a.ids)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("candidates", cmd_candidates, "imzalı bölümlerin cümleleri ve satırları (layout gerekir)"),
                            ("check", cmd_check, "adayları doğrula ve kelime boşluklarına oturt")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("episode")
        p.set_defaults(fn=fn)
    p = sub.add_parser("prepare", help="kabul edilmiş shortların yüz kırpması, teaser kesiği, grafikleri ve altyazısı")
    p.add_argument("episode")
    p.add_argument("ids", nargs="*")
    p.set_defaults(fn=cmd_prepare)
    for name, help_ in (("freeze", "adayı dondur"), ("unfreeze", "adayın dondurmasını kaldır")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("episode")
        p.add_argument("ids", nargs="+")
        p.set_defaults(fn=cmd_freeze)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
