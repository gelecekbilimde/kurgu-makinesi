"""Captions of a short: script spelling, subtitle cues (SRT) and the teaser's word-by-word timings.

`words_on_short` is a list of {"start","end","text"} in short frames (half-open), `text` the transcript word."""
import difflib
import re

import align

POST_F = 3    # the rough cutter's boundary padding after a word (cands.POST_F)
GAP_F = 12    # a pause longer than this starts a new cue; a gap up to this is bridged
SENTENCE_END = ".?!…"


def _script_words(script_rows):
    out = []
    for r in script_rows:
        for raw in re.sub(r"\([^)]*\)", " ", r.ses).split():
            if align.norm(raw):
                out.append(raw)
    return out


def _alike(a, b):
    return a.startswith(b) or b.startswith(a) or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def spell(words, script_rows):
    """Per word, the script's spelling where the normalised words line up with the script's (an equal block,
    or a similar word, in order, inside a differing block, e.g. '1,5' / '1,5°C'); else the transcript's."""
    script = _script_words(script_rows)
    a = [align.norm(x["text"]) for x in words]
    b = [align.norm(x) for x in script]
    out = [x["text"] for x in words]
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out[i1:i2] = script[j1:j2]
        elif tag == "replace":  # similar words in order inside the block, e.g. '1,5' / '1,5°C'
            j = j1
            for i in range(i1, i2):
                k = next((k for k in range(j, j2) if _alike(a[i], b[k])), None)
                if k is not None:
                    out[i], j = script[k], k + 1
    return out


def _overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def cues(words_on_short, fps, max_chars=32, max_lines=2, avoid=()):
    """[{"start","end","text"}] (`\\n` between lines). Words inside the `avoid` [start, end) ranges are left out
    and no cue runs into them. (Frame limits are fps-independent, like the rough cutter's.)"""
    ws = [w for w in words_on_short if not any(_overlaps(w["start"], w["end"], a, b) for a, b in avoid)]
    groups, cur, lines = [], [], []

    def flush():
        nonlocal cur, lines
        if cur:
            groups.append((cur[0]["start"], cur[-1]["end"], "\n".join(lines)))
        cur, lines = [], []

    for w in ws:
        if cur:
            prev = cur[-1]
            if (w["start"] - prev["end"] > GAP_F or prev["text"][-1:] in SENTENCE_END
                    or any(_overlaps(prev["end"], w["start"], a, b) for a, b in avoid)):
                flush()
        if lines and len(lines[-1]) + 1 + len(w["text"]) <= max_chars:
            lines[-1] += " " + w["text"]
        elif len(lines) < max_lines:
            lines.append(w["text"])
        else:
            flush()
            lines = [w["text"]]
        cur.append(w)
    flush()

    out = []
    for i, (s, e, text) in enumerate(groups):
        end = e + POST_F
        if i + 1 < len(groups):
            nxt = groups[i + 1][0]
            end = nxt if nxt - e <= GAP_F else min(end, nxt)
        for a, _b in avoid:
            if a >= s:
                end = min(end, a)
        out.append({"start": s, "end": end, "text": text})
    return out


def teaser_words(words_on_short, teaser):
    """The words inside the teaser [start, end), in frames relative to its start (the graphic's `words`)."""
    t0, t1 = teaser
    return [{"text": w["text"], "start": max(w["start"], t0) - t0, "end": min(w["end"], t1) - t0}
            for w in words_on_short if _overlaps(w["start"], w["end"], t0, t1)]


def _stamp(frame, fps):
    ms = (frame * 1000 + fps // 2) // fps
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(cues_, fps):
    return "".join(f"{i}\n{_stamp(c['start'], fps)} --> {_stamp(c['end'], fps)}\n{c['text']}\n\n"
                   for i, c in enumerate(cues_, 1))
