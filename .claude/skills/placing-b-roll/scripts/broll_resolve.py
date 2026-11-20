#!/usr/bin/env python3
"""B-roll steps that talk to DaVinci Resolve. Run through the rough cutter's rv.sh:
  bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh .claude/skills/placing-b-roll/scripts/broll_resolve.py layout EP
layout: read each frozen chapter timeline's V1 items (read-only: no SetCurrentTimeline, no setters) and
        write broll/layout/ch<N>.json = {"units": "frames", "timeline", "frames", "pieces": [[rec, clip, a, b]]}.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import episode  # noqa: E402


def connect():
    """(resolve, project) of the running Resolve; exits with a message when it isn't reachable."""
    try:
        import DaVinciResolveScript as d
    except ImportError:
        sys.exit("DaVinciResolveScript bulunamadı: rv.sh ile çalıştırın")
    r = d.scriptapp("Resolve")
    if r is None:
        sys.exit("Resolve'a bağlanılamadı: Resolve açık mı, harici betik erişimi 'Local' mi?")
    p = r.GetProjectManager().GetCurrentProject()
    if p is None:
        sys.exit("Resolve'da açık proje yok")
    return r, p


def timeline_by_name(project, name):
    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if tl.GetName() == name:
            return tl
    return None


def layout_from_items(name, tl_start, items):
    """V1 items -> layout dict; rec is relative to the timeline start, [a, b) in source frames.
    frames = end of the last V1 item (avoids relying on whether GetEndFrame() is inclusive)."""
    pieces = []
    for it in items:
        a, m = it.GetLeftOffset(), it.GetMediaPoolItem()  # generators/titles have no media-pool item
        pieces.append([it.GetStart() - tl_start, m.GetName() if m else None, a, a + it.GetDuration()])
    pieces.sort(key=lambda p: p[0])
    return {"units": "frames", "timeline": name, "frames": max((p[0] + p[3] - p[2] for p in pieces), default=0), "pieces": pieces}


def cmd_layout(a):
    ep = episode.Episode(a.episode)
    frozen = sorted(ep.m.get("frozen", []))
    if not frozen:
        sys.exit("Dondurulmuş bölüm yok (episode.json 'frozen')")
    with open(ep.path("sections.json"), encoding="utf-8") as f:
        chapters = json.load(f)["chapters"]
    _, p = connect()
    os.makedirs(ep.path("broll", "layout"), exist_ok=True)
    for n in frozen:
        name = episode.chapter_timeline_name(ep.m["prefix"], chapters[n - 1], n - 1)
        tl = timeline_by_name(p, name)
        if tl is None:
            sys.exit(f"Bölüm {n}: '{name}' zaman çizelgesi bulunamadı")
        lay = layout_from_items(name, tl.GetStartFrame(), tl.GetItemListInTrack("video", 1) or [])
        out = ep.path("broll", "layout", f"ch{n}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(lay, f, ensure_ascii=False, indent=1)
        print(f"ch{n} '{name}': {len(lay['pieces'])} parça, {lay['frames']} kare -> {out}", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("layout", help="dondurulmuş bölümlerin V1 yerleşimini oku (salt okunur)")
    s.add_argument("episode")
    s.set_defaults(fn=cmd_layout)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
