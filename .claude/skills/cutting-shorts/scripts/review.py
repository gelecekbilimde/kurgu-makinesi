"""Review timeline markers: candidates as ranged markers on a 16:9 timeline that nests the eligible chapters,
and reading the editor's changes back (Green = accepted, moved/resized markers = adjusted ranges). Pure; no Resolve."""
import copy

PREFIX = "short"
MAX_BUMP = 4


def offsets(chapter_frames, eligible):
    """{chapter: start frame of that chapter on the review timeline}, chapters nested in eligible order."""
    out, rec = {}, 0
    for n in eligible:
        out[n] = rec
        rec += chapter_frames[n]
    return out


def placed_offsets(placed, names):
    """(offsets, frames) from the nested timelines as they sit on the review timeline's V1 (a nested "… B-roll"
    timeline can be longer than the chapter's A-roll layout, so the layout's frame count is not used).
    placed: [(name, start, frames)] of the V1 items, start from the timeline start; names: {chapter: nested
    timeline name} in eligible order. ValueError (Turkish) unless V1 holds exactly those timelines in that order."""
    placed = sorted(placed, key=lambda p: p[1])
    want = list(names.items())
    if [p[0] for p in placed] != [name for _, name in want]:
        raise ValueError("inceleme zaman çizelgesinin V1'i beklenen bölümler değil "
                         f"({', '.join(p[0] for p in placed) or 'boş'}; beklenen: "
                         f"{', '.join(name for _, name in want)}): işaretçiler yerleştirilmedi/okunmadı")
    return ({n: p[1] for (n, _), p in zip(want, placed)}, {n: p[2] for (n, _), p in zip(want, placed)})


def _data(cid, suffix):
    return f"{PREFIX}:{cid}:{suffix}"


def markers(data, offs):
    """One marker per piece (short:<id>:p<i>) and per teaser (short:<id>:t); Green when accepted, else Fuchsia."""
    out = []
    for c in data.get("candidates", []):
        color = "Green" if c.get("accepted") else "Fuchsia"
        name = f"{c.get('rank', '')}. {c.get('title', '')}"
        note = f"{c.get('reason', '')}\nteaser: {c.get('teaser_rating', '')}"
        ranges = [(_data(c["id"], f"p{i}"), p, name) for i, p in enumerate(c.get("pieces", []))]
        if c.get("teaser"):
            ranges.append((_data(c["id"], "t"), c["teaser"], name + " · teaser"))
        for cd, r, nm in ranges:
            if r["chapter"] not in offs:
                continue
            out.append({"frameId": offs[r["chapter"]] + r["start"], "color": color, "name": nm, "note": note,
                        "duration": r["end"] - r["start"], "customData": cd})
    return out


def bumped(m, frame):
    """The marker placed at frame (> its frameId) because its own frame was occupied: customData carries the
    intended start (short:<id>:p<i>@<frame>), so read_back can tell an untouched bumped marker from a moved one."""
    return {**m, "frameId": frame, "customData": f"{m['customData']}@{m['frameId']}"}


def _locate(frame, offs):
    """chapter whose span starts at or before frame (None before the first chapter)."""
    best = None
    for n, o in offs.items():
        if o <= frame and (best is None or o >= offs[best]):
            best = n
    return best


def _chapter_end(n, offs, chapter_frames):
    if chapter_frames and n in chapter_frames:
        return offs[n] + chapter_frames[n]
    later = [o for o in offs.values() if o > offs[n]]
    return min(later) if later else None


def read_back(data, markers_from_resolve, offs, chapter_frames=None):
    """-> (data, notes). markers_from_resolve: [{frameId, color, duration, customData, ...}] of the review
    timeline. Accepted = any of the candidate's markers Green; a missing marker keeps its old range, a moved or
    resized one gives the new range in the chapter it starts in (clamped to that chapter, with a note)."""
    data = copy.deepcopy(data)
    notes = []
    by_cd = {}
    for m in markers_from_resolve:
        cd, _, intended = str(m.get("customData")).partition("@")
        m = dict(m, customData=cd)
        if intended.isdigit():
            m["_intended"] = int(intended)
        by_cd[cd] = m
    for c in data.get("candidates", []):
        cid = c["id"]
        ranges = {_data(cid, f"p{i}"): p for i, p in enumerate(c.get("pieces", []))}
        if c.get("teaser"):
            ranges[_data(cid, "t")] = c["teaser"]
        found = [by_cd[cd] for cd in ranges if cd in by_cd]
        c["accepted"] = any(m.get("color") == "Green" for m in found)
        for cd, r in ranges.items():
            m = by_cd.get(cd)
            if m is None:
                continue
            frame = m["frameId"]
            if "_intended" in m and 0 < frame - m["_intended"] <= MAX_BUMP and m["duration"] == r["end"] - r["start"]:
                frame = m["_intended"]  # untouched marker that was only bumped off an occupied frame
            ch = _locate(frame, offs)
            if ch is None:
                notes.append(f"{cid}: işaretçi ilk bölümün öncesinde, aralık değişmedi")
                continue
            start = frame - offs[ch]
            end = start + m["duration"]
            limit = _chapter_end(ch, offs, chapter_frames)
            if limit is not None and offs[ch] + end > limit:
                end = limit - offs[ch]
                notes.append(f"{cid}: işaretçi bölüm {ch} sınırını aşıyordu, bölüm sonuna kırpıldı")
            if (ch, start, end) != (r["chapter"], r["start"], r["end"]):
                r["chapter"], r["start"], r["end"] = ch, start, end
    return data, notes
