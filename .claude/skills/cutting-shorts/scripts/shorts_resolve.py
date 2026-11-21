#!/usr/bin/env python3
"""Shorts steps that talk to DaVinci Resolve. Run through the rough cutter's rv.sh:
  bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh .claude/skills/cutting-shorts/scripts/shorts_resolve.py read EP
read: per eligible chapter (frozen A-roll + signed-off B-roll) read the frozen A-roll timeline's V1 layout and the
      "<chapter timeline> B-roll" timeline's V2+ items, read-only (no SetCurrentTimeline, no setters, no markers):
      shorts/layout/ch<N>.json (the B-roll skill's layout format) and shorts/broll/ch<N>.json
      = {"units": "frames", "timeline", "items": [{track,start,end,file,src_in,src_out,props,kind,src_size}]}
      (src_size: [w, h] from the media-pool clip's "Resolution", when readable).
review: builds "<prefix> short adayları" (bin "<prefix> Shorts", 16:9) nesting the eligible chapters' B-roll
      timelines, with one Fuchsia ranged marker per candidate piece and teaser. Only that timeline is touched.
accept: reads that timeline's markers back (Green = accepted, moved/resized = new ranges) into
      shorts/candidates.json, re-snaps, then rebuilds the review timeline.
build [ID ...]: per accepted, not frozen candidate (signed-off chapters only) create or update its 1080x1920
      timeline "<prefix> short <rank> <title>" (bin "<prefix> Shorts/<id>") from shorts/<id>/assets.json and
      crop.json, keeping every editor change (sbuild.py); shorts/plan.json is saved after every change.
      Long-form timelines are only read; every setter is checked against our name pattern first.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "placing-b-roll", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cutting-a-roll", "scripts"))

import broll_resolve as br  # noqa: E402
import build as glue  # noqa: E402
import cands  # noqa: E402
import captions  # noqa: E402
import eligible  # noqa: E402
import episode  # noqa: E402
import mapping  # noqa: E402
import review  # noqa: E402
import sbuild  # noqa: E402
import shorts  # noqa: E402
import splan  # noqa: E402
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


def parse_resolution(text):
    """Clip property "Resolution" ("1920x1080") -> [w, h], or None when unreadable."""
    m = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", str(text or ""))
    if not m or not int(m.group(1)) or not int(m.group(2)):
        return None
    return [int(m.group(1)), int(m.group(2))]


def src_sizes(by_uid):
    """uid -> [w, h] of each timeline item's media-pool clip (None when unknown)."""
    out = {}
    for uid, it in by_uid.items():
        mpi = it.GetMediaPoolItem()
        out[uid] = parse_resolution(mpi.GetClipProperty("Resolution")) if mpi is not None else None
    return out


def read_items(seen, fetched, sizes=None):
    """B-roll timeline items (glue.seen_item dicts) -> short items with a "kind": the fetched asset's kind,
    "still" (+ "hold_of": the graphic's file) for a graphic's hold still, "editor" for a file never fetched;
    "src_size": [w, h] of the source picture when sizes (uid -> [w, h] | None) knows it."""
    files, holds = _file_index(fetched)
    out = []
    for s in seen:
        f = glue.canon(s["file"])
        it = {k: s[k] for k in KEYS}
        if (sizes or {}).get(s.get("uid")):
            it["src_size"] = list(sizes[s["uid"]])
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
        seen, by_uid = sync.track_items(btl, btl.GetStartFrame(), fps, tracks=None)
        items = sorted(read_items(seen, fetched, src_sizes(by_uid)), key=lambda i: (i["start"], i["track"]))
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
        for bump in range(0, review.MAX_BUMP + 1):  # a second marker on an occupied frame is refused
            mm = m if not bump else review.bumped(m, fr + bump)
            if tl.AddMarker(mm["frameId"], mm["color"], mm["name"], mm["note"], mm["duration"], mm["customData"]):
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
    try:
        frames = _chapter_frames(ep, chapters_ok)
    except FileNotFoundError as err:
        sys.exit(f"{err} yok: önce 'read' ile bölümlerin yerleşimini okuyun")
    offs = review.offsets(frames, chapters_ok)
    data, notes = review.read_back(data, marks, offs, frames)
    need = sorted({r["chapter"] for c in data["candidates"] for r in c.get("pieces", []) + [c.get("teaser") or {}]
                   if r.get("chapter") in chapters_ok})
    try:
        words = shorts._words(ep, need)
    except FileNotFoundError as err:
        sys.exit(f"{err} yok: önce 'read' ile bölümlerin yerleşimini okuyun")
    data, cnotes, errors = cands.check(data, words, chapters_ok, ep.fps)
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


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def chapter_cameras(p, ep, chapters, titles):
    """canonical camera path -> the media-pool item the frozen chapter's V1 uses (read only: getters), so the
    short's camera items are the same clip, with the recorder WAV linked to it."""
    out = {}
    for n in chapters:
        tl = br.timeline_by_name(p, episode.chapter_timeline_name(ep.m["prefix"], titles[n - 1], n - 1))
        for it in (tl.GetItemListInTrack("video", 1) or []) if tl is not None else []:
            mpi = it.GetMediaPoolItem()
            fp = mpi.GetClipProperty("File Path") if mpi is not None else None
            if fp:
                out.setdefault(glue.canon(fp), mpi)
    return out


