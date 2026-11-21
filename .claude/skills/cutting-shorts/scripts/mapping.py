"""Layout of one vertical short: camera ranges on V1, B-roll copied over the passage, teaser and end card.

All values are integer frames, half-open [start, end). Chapter frames are on the chapter timeline; "rec" is on the short.
"""


def _get(d, chapter):
    """Chapter-keyed lookup tolerant of int or str keys (JSON keys are strings)."""
    return d[chapter] if chapter in d else d[str(chapter)]


def _camera(layout, s, e, rec, seg_index):
    """V1 items for chapter range [s, e): one per overlapping camera piece; generator pieces (clip None) give none."""
    out = []
    for p_rec, clip, a, b in layout["pieces"]:
        lo, hi = max(s, p_rec), min(e, p_rec + (b - a))
        if lo >= hi or clip is None:
            continue
        out.append({"rec": rec + lo - s, "clip": clip, "src_in": a + lo - p_rec,
                    "src_out": a + hi - p_rec, "segment": seg_index})
    return out


def short_layout(cand, layouts, brolls, fps, end_card_frames):
    """Layout dict: segments, v1, broll, skipped, teaser, end_card, frames (ranges on the short are [start, end]).
    skipped: the long-form placeholders ("placeholder") and items without a file ("no-file": Text+, generators,
    compound clips, Fusion compositions), not copied."""
    parts = [("teaser", cand["teaser"])] + [("passage", p) for p in cand["pieces"]]
    segments, v1, broll, skipped = [], [], [], []
    rec = 0
    for i, (part, r) in enumerate(parts):
        ch, s, e = r["chapter"], r["start"], r["end"]
        segments.append({"part": part, "chapter": ch, "ch_start": s, "ch_end": e, "rec": rec})
        v1 += _camera(_get(layouts, ch), s, e, rec, i)
        if part == "passage":
            for it in _get(brolls, ch)["items"]:
                lo, hi = max(s, it["start"]), min(e, it["end"])
                if lo >= hi:
                    continue
                if it["kind"] == "placeholder" or not it.get("file"):  # nothing to copy: the speaker shows
                    skipped.append({"chapter": ch, "start": lo, "end": hi, "track": it["track"],
                                    "kind": "placeholder" if it.get("file") else "no-file", "file": it.get("file")})
                    continue
                out = {"rec": rec + lo - s, "end": rec + hi - s, "track": it["track"], "file": it["file"],
                       "src_in": it["src_in"] + lo - it["start"], "src_out": it["src_in"] + hi - it["start"],
                       "kind": it["kind"], "props": it.get("props", {}),
                       "anchor": {"chapter": ch, "ch_start": lo, "ch_end": hi}}
                for k in ("hold_of", "src_size"):  # src_size: the source picture's [w, h] when known
                    if k in it:
                        out[k] = it[k]
                broll.append(out)
        rec += e - s
    teaser_end = segments[0]["ch_end"] - segments[0]["ch_start"]
    return {"segments": segments, "v1": v1, "broll": broll, "skipped": skipped,
            "teaser": [0, teaser_end], "end_card": [rec, rec + end_card_frames], "frames": rec + end_card_frames}


def anchor_of(short_layout, rec_start, rec_end):
    """Chapter range under short range [rec_start, rec_end), or None if it is not inside one segment."""
    for g in short_layout["segments"]:
        length = g["ch_end"] - g["ch_start"]
        if g["rec"] <= rec_start and rec_end <= g["rec"] + length and rec_start < rec_end:
            off = rec_start - g["rec"]
            return {"chapter": g["chapter"], "ch_start": g["ch_start"] + off,
                    "ch_end": g["ch_start"] + off + rec_end - rec_start}
    return None
