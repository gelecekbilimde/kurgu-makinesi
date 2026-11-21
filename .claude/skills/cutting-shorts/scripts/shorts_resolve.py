#!/usr/bin/env python3
"""Shorts steps that talk to DaVinci Resolve. Run through the rough cutter's rv.sh:
  bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh .claude/skills/cutting-shorts/scripts/shorts_resolve.py read EP
read: per eligible chapter (frozen A-roll + signed-off B-roll) read the frozen A-roll timeline's V1 layout and the
      "<chapter timeline> B-roll" timeline's V2+ items, read-only (no SetCurrentTimeline, no setters, no markers):
      shorts/layout/ch<N>.json (the B-roll skill's layout format) and shorts/broll/ch<N>.json
      = {"units": "frames", "timeline", "items": [{track,start,end,file,src_in,src_out,props,kind}]}.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "placing-b-roll", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import broll_resolve as br  # noqa: E402
import build as glue  # noqa: E402
import eligible  # noqa: E402
import episode  # noqa: E402
import sync  # noqa: E402

KEYS = ("track", "start", "end", "file", "src_in", "src_out", "props")


def _file_index(fetched):
    """canonical file -> (asset kind, graphic file it is the hold still of or None)"""
    files, holds = {}, {}
    for assets in fetched.get("rows", {}).values():
        for a in assets:
            for c in a.get("files") or []:
                files[glue.canon(c["file"])] = a.get("kind")
            if a.get("hold") and a.get("files"):
                holds[glue.canon(a["hold"])] = glue.canon(a["files"][0]["file"])
    return files, holds


def read_items(seen, fetched):
    """B-roll timeline items (glue.seen_item dicts) -> short items with a "kind": the fetched asset's kind,
    "still" (+ "hold_of": the graphic's file) for a graphic's hold still, "editor" for a file never fetched."""
    files, holds = _file_index(fetched)
    out = []
    for s in seen:
        f = glue.canon(s["file"])
        it = {k: s[k] for k in KEYS}
        if f in holds:
            it["kind"], it["hold_of"] = "still", holds[f]
        else:
            it["kind"] = files.get(f) or "editor"
        out.append(it)
    return out


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def cmd_read(a):
    ep = episode.Episode(a.episode)
    chapters_ok = eligible.chapters(ep)
    if not chapters_ok:
        sys.exit("Uygun bölüm yok: hem 'frozen' hem 'broll_frozen' içinde olmalı (episode.json)")
    with open(ep.path("sections.json"), encoding="utf-8") as f:
        chapters = json.load(f)["chapters"]
    fp = ep.path("broll", "fetched.json")
    fetched = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {"rows": {}}
    fps = ep.m["fps"]
    _, p = br.connect()
    for n in chapters_ok:
        name = episode.chapter_timeline_name(ep.m["prefix"], chapters[n - 1], n - 1)
        tl = br.timeline_by_name(p, name)
        if tl is None:
            sys.exit(f"Bölüm {n}: '{name}' zaman çizelgesi bulunamadı")
        bname = glue.broll_name(name)
        btl = br.timeline_by_name(p, bname)
        if btl is None:
            sys.exit(f"Bölüm {n}: '{bname}' zaman çizelgesi bulunamadı")
        lay = br.layout_from_items(name, tl.GetStartFrame(), tl.GetItemListInTrack("video", 1) or [])
        seen, _ = sync.track_items(btl, btl.GetStartFrame(), fps, tracks=None)
        items = sorted(read_items(seen, fetched), key=lambda i: (i["start"], i["track"]))
        _write(ep.path("shorts", "layout", f"ch{n}.json"), lay)
        _write(ep.path("shorts", "broll", f"ch{n}.json"), {"units": "frames", "timeline": bname, "items": items})
        print(f"ch{n} '{name}': {len(lay['pieces'])} parça; '{bname}': {len(items)} B-roll öğesi", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("read")
    s.add_argument("episode")
    s.set_defaults(fn=cmd_read)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
