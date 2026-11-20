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
import sync  # noqa: E402


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


def build_chapter(ctx, n, chapter_rows, last_items, save):
    """One chapter: returns (timeline name, plan items | None when nothing was done, counts, problems).
    save(items) records plan items as soon as the timeline changed."""
    p, mp, ep = ctx["p"], ctx["mp"], ctx["ep"]
    a_name = episode.chapter_timeline_name(ep.m["prefix"], ctx["chapters"][n - 1], n - 1)
    name = glue.broll_name(a_name)
    frozen_tl = timeline_by_name(p, a_name)
    if frozen_tl is None:
        return name, None, None, [f"'{a_name}' bulunamadı"]
    problems = []
    try:
        ch_bin = sync.subfolder(mp, ctx["top"], f"ch{n}")
    except sync.Problem as err:
        ch_bin = None
        problems.append(str(err))
    tl = timeline_by_name(p, name)
    if tl is None:
        mp.SetCurrentFolder(ctx["top"])
        tl = mp.CreateEmptyTimeline(name)
        mp.SetCurrentFolder(mp.GetRootFolder())
        if not tl:
            return name, None, None, problems + [f"'{name}' oluşturulamadı"]
        make_current(p, tl)
        if not mp.AppendToTimeline([{"mediaPoolItem": frozen_tl.GetMediaPoolItem()}]):  # getter only
            mp.DeleteTimelines([tl])  # ours and empty: the next build starts clean
            return name, None, None, problems + [f"'{a_name}' iç içe eklenemedi; '{name}' silindi"]
        if last_items:
            problems.append(f"zaman çizelgesi yoktu, yeniden kuruldu; plan.json'daki {len(last_items)} öğe yok sayıldı")
        last_items = []
        save([])
    make_current(p, tl)
    ensure_tracks(tl)
    desired = [dict(d, file=glue.canon(d["file"])) for d in plan.desired(chapter_rows, ctx["fetched"], ctx["visuals"])]
    items, counts, probs = sync.sync_items(tl, mp, ctx["media"], ch_bin, ep.fps, last_items, desired, save)
    problems += probs
    save(items)
    problems += sync.file_candidates(mp, ctx["media"], ch_bin, chapter_rows, ctx["canon_fetched"], items)
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
    try:
        ctx["top"] = sync.subfolder(mp, mp.GetRootFolder(), f"{ep.m['prefix']} B-roll")
    except sync.Problem as err:
        sys.exit(str(err))
    ctx["media"] = sync.Media(mp, ctx["top"])
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
        tl_name = glue.broll_name(episode.chapter_timeline_name(ep.m["prefix"], ctx["chapters"][n - 1], n - 1))

        def save(items, n=n, tl_name=tl_name):
            data["chapters"][str(n)] = {"timeline": tl_name, "items": items}
            plan.save(plan_path, data)

        name, items, c, probs = build_chapter(ctx, n, ch["rows"], last, save)
        if items is None:
            print(f"ch{n} '{name}': kurulamadı", file=sys.stderr)
        else:
            built.append((n, ch["rows"], items))
            print(f"ch{n} '{name}': {c['added']} eklendi, {c['removed']} kaldırıldı, {c['kept']} korundu "
                  f"({c['editor']} düzenleyici öğesi)", file=sys.stderr)
        for x in probs:
            print(f"  Uyarı: {x}", file=sys.stderr)
    kp = ep.path("broll", "kaynaklar.txt")
    credits.write(kp, glue.episode_credits(data["chapters"], ctx["canon_fetched"],
                                          credits.tool_credits(ep.path("broll"))))
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
    top = sync.subfolder(mp, mp.GetRootFolder(), name)
    mp.SetCurrentFolder(top)
    tl = mp.CreateEmptyTimeline(name)
    mp.SetCurrentFolder(mp.GetRootFolder())
    if not tl:
        sys.exit(f"'{name}' oluşturulamadı")
    make_current(p, tl)

    def lookup(src):
        t = timeline_by_name(p, src)
        return t.GetMediaPoolItem() if t is not None else None

    marks, rec, lines = glue.nest_chapters(mp, plan_, titles, lookup)
    for line in lines:
        print(line, file=sys.stderr)
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