def find_timeline(p, entry, want):
    """The short's timeline: by the uid in plan.json, else by its recorded name, else by the wanted name."""
    uid = entry.get("timeline")
    if uid:
        for i in range(1, p.GetTimelineCount() + 1):
            tl = p.GetTimelineByIndex(i)
            if tl.GetUniqueId() == uid:
                return tl
    for name in (entry.get("timeline_name"), want):
        tl = br.timeline_by_name(p, name) if name else None
        if tl is not None:
            return tl
    return None


def build_short(ctx, cand, entry, save):
    """One short -> report dict {name, counts, problems, flags, skipped, stale, needed}. save(entry) records
    plan.json's entry of the short as soon as the timeline changed."""
    ep, p, mp, fps, pre = ctx["ep"], ctx["p"], ctx["mp"], ctx["ep"].fps, ctx["ep"].m["prefix"]
    sid = cand["id"]
    d = ep.path("shorts", sid)
    rep = {"name": None, "counts": None, "problems": [], "flags": [], "skipped": [], "stale": [], "needed": []}
    try:
        assets = _json(os.path.join(d, "assets.json"))
        crops = _json(assets.get("crop") or os.path.join(d, "crop.json"))
    except FileNotFoundError as err:
        rep["problems"].append(f"{err.filename} yok: önce 'shorts.py prepare {ep.dir} {sid}' çalıştırın")
        return rep
    rep["needed"] = assets.get("needed") or []
    layout = mapping.short_layout(cand, ctx["layouts"], ctx["brolls"], fps, assets["end_card_frames"])
    try:
        desired = [sbuild.still_range(dict(i, file=glue.canon(i["file"])))
                   for i in splan.desired(layout, assets, crops)]
    except ValueError as err:
        rep["problems"].append(str(err))
        return rep
    desired, probs = sbuild.black_backgrounds(desired, os.path.join(d, "siyah"))
    rep["problems"] += probs
    want_cues = splan.cues(assets, layout)
    want_name = cands.timeline_name(pre, cand.get("rank"), cand.get("title") or "")
    folder = sync.subfolder(mp, ctx["top"], sid)

    last_items, last_subs = entry.get("items") or [], entry.get("subtitles") or []
    last_segs = entry.get("segments") or []
    tl = find_timeline(p, entry, want_name)
    fresh = tl is None
    if fresh:
        tl = sbuild.create_timeline(mp, folder, want_name, fps, pre)
        if last_items or last_subs:
            rep["problems"].append(f"zaman çizelgesi yoktu, yeniden kuruldu; plan.json'daki {len(last_items)} öğe "
                                   "yok sayıldı")
        last_items, last_subs, last_segs = [], [], layout["segments"]
    else:
        if not sbuild.is_ours(tl.GetName(), pre):
            raise sbuild.NotOurs(f"zaman çizelgesi '{tl.GetName()}': düzenleyici yeniden adlandırmış, atlandı "
                                 f"(adı '{pre} short <sıra> ...' biçiminde olmalı)")
        new = sbuild.rename_to(tl.GetName(), want_name, pre)
        if new:
            sbuild.assert_ours(tl, pre)
            old = tl.GetName()
            if tl.SetName(new):
                rep["problems"].append(f"'{old}' -> '{new}' olarak yeniden adlandırıldı")
            else:
                rep["problems"].append(f"'{old}' '{new}' olarak yeniden adlandırılamadı (ad kullanımda olabilir)")
    rep["name"] = tl.GetName()
    state = {"timeline": tl.GetUniqueId(), "timeline_name": tl.GetName(), "items": last_items,
             "subtitles": last_subs, "segments": last_segs}

    def keep(**kw):
        state.update(kw)
        save(dict(state))

    keep()
    sbuild.assert_ours(tl, pre)
    br.make_current(p, tl)  # AppendToTimeline appends to the current timeline

    extra = []
    if fresh and want_cues:  # Ruling 5: subtitles first, while the timeline is empty
        rep["problems"] += sbuild.import_subtitles(mp, tl, folder, assets["captions"], pre)
    keep_cues, ours = splan.subtitle_readback(last_subs, sbuild.read_cues(tl), last_segs, want_cues)
    subs = keep_cues + ours
    keep(subtitles=subs)
    if splan.subtitles_stale(subs, want_cues):
        with open(assets["captions"], "w", encoding="utf-8") as f:
            f.write(captions.srt(assets.get("cues") or [], fps))
        m, line = splan.subtitles_stale_note(sid)
        extra.append(m)
        rep["flags"].append(line)

    sctx = {"mp": mp, "media": ctx["media"], "bin": folder, "fps": fps, "prefix": pre}
    items, rep["counts"], probs = sbuild.sync_short(sctx, tl, last_items, desired, last_segs,
                                                    lambda its: keep(items=its))
    rep["problems"] += probs
    if fresh:
        sbuild.mute_scratch(tl, pre)
    stale = splan.stale_anchors([i for i in items + subs if i.get("editor")], layout)
    sm, rep["stale"] = splan.stale_notes(sid, stale)
    rep["flags"] = splan.flag_lines(sid, items) + rep["flags"]
    rep["skipped"] = [f"{sid}: bölüm {s['chapter']} [{s['start']}, {s['end']}) V{s['track']} "
                      f"{os.path.basename(s.get('file') or '')}" for s in layout.get("skipped") or []]
    markers = splan.merge(splan.flags(items, layout, cand) + sm + extra)
    rep["problems"] += sbuild.set_markers(tl, sid, markers, layout["frames"], pre)
    keep(items=items, segments=layout["segments"], timeline_name=tl.GetName())
    return rep


