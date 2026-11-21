"""Eligible chapters and sentences of a signed-off chapter."""

# The rough cutter's pause threshold (rough-cutting-a-roll/scripts/cutplan.py), at 25 fps.
PAUSE_F = 12
END_PUNCT = ".?!…"


def chapters(ep):
    """Sorted 1-based chapters that are in both "frozen" (A-roll) and "broll_frozen" (B-roll)."""
    return sorted(set(ep.m.get("frozen", [])) & set(ep.m.get("broll_frozen", [])))


def sentences(words, fps):
    """[{"start","end","text"}] from chapter words (start, end, norm[, raw text]): a sentence ends after a word
    whose text ends in . ? ! … or before a gap longer than PAUSE_F frames (scaled by fps)."""
    pause = round(PAUSE_F * fps / 25)
    out, cur = [], []

    def flush():
        if cur:
            out.append({"start": cur[0][0], "end": cur[-1][1], "text": " ".join(w[-1] for w in cur)})
            cur.clear()

    for w in words:
        if cur and w[0] - cur[-1][1] > pause:
            flush()
        cur.append(w)
        if w[-1].rstrip().endswith(tuple(END_PUNCT)):
            flush()
    flush()
    return out
