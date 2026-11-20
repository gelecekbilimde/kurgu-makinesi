#!/usr/bin/env python3
"""B-roll steps that talk to DaVinci Resolve. Run through the rough cutter's rv.sh:
  bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh .claude/skills/placing-b-roll/scripts/broll_resolve.py layout EP
layout: read each frozen chapter timeline's V1 items (read-only: no SetCurrentTimeline, no setters) and
        write broll/layout/ch<N>.json = {"units": "frames", "timeline", "frames", "pieces": [[rec, clip, a, b]]}.
build [N ...]: per frozen chapter not in "broll_frozen" (all, or only N ...): create or update
        "<chapter timeline> B-roll" (V1 = the frozen chapter nested; V2/V3 = B-roll), keeping every editor change
        (plan.readback/actions); unused candidates go to the bin "<prefix> B-roll/ch<N>/<row id>";
        writes broll/plan.json and broll/kaynaklar.txt and prints the summary.
master: rebuild "<prefix> B-roll": per chapter, its B-roll timeline, else the frozen A-roll chapter, nested.
The frozen A-roll chapter timelines are only read: never made current, never changed.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import build as glue  # noqa: E402
import credits  # noqa: E402
import episode  # noqa: E402
import plan  # noqa: E402
import rows as rows_mod  # noqa: E402


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


def _read(path, default=None):
    if not os.path.exists(path):
        if default is None:
            sys.exit(f"{path} yok")
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def subfolder(mp, parent, name):
    for f in parent.GetSubFolderList() or []:
        if f.GetName() == name:
            return f
    f = mp.AddSubFolder(parent, name)
    if not f:
        sys.exit(f"'{name}' klasörü oluşturulamadı")
    return f


def index_paths(folder, out=None):
    """canonical file path -> media-pool item, for every clip under folder (recursive)"""
    out = {} if out is None else out
    for c in folder.GetClipList() or []:
        fp = c.GetClipProperty("File Path")
        if fp:
            out.setdefault(glue.canon(fp), c)
    for f in folder.GetSubFolderList() or []:
        index_paths(f, out)
    return out


class Media:
    """Imports into our bins only, reusing an item already imported anywhere under '<prefix> B-roll'."""

    def __init__(self, mp, top):
        self.mp, self.root, self.paths, self.notes = mp, mp.GetRootFolder(), index_paths(top), []

    def get(self, path, folder):
        key = glue.canon(path)
        if key in self.paths:
            return self.paths[key]
        self.mp.SetCurrentFolder(folder)
        got = self.mp.ImportMedia([path]) or []
        self.mp.SetCurrentFolder(self.root)
        if not got:
            self.notes.append(f"içe aktarılamadı: {path}")
            return None
        mpi = got[0]
        if glue.canon(mpi.GetClipProperty("File Path")) != key:
            self.notes.append(f"içe aktarılan dosya farklı: {path} -> {mpi.GetClipProperty('File Path')}")
        self.paths[key] = mpi
        return mpi


def track_items(tl, s0, fps):
    """(seen dicts, uid -> timeline item) of V2 and V3"""
    seen, by_uid = [], {}
    for k in (2, 3):
        if k > tl.GetTrackCount("video"):
            continue
        for it in tl.GetItemListInTrack("video", k) or []:
            s = glue.seen_item(it, s0, k, fps)
            seen.append(s)
            by_uid[s["uid"]] = it
    return seen, by_uid


def ensure_tracks(tl):
    while tl.GetTrackCount("video") < 3:
        if not tl.AddTrack("video"):
            sys.exit(f"'{tl.GetName()}': video izi eklenemedi")


def make_current(p, tl):
    """Make one of OUR timelines current, and prove it: AppendToTimeline appends to whatever is current."""
    p.SetCurrentTimeline(tl)
    cur = p.GetCurrentTimeline()
    if cur is None or cur.GetName() != tl.GetName():
        sys.exit(f"'{tl.GetName()}' etkin zaman çizelgesi yapılamadı; durduruldu")


def place(mp, tl, s0, item, mpi, fps):
    """Append one plan item; returns the placed video timeline item or None."""
    still = glue.is_still(mpi)
    if still:
        mpi.SetMarkInOut(*glue.still_marks(item))
    try:
        got = mp.AppendToTimeline([glue.append_spec(item, mpi, s0, still, glue.clip_ratio(mpi, fps))]) or []
    finally:
        if still:
            mpi.ClearMarkInOut()
    for it in got:
        tt = it.GetTrackTypeAndIndex()
        if tt and tt[0] == "video" and tt[1] == item["track"]:
            return it
    return None


def build_chapter(ctx, n, chapter_rows, last_items):
    """One chapter: returns (new plan items, counts, problems)."""
    p, mp, ep = ctx["p"], ctx["mp"], ctx["ep"]
    a_name = episode.chapter_timeline_name(ep.m["prefix"], ctx["chapters"][n - 1], n - 1)
    name = glue.broll_name(a_name)
    frozen_tl = timeline_by_name(p, a_name)
    if frozen_tl is None:
        sys.exit(f"Bölüm {n}: '{a_name}' bulunamadı")
    ch_bin = subfolder(mp, ctx["top"], f"ch{n}")
    problems = []
    tl = timeline_by_name(p, name)
    if tl is None:
        mp.SetCurrentFolder(ctx["top"])
        tl = mp.CreateEmptyTimeline(name)
        mp.SetCurrentFolder(mp.GetRootFolder())
        if not tl:
            sys.exit(f"'{name}' oluşturulamadı")
        make_current(p, tl)
        nested = mp.AppendToTimeline([{"mediaPoolItem": frozen_tl.GetMediaPoolItem()}])  # getter only
        if not nested:
            sys.exit(f"'{a_name}' iç içe eklenemedi")
        if last_items:
            problems.append(f"zaman çizelgesi yoktu, yeniden kuruldu; plan.json'daki {len(last_items)} öğe yok sayıldı")
        last_items = []
    make_current(p, tl)
    ensure_tracks(tl)
    s0 = tl.GetStartFrame()
    seen, by_uid = track_items(tl, s0, ctx["ep"].fps)
    current = plan.readback(last_items, seen)
    desired = [dict(d, file=glue.canon(d["file"])) for d in plan.desired(chapter_rows, ctx["fetched"], ctx["visuals"])]
    keep, remove, add = plan.actions(current, desired)

    # remove before add: an append over an existing item is cut to the free gap
    dead = [by_uid[i["uid"]] for i in remove if i.get("uid") in by_uid]
    if dead and not tl.DeleteClips(dead):
        problems.append(f"{len(dead)} öğe silinemedi")
    for i in remove:
        tl.DeleteMarkerByCustomData(glue.CUSTOM + i["id"])

    kept = []
    for i, old_id in glue.rebind(keep, desired):
        if i.get("kind") == "placeholder" and not i.get("editor") and i.get("row") is not None:
            tl.DeleteMarkerByCustomData(glue.CUSTOM + old_id)  # refreshed below with the current text
        kept.append(i)

    added = []
    for i in add:
        mpi = ctx["media"].get(i["file"], ch_bin)
        it = place(mp, tl, s0, i, mpi, ep.fps) if mpi else None
        new, probs = glue.placed(i, glue.seen_item(it, s0, i["track"], ep.fps) if it else None)
        problems += probs
        added.append(new)

    used = {int(f) for f in (tl.GetMarkers() or {})}
    for i in kept + added:
        if i.get("editor") or i.get("uid") is None:
            continue
        m = glue.marker_args(i, used)
        if m and tl.GetMarkerByCustomData(m["customData"]) in (None, {}):
            if tl.AddMarker(m["frameId"], m["color"], m["name"], m["note"], m["duration"], m["customData"]):
                used.add(m["frameId"])
            else:
                problems.append(f"{i['id']}: işaretçi eklenemedi")

    items = kept + added
    for key, row in chapter_rows.items():  # unused candidates -> <prefix> B-roll/ch<N>/<row id>
        if row is None:
            continue
        files = plan.unused_candidates(ctx["canon_fetched"]["rows"].get(key, []),
                                       [i for i in items if i.get("row") == key])
        if files:
            row_bin = subfolder(mp, ch_bin, row["id"])
            for f in files:
                ctx["media"].get(f, row_bin)
    counts = {"added": sum(1 for i in added if i.get("uid")), "removed": len(remove), "kept": len(kept),
              "editor": sum(1 for i in items if i.get("editor"))}
    return name, items, counts, problems


def cmd_build(a):
    ep = episode.Episode(a.episode)
    frozen = set(ep.m.get("frozen", []))
    done = set(ep.m.get("broll_frozen", []))
    todo = sorted(set(a.chapters) & frozen if a.chapters else frozen)
    for n in sorted(set(a.chapters) - frozen) if a.chapters else []:
        print(f"ch{n}: A-roll bölümü dondurulmamış, atlandı", file=sys.stderr)
    rows_json = _read(ep.path("broll", "rows.json"))
    fetched = _read(ep.path("broll", "fetched.json"))
    requests = _read(ep.path("broll", "requests.json"), {"rows": {}})
    script_rows = rows_mod.load(ep)
    plan_path = ep.path("broll", "plan.json")
    data = plan.load(plan_path)
    data["units"] = "frames"
    _, p = connect()
    mp = p.GetMediaPool()
    ctx = {"ep": ep, "p": p, "mp": mp, "fetched": fetched, "visuals": {r.key: r.visual for r in script_rows},
           "chapters": _read(ep.path("sections.json"))["chapters"]}
    ctx["canon_fetched"] = _canon_fetched(fetched)
    ctx["top"] = subfolder(mp, mp.GetRootFolder(), f"{ep.m['prefix']} B-roll")
    ctx["media"] = Media(mp, ctx["top"])
    built = []
    for n in todo:
        if n in done:
            print(f"ch{n}: B-roll dondurulmuş, atlandı", file=sys.stderr)
            continue
        ch = rows_json.get("chapters", {}).get(str(n))
        if ch is None:
            print(f"ch{n}: rows.json'da yok: önce 'broll.py align' ve 'fetch' çalıştırın", file=sys.stderr)
            continue
        last = data["chapters"].get(str(n), {}).get("items", [])
        name, items, c, probs = build_chapter(ctx, n, ch["rows"], last)
        data["chapters"][str(n)] = {"timeline": name, "items": items}
        plan.save(plan_path, data)
        built.append((n, ch["rows"], items))
        print(f"ch{n} '{name}': {c['added']} eklendi, {c['removed']} kaldırıldı, {c['kept']} korundu "
              f"({c['editor']} düzenleyici öğesi)", file=sys.stderr)
        for x in probs:
            print(f"  Uyarı: {x}", file=sys.stderr)
    for x in ctx["media"].notes:
        print(f"Uyarı: {x}", file=sys.stderr)
    all_items = [i for ch in data["chapters"].values() for i in ch["items"]]
    kp = ep.path("broll", "kaynaklar.txt")
    credits.write(kp, credits.collect(all_items, ctx["canon_fetched"]))
    ids = {r.key: r.id for r in script_rows}
    for line in glue.summary(built, fetched, requests, ids):
        print(line, file=sys.stderr)
    print(f"-> {plan_path}, {kp}", file=sys.stderr)
    return 0


def _canon_fetched(fetched):
    """fetched.json with canonical paths, to match plan items' file form"""
    out = {"rows": {}}
    for key, assets in fetched.get("rows", {}).items():
        out["rows"][key] = [dict(a, hold=glue.canon(a.get("hold")),
                                 files=[dict(c, file=glue.canon(c["file"])) for c in a.get("files") or []])
                            for a in assets]
    return out


