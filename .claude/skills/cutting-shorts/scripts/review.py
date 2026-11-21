"""Review timeline markers: candidates as ranged markers on a 16:9 timeline that nests the eligible chapters,
and reading the editor's changes back (Green = accepted, moved/resized markers = adjusted ranges). Pure; no Resolve."""
import copy

PREFIX = "short"


def offsets(chapter_frames, eligible):
    """{chapter: start frame of that chapter on the review timeline}, chapters nested in eligible order."""
    out, rec = {}, 0
    for n in eligible:
        out[n] = rec
        rec += chapter_frames[n]
    return out


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
    by_cd = {m.get("customData"): m for m in markers_from_resolve}
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
            ch = _locate(m["frameId"], offs)
            if ch is None:
                notes.append(f"{cid}: işaretçi ilk bölümün öncesinde, aralık değişmedi")
                continue
            start = m["frameId"] - offs[ch]
            end = start + m["duration"]
            limit = _chapter_end(ch, offs, chapter_frames)
            if limit is not None and offs[ch] + end > limit:
                end = limit - offs[ch]
                notes.append(f"{cid}: işaretçi bölüm {ch} sınırını aşıyordu, bölüm sonuna kırpıldı")
            if (ch, start, end) != (r["chapter"], r["start"], r["end"]):
                r["chapter"], r["start"], r["end"] = ch, start, end
    return data, notes