def _section(title, lines):
    print(f"{title}: " + ("yok" if not lines else ""), file=sys.stderr)
    for line in lines:
        print(f"  - {line}", file=sys.stderr)


def cmd_build(a):
    ep = episode.Episode(a.episode)
    pre = ep.m["prefix"]
    chapters_ok = eligible.chapters(ep)
    _, data = _load(ep)
    todo, lines, bad = sbuild.todo(data["candidates"], a.ids, chapters_ok)
    for line in lines:
        print(line, file=sys.stderr)
    if not todo:
        print("Kurulacak short yok: kabul edilmiş, dondurulmamış aday gerekli.", file=sys.stderr)
        return 1
    need = sorted({r["chapter"] for c in todo for r in c["pieces"] + [c["teaser"]]})
    try:
        layouts = {n: _json(ep.path("shorts", "layout", f"ch{n}.json")) for n in need}
        brolls = {n: _json(ep.path("shorts", "broll", f"ch{n}.json")) for n in need}
    except FileNotFoundError as err:
        sys.exit(f"{err.filename} yok: önce 'read' ile bölümleri okuyun")
    titles = _json(ep.path("sections.json"))["chapters"]
    plan_path = ep.path("shorts", "plan.json")
    pdata = splan.load(plan_path)
    pdata["units"] = "frames"
    pdata.setdefault("shorts", {})
    _, p = br.connect()
    mp = p.GetMediaPool()
    try:
        top = sync.subfolder(mp, mp.GetRootFolder(), f"{pre} Shorts")
    except sync.Problem as err:
        sys.exit(str(err))
    media = sync.Media(mp, top)
    for f in mp.GetRootFolder().GetSubFolderList() or []:  # reuse what the B-roll skill imported
        if f.GetName() == f"{pre} B-roll":
            sync.index_paths(f, media.paths)
    media.paths.update(chapter_cameras(p, ep, need, titles))
    ctx = {"ep": ep, "p": p, "mp": mp, "top": top, "media": media, "layouts": layouts, "brolls": brolls}
    flags, skipped, stale, needed, rc = [], [], [], [], 1 if bad else 0
    for c in todo:
        sid = c["id"]

        def save(entry, sid=sid):
            pdata["shorts"][sid] = entry
            splan.save(plan_path, pdata)

        try:
            rep = build_short(ctx, c, pdata["shorts"].get(sid) or {}, save)
        except (sbuild.NotOurs, sync.Problem) as err:
            print(f"{sid}: {err}", file=sys.stderr)
            rc = 1
            continue
        n = rep["counts"]
        if n is None:
            print(f"{sid}: kurulamadı", file=sys.stderr)
            rc = 1
        else:
            print(f"{sid} '{rep['name']}': {n['added']} eklendi, {n['removed']} kaldırıldı, {n['kept']} korundu "
                  f"({n['editor']} düzenleyici öğesi)", file=sys.stderr)
        for x in rep["problems"]:
            print(f"  Uyarı: {x}", file=sys.stderr)
        flags += rep["flags"]
        skipped += rep["skipped"]
        stale += rep["stale"]
        needed += [x for x in rep["needed"] if x not in needed]
    _section("Kontrol edilecekler", flags)
    _section("Kopyalanmayan yer tutucular", skipped)
    _section("Kayan düzenleyici öğeleri", stale)
    _section("Gereken şablonlar", needed)
    print(f"-> {plan_path}", file=sys.stderr)
    return rc


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
    s = sub.add_parser("build")
    s.add_argument("episode")
    s.add_argument("ids", nargs="*")
    s.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
