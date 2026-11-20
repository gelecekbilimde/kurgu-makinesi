#!/usr/bin/env python3
"""B-roll placement tools. Usage: broll.py requests EP"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import episode  # noqa: E402
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("requests", help="B-roll isteklerini hazırla (ARŞİV/KAYNAK otomatik)")
    p.add_argument("episode")
    p.set_defaults(fn=cmd_requests)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
