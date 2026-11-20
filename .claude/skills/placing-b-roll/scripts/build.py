"""Pure glue for broll_resolve.py build/master: Resolve items -> plan fields, append specs, markers, the summary.
Takes duck-typed Resolve objects (tests pass fakes); never connects to Resolve itself.
Frames: plan items are relative to the B-roll timeline start (s0); Resolve record frames are absolute (s0 + rel).
"""
import os

import credits
import plan

MARKER_COLOR = "Lavender"
CUSTOM = "broll:"  # + item id: our markers' customData
CHECK = ("track", "start", "end", "file", "src_in", "src_out")


def canon(path):
    """One path form for plan files and read-back files, so identities compare equal."""
    return os.path.realpath(path) if path else path


def broll_name(chapter_timeline):
    return f"{chapter_timeline} B-roll"


def is_still(mpi):
    return mpi is not None and mpi.GetClipProperty("Type") == "Still"


def clip_ratio(mpi, fps):
    """clip frames per timeline frame: source frames are counted in the clip's own rate (1.0 for stills and
    when the rate is unreadable)"""
    if mpi is None or is_still(mpi):
        return 1.0
    try:
        return float(mpi.GetClipProperty("FPS")) / fps
    except (TypeError, ValueError):
        return 1.0


def seen_item(it, s0, track, fps):
    """A V2/V3 timeline item as plan.readback's `seen` dict. Source range = left offset + duration (a still's
    left offset is meaningless, so a still reads [0, duration)). props: GetProperty() plus clip colour and speed,
    everything the API shows an editor may change."""
    mpi = it.GetMediaPoolItem()
    start = it.GetStart() - s0
    dur = it.GetDuration()
    ratio = clip_ratio(mpi, fps)
    src_in = 0 if mpi is None or is_still(mpi) else round(it.GetLeftOffset() / ratio)
    props = dict(it.GetProperty() or {})
    props["ClipColor"] = it.GetClipColor() or ""
    speed = it.GetSpeed()
    props["Speed"] = speed.get("Percentage") if isinstance(speed, dict) else speed
    return {"uid": it.GetUniqueId(), "track": track, "start": start, "end": start + dur,
            "file": canon(mpi.GetClipProperty("File Path")) if mpi is not None else None,
            "src_in": src_in, "src_out": src_in + dur, "props": props}


def append_spec(item, mpi, s0, still, ratio=1.0):
    """MediaPool.AppendToTimeline clip info: video only, absolute record frame, exclusive end frame.
    A still takes no source range (Resolve ignores it): set still_marks() as mark in/out around the append."""
    spec = {"mediaPoolItem": mpi, "trackIndex": item["track"], "recordFrame": s0 + item["start"], "mediaType": 1}
    if not still:
        spec.update(startFrame=round(item["src_in"] * ratio), endFrame=round(item["src_out"] * ratio))
    return spec


def still_marks(item):
    """(in, out) for SetMarkInOut on a still: inclusive out, so the append is exactly end - start frames."""
    return 0, item["end"] - item["start"] - 1


RATE_SLACK = ("end", "src_in", "src_out")


def placed(item, seen):
    """(plan item with uid/props/file as read back right after placing, problems). A placement that differs from
    the plan only by clip-rate rounding (at most 1 frame in end/src_in/src_out) keeps the planned values plus a
    `seen` snapshot for read-back, so the next build matches it; any other difference (clipped by an overlap,
    wrong length) is recorded as placed and reported."""
    if seen is None:
        return dict(item, uid=None), [f"{item['id']}: yerleştirilemedi"]
    want = dict(item, file=canon(item.get("file")))
    diff = [k for k in CHECK if seen.get(k) != want.get(k)]
    base = dict(want, uid=seen["uid"], props=seen["props"])
    base.pop("seen", None)
    if not diff:
        return base, []
    if all(k in RATE_SLACK and abs(seen[k] - want[k]) <= 1 for k in diff):
        return dict(base, seen={k: seen[k] for k in ("start", "end", "src_in", "src_out")}), []
    new = dict(base, **{k: seen[k] for k in CHECK})
    return new, [f"{item['id']}: yerleşim farklı ({', '.join(f'{k} {want.get(k)} -> {seen.get(k)}' for k in diff)})"]


