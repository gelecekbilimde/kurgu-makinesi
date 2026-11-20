#!/usr/bin/env python3
"""B-roll placement tools. Usage: broll.py requests EP | broll.py align EP | broll.py fetch EP"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import align  # noqa: E402
import episode  # noqa: E402
import fetch  # noqa: E402
import reqs  # noqa: E402
import rows as rows_mod  # noqa: E402

TEMPLATES_CMD = "python3 .claude/skills/making-graphics/scripts/make_graphic.py --list --json"


def cmd_requests(a):
    ep = episode.Episode(a.episode)
    frozen = set(ep.m.get("frozen", []))
    todo = rows_mod.broll_rows(rows_mod.load(ep), frozen)
    path = ep.path("broll", "requests.json")
    data = reqs.load(path)
    data.setdefault("units", "frames")
    store = data.setdefault("rows", {})
    for r in todo:
        cur = store.setdefault(r.key, [])
        have = {q.get("tag") for q in cur}
        cur.extend(q for q in reqs.autofill(r) if q["tag"] not in have)
    reqs.save(path, data)
    pend = reqs.pending(todo, data)
    if not todo:
        print("Dondurulmuş bölümde B-roll satırı yok.", file=sys.stderr)
    print(f"{len(todo)} satır, {len(pend)} istek bekliyor -> {path}", file=sys.stderr)
    print(json.dumps([{"id": r.id, "key": r.key, "tags": r.tags, "visual": r.visual, "links": r.links,
                       "refs": r.refs, "est_s": r.est_s} for r in pend], ensure_ascii=False, indent=1))
    print(f"Şablonlar: {TEMPLATES_CMD}", file=sys.stderr)
    return 0


def cmd_align(a):
    ep = episode.Episode(a.episode)
    frozen = sorted(ep.m.get("frozen", []))
    all_rows = rows_mod.load(ep)
    out = {"units": "frames", "fps": ep.fps, "chapters": {}}
    for n in frozen:
        lp = ep.path("broll", "layout", f"ch{n}.json")
        if not os.path.exists(lp):
            print(f"{lp} yok: önce 'broll_resolve.py layout' çalıştırın", file=sys.stderr)
            return 1
        with open(lp, encoding="utf-8") as f:
            layout = json.load(f)
        words = align.chapter_words(ep, layout)
        ch_rows = [r for r in all_rows if r.chapter == n - 1]
        cov = align.coverage(ch_rows, align.align_rows(ch_rows, words), words)
        ids = {r.key: r.id for r in ch_rows}
        out["chapters"][str(n)] = {"timeline": layout["timeline"],
                                   "rows": {k: v and {"id": ids[k], **v} for k, v in cov.items()}}
        miss = [ids[k] for k, v in cov.items() if v is None]
        print(f"ch{n}: {len(cov) - len(miss)}/{len(cov)} B-roll satırı bulundu"
              + (f"; bulunamayan: {', '.join(miss)}" if miss else ""), file=sys.stderr)
    path = ep.path("broll", "rows.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"-> {path}", file=sys.stderr)
    return 0


def cmd_fetch(a):
    ep = episode.Episode(a.episode)
    try:
        summary = fetch.run(ep)
    except (fetch.FetchError, fetch.stills.StillError) as err:
        print(f"Hata: {err}", file=sys.stderr)
        return 1
    for line in summary.lines():
        print(line, file=sys.stderr)
    print(f"-> {ep.path('broll', 'fetched.json')}", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("requests", help="B-roll isteklerini hazırla (ARŞİV/KAYNAK otomatik)")
    p.add_argument("episode")
    p.set_defaults(fn=cmd_requests)
    p = sub.add_parser("align", help="satırları dondurulmuş bölümlerin karelerine eşle (layout gerekir)")
    p.add_argument("episode")
    p.set_defaults(fn=cmd_align)
    p = sub.add_parser("fetch", help="stok, grafik, ekran görüntüsü ve yer tutucuları getir (align gerekir)")
    p.add_argument("episode")
    p.set_defaults(fn=cmd_fetch)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