def cmd_master(a):
    ep = episode.Episode(a.episode)
    pre = ep.m["prefix"]
    titles = _read(ep.path("sections.json"))["chapters"]
    names = [episode.chapter_timeline_name(pre, t, i) for i, t in enumerate(titles)]
    _, p = connect()
    mp = p.GetMediaPool()
    existing = {p.GetTimelineByIndex(i).GetName() for i in range(1, p.GetTimelineCount() + 1)}
    plan_ = glue.master_entries(names, existing, set(ep.m.get("frozen", [])))
    name = f"{pre} B-roll"
    old = timeline_by_name(p, name)
    if old is not None:
        mp.DeleteTimelines([old])
    top = subfolder(mp, mp.GetRootFolder(), name)
    mp.SetCurrentFolder(top)
    tl = mp.CreateEmptyTimeline(name)
    mp.SetCurrentFolder(mp.GetRootFolder())
    if not tl:
        sys.exit(f"'{name}' oluşturulamadı")
    make_current(p, tl)
    rec, marks = 0, []
    for n, src in plan_:
        if src is None:
            print(f"ch{n}: ne B-roll ne dondurulmuş A-roll zaman çizelgesi var, eklenmedi", file=sys.stderr)
            continue
        mpi = timeline_by_name(p, src).GetMediaPoolItem()
        got = mp.AppendToTimeline([{"mediaPoolItem": mpi}])
        frames = int(mpi.GetClipProperty("Frames"))
        marks.append((rec, titles[n - 1], f"chapter start ({src})"))
        print(f"ch{n}: {src} iç içe eklendi ({frames} kare, {bool(got)})", file=sys.stderr)
        rec += frames
    for fr, nm, note in marks:
        tl.AddMarker(fr, "Green", nm, note, 1)
    print(f"{name}: {rec} kare, zaman çizelgesi uzunluğu {tl.GetEndFrame() - tl.GetStartFrame()}", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("layout", help="dondurulmuş bölümlerin V1 yerleşimini oku (salt okunur)")
    s.add_argument("episode")
    s.set_defaults(fn=cmd_layout)
    s = sub.add_parser("build", help="B-roll zaman çizelgelerini kur / güncelle (düzenleyici değişiklikleri korunur)")
    s.add_argument("episode")
    s.add_argument("chapters", nargs="*", type=int)
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser("master", help="'<prefix> B-roll' ana zaman çizelgesini yeniden kur")
    s.add_argument("episode")
    s.set_defaults(fn=cmd_master)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
