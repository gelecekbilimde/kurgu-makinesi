#!/usr/bin/env python3
"""Shorts tools. Usage: shorts.py candidates EP | check EP | freeze EP ID... | unfreeze EP ID...
candidates: sentences + script rows of the eligible chapters (needs shorts/layout/chN.json) for the candidate pass.
check: validate and snap shorts/candidates.json. freeze/unfreeze: a frozen candidate is never rebuilt."""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "placing-b-roll", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import align  # noqa: E402
import cands  # noqa: E402
import eligible  # noqa: E402
import episode  # noqa: E402
import rows as rows_mod  # noqa: E402


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("candidates", cmd_candidates, "imzalı bölümlerin cümleleri ve satırları (layout gerekir)"),
                            ("check", cmd_check, "adayları doğrula ve kelime boşluklarına oturt")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("episode")
        p.set_defaults(fn=fn)
    for name, help_ in (("freeze", "adayı dondur"), ("unfreeze", "adayın dondurmasını kaldır")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("episode")
        p.add_argument("ids", nargs="+")
        p.set_defaults(fn=cmd_freeze)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
