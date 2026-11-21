#!/usr/bin/env python3
"""Shorts steps that talk to DaVinci Resolve. Run through the rough cutter's rv.sh:
  bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh .claude/skills/cutting-shorts/scripts/shorts_resolve.py read EP
read: per eligible chapter (frozen A-roll + signed-off B-roll) read the frozen A-roll timeline's V1 layout and the
      "<chapter timeline> B-roll" timeline's V2+ items, read-only (no SetCurrentTimeline, no setters, no markers):
      shorts/layout/ch<N>.json (the B-roll skill's layout format) and shorts/broll/ch<N>.json
      = {"units": "frames", "timeline", "items": [{track,start,end,file,src_in,src_out,props,kind}]}.
review: builds "<prefix> short adayları" (bin "<prefix> Shorts", 16:9) nesting the eligible chapters' B-roll
      timelines, with one Fuchsia ranged marker per candidate piece and teaser. Only that timeline is touched.
accept: reads that timeline's markers back (Green = accepted, moved/resized = new ranges) into
      shorts/candidates.json, re-snaps, then rebuilds the review timeline.
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
import cands  # noqa: E402
import eligible  # noqa: E402
import episode  # noqa: E402
import review  # noqa: E402
import shorts  # noqa: E402
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


def review_name(prefix):
    return f"{prefix} short adayları"


def _chapter_frames(ep, chapters_ok):
    out = {}
    for n in chapters_ok:
        with open(ep.path("shorts", "layout", f"ch{n}.json"), encoding="utf-8") as f:
            out[n] = json.load(f)["frames"]
    return out


def _marker_list(tl):
    return [{"frameId": fr, **m} for fr, m in sorted((tl.GetMarkers() or {}).items())]


def build_review(ep, p, data):
    """(Re)create the review timeline of OUR prefix only and put the candidates' markers on it."""
    pre = ep.m["prefix"]
    chapters_ok = eligible.chapters(ep)
    with open(ep.path("sections.json"), encoding="utf-8") as f:
        titles = json.load(f)["chapters"]
    try:
        frames = _chapter_frames(ep, chapters_ok)
    except FileNotFoundError as err:
        sys.exit(f"{err} yok: önce 'read' ile bölümlerin yerleşimini okuyun")
    offs = review.offsets(frames, chapters_ok)
    mp = p.GetMediaPool()
    name = review_name(pre)
    old = br.timeline_by_name(p, name)
    if old is not None:
        mp.DeleteTimelines([old])
    top = sync.subfolder(mp, mp.GetRootFolder(), f"{pre} Shorts")
    mp.SetCurrentFolder(top)
    tl = mp.CreateEmptyTimeline(name)
    mp.SetCurrentFolder(mp.GetRootFolder())
    if not tl:
        sys.exit(f"'{name}' oluşturulamadı")
    br.make_current(p, tl)
    for n in chapters_ok:
        src = glue.broll_name(episode.chapter_timeline_name(pre, titles[n - 1], n - 1))
        child = br.timeline_by_name(p, src)
        mpi = child.GetMediaPoolItem() if child is not None else None
        if mpi is None or not mp.AppendToTimeline([{"mediaPoolItem": mpi}]):
            sys.exit(f"Bölüm {n}: '{src}' iç içe eklenemedi; durduruldu")
        got = int(mpi.GetClipProperty("Frames"))
        if got != frames[n]:
            print(f"Bölüm {n}: '{src}' {got} kare, layout'ta {frames[n]}; işaretçiler kayabilir", file=sys.stderr)
    total = sum(frames.values())
    placed = 0
    for m in review.markers(data, offs):
        fr = m["frameId"]
        if not 0 <= fr < total or fr + m["duration"] > total:
            print(f"{m['customData']}: aralık zaman çizelgesinin dışında, işaretçi eklenmedi", file=sys.stderr)
            continue
        ok = False
        for bump in range(0, 5):  # a second marker on an occupied frame is refused
            if tl.AddMarker(fr + bump, m["color"], m["name"], m["note"], m["duration"], m["customData"]):
                ok = True
                if bump:
                    print(f"{m['customData']}: kare dolu, işaretçi {bump} kare kaydırıldı", file=sys.stderr)
                break
        if not ok:
            print(f"{m['customData']}: işaretçi eklenemedi", file=sys.stderr)
            continue
        placed += 1
    print(f"{name}: {len(chapters_ok)} bölüm, {total} kare, {placed} işaretçi", file=sys.stderr)
    return tl


def _load(ep):
    path = ep.path("shorts", "candidates.json")
    if not os.path.exists(path):
        sys.exit(f"{path} yok: önce adayları yazın (shorts.py check)")
    return path, cands.load(path)


def cmd_review(a):
    ep = episode.Episode(a.episode)
    if not eligible.chapters(ep):
        sys.exit("Uygun bölüm yok: hem 'frozen' hem 'broll_frozen' içinde olmalı (episode.json)")
    _, data = _load(ep)
    _, p = br.connect()
    build_review(ep, p, data)
    print("Adaylar Fuchsia işaretçi: kabul için işaretçiyi Green yapın, aralığı sürükleyip değiştirebilirsiniz; "
          "sonra 'accept' çalıştırın.", file=sys.stderr)
    return 0


def cmd_accept(a):
    ep = episode.Episode(a.episode)
    chapters_ok = eligible.chapters(ep)
    path, data = _load(ep)
    _, p = br.connect()
    tl = br.timeline_by_name(p, review_name(ep.m["prefix"]))
    if tl is None:
        sys.exit(f"'{review_name(ep.m['prefix'])}' bulunamadı: önce 'review' çalıştırın")
    marks = _marker_list(tl)  # read BEFORE the timeline is rebuilt
    frames = _chapter_frames(ep, chapters_ok)
    offs = review.offsets(frames, chapters_ok)
    data, notes = review.read_back(data, marks, offs, frames)
    need = sorted({r["chapter"] for c in data["candidates"] for r in c.get("pieces", []) + [c.get("teaser") or {}]
                   if r.get("chapter") in chapters_ok})
    data, cnotes, errors = cands.check(data, shorts._words(ep, need), chapters_ok, ep.fps)
    cands.save(path, data)
    for n in notes + cnotes:
        print(n, file=sys.stderr)
    for cid, msgs in errors.items():
        for m in msgs:
            print(f"{cid}: {m}", file=sys.stderr)
    build_review(ep, p, data)
    acc = [c["id"] for c in data["candidates"] if c.get("accepted")]
    print("Kabul edilen adaylar: " + (", ".join(acc) if acc else "yok"))
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("read")
    s.add_argument("episode")
    s.set_defaults(fn=cmd_read)
    for name, fn in (("review", cmd_review), ("accept", cmd_accept)):
        s = sub.add_parser(name)
        s.add_argument("episode")
        s.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