def rebind(keep, desired):
    """[(item, old id)]: a kept item of ours takes the id, marker and code of the desired item it matched, so ids
    stay unique and a placeholder's marker text follows the script. Editor entries, and every item of a row that
    has one (plan.actions leaves such rows whole), are returned unchanged."""
    locked = {i["row"] for i in keep if i.get("editor") and i.get("row") is not None}
    free = {}
    for d in desired:
        free.setdefault(tuple(d.get(k) for k in plan.IDENTITY), []).append(d)
    out = []
    for i in keep:
        match = None
        if not i.get("editor") and i.get("row") is not None and i["row"] not in locked:
            cands = free.get(tuple(i.get(k) for k in plan.IDENTITY))
            match = cands.pop(0) if cands else None
        out.append((dict(i, id=match["id"], marker=match["marker"], code=match["code"], kind=match["kind"])
                    if match else i, i["id"]))
    return out


def marker_args(item, used):
    """Timeline.AddMarker kwargs for a placeholder item (None otherwise): ranged over the item, Lavender, customData
    broll:<id>. used: frames that already hold a marker (Resolve allows one per frame); the marker moves on and
    shortens instead."""
    if item.get("kind") != "placeholder" or not item.get("marker") or item.get("deleted"):
        return None
    f = item["start"]
    while f in used and f < item["end"] - 1:
        f += 1
    text = item["marker"]
    return {"frameId": f, "color": MARKER_COLOR, "name": text.split(":", 1)[0], "note": text,
            "duration": max(1, item["end"] - f), "customData": CUSTOM + item["id"]}


def summary(chapters, fetched, requests, ids):
    """Summary lines for the built chapters. chapters: [(N, rows.json chapter rows, plan items)]; ids: row key ->
    row id (script). Lines: rows placed, placeholders by reason, stok yetmedi, rows not found in the chapter,
    satırı kayboldu, then "Gereken şablonlar" (distinct need lines)."""
    placed_rows, by_reason, short, missing, lost, needs = [], {}, [], [], [], []
    for _, rows, items in chapters:
        live = {i["row"] for i in items if i.get("row") and not i.get("deleted") and i.get("kind") != "placeholder"}
        for key, row in sorted(((k, r) for k, r in rows.items() if r), key=lambda kr: kr[1]["start"]):
            if key in live:
                placed_rows.append(row["id"])
            for a in fetched.get("rows", {}).get(key, []):
                if a["kind"] == "placeholder":
                    reason = (a.get("note") or "?").split(": ", 1)[0]
                    by_reason.setdefault(reason, []).append(f"{row['id']} ({a.get('tag') or '?'})")
            for q in requests.get("rows", {}).get(key, []):
                if q.get("kind") == "placeholder" and q.get("need") and q["need"] not in needs:
                    needs.append(q["need"])
        short += plan.shortfalls(rows, fetched)
        missing += [ids.get(k, k) for k, r in rows.items() if r is None]
        lost += plan.lost(items, rows)
    out = [f"Yerleştirilen satırlar: {', '.join(placed_rows) or 'yok'}"]
    if by_reason:
        out.append("Yer tutucular: " + "; ".join(f"{r}: {', '.join(v)}" for r, v in sorted(by_reason.items())))
    out += short
    if missing:
        out.append(f"Bölümde bulunamadı: {', '.join(missing)}")
    out += lost
    if needs:
        out += ["Gereken şablonlar:"] + [f"  - {n}" for n in needs]
    else:
        out.append("Gereken şablonlar: yok")
    return out


def episode_credits(plan_chapters, fetched):
    """kaynaklar.txt lines over plan.json chapters: chapter order, then timeline order inside a chapter
    (frames restart at 0 on every chapter's B-roll timeline)."""
    out = []
    for n in sorted(plan_chapters, key=int):
        for line in credits.collect(plan_chapters[n]["items"], fetched):
            if line not in out:
                out.append(line)
    return out


def master_entries(chapter_names, existing, frozen):
    """[(N, timeline name to nest | None)] in chapter order: the chapter's B-roll timeline if it exists, else the
    frozen A-roll chapter timeline, else None. frozen: the manifest's 1-based set."""
    out = []
    for n, name in enumerate(chapter_names, 1):
        if broll_name(name) in existing:
            out.append((n, broll_name(name)))
        elif n in frozen and name in existing:
            out.append((n, name))
        else:
            out.append((n, None))
    return out
