"""Script rows -> frames on a frozen chapter timeline.

chapter_words: transcript words that survive in the chapter's layout (broll/layout/chN.json), on the chapter
  timeline. A word belongs to a piece when its camera-frame midpoint lies in [src_start, src_end)
  (sections.py convention: camera frame = recorder frame + offset_f).
align_rows: each row's SES words matched, in script order, to those words with 3-grams.
coverage: the [start, end) range a B-roll row covers (runs on to the next B-roll row across small gaps; a mixed
  [KAMERA, X] row is an overlay over the presenter and ends at its own last word).
"""
import json
import re
import sys

import rows as rows_mod


def norm(x):  # same as rough-cutting-a-roll/scripts/sections.py
    return re.sub(r"[^\wçğıöşüâî]", "", x.lower().replace("i̇", "i"))


def tc2f(tc, fps=25):  # same as sections.py
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * fps + f


def chapter_words(ep, layout, raw=False):
    """[(start_f, end_f, norm_text)] on the chapter timeline, in timeline order; raw=True adds the word's
    original transcript text as a 4th element."""
    clips = {c["clip"]: c for c in ep.clips(all_=True)}
    cache = {}

    def clip_words(name):
        if name not in cache:
            c = clips[name]
            if "offset_f" not in c:
                raise ValueError(f"{name}: episode.json'da offset_f yok (ingest.py senkronu yapılmamış)")
            off, fps = c["offset_f"], ep.fps
            with open(ep.wav_tr(c), encoding="utf-8") as f:
                t = json.load(f)
            ws = []
            for s in t["segments"]:
                for w in s.get("words", []):
                    n = norm(w["text"])
                    if n:
                        a, b = tc2f(w["start"], fps) + off, tc2f(w["end"], fps) + off
                        ws.append(((a + b) // 2, a, b, n, w["text"]))
            cache[name] = ws
        return cache[name]

    out = []
    for rec, clip, a, b in sorted(layout["pieces"], key=lambda p: p[0]):
        if clip not in clips:  # not a camera clip of this episode (title, generator, foreign media): no words
            print(f"uyarı: {layout['timeline']} @{rec}: {clip!r} episode.json'da yok, atlandı", file=sys.stderr)
            continue
        for mid, s, e, n, text in clip_words(clip):
            if a <= mid < b:
                t = (rec + max(s, a) - a, rec + min(e, b) - a, n)
                out.append(t + (text,) if raw else t)
    out.sort()
    return out


def tokens(ses):
    return [n for n in (norm(w) for w in re.sub(r"\([^)]*\)", " ", ses).split()) if n]


def _match(toks, texts, cursor):
    """3-gram hits at or after cursor, in order (row position strictly increasing), as one bounded run:
    the first hit lies within max(60, 3*len) words of the cursor, and each next hit within max(8, len) words
    of the previous one; the run stops at the first larger gap. -> (first, last, covered)"""
    grams = {}
    for k in range(len(toks) - 2):
        grams.setdefault(tuple(toks[k:k + 3]), []).append(k)
    reach, step = max(60, 3 * len(toks)), max(8, len(toks))
    last_k, first, prev, last, covered = -1, None, None, None, set()
    for i in range(cursor, len(texts) - 2):
        if (i - cursor if prev is None else i - prev) > (reach if prev is None else step):
            break
        ks = [k for k in grams.get(tuple(texts[i:i + 3]), []) if k > last_k]
        if not ks:
            continue
        k = ks[0]
        if first is None:
            first = i
        prev, last, last_k = i, i + 2, k
        covered.update((k, k + 1, k + 2))
        if k == len(toks) - 3:  # row's last 3-gram: the row is done
            break
    return first, last, len(covered)


def align_rows(rows, words):
    """{row.key: {"start", "end", "first_word", "last_word"} | None} for every row, in script order."""
    texts = [w[2] for w in words]
    out, cursor = {}, 0
    for r in rows:
        toks = tokens(r.ses)
        first, last, n = _match(toks, texts, cursor)
        if first is None or n < max(3, 0.3 * len(toks)):
            out[r.key] = None
            continue
        out[r.key] = {"start": words[first][0], "end": words[last][1], "first_word": first, "last_word": last}
        cursor = last + 1
    return out


def coverage(rows, spans, words, max_gap=3):
    """{key: {"start", "end"} | None} for the B-roll rows (rows.is_broll: KAMERA-only rows are left out): a row
    runs on to the next found row's start when neither row has KAMERA and at most max_gap words lie between them,
    else it ends at its last word. A mixed [KAMERA, X] row never runs on (the presenter is on screen)."""
    found = [r for r in rows if spans.get(r.key)]
    out = {}
    for r in rows:
        if not rows_mod.is_broll(r):
            continue
        sp = spans.get(r.key)
        if not sp:
            out[r.key] = None
            continue
        end = words[sp["last_word"]][1]
        i = found.index(r)
        if i + 1 < len(found) and "KAMERA" not in r.tags:
            nxt = found[i + 1]
            ns = spans[nxt.key]
            if "KAMERA" not in nxt.tags and ns["first_word"] - sp["last_word"] - 1 <= max_gap:
                end = ns["start"]
        out[r.key] = {"start": sp["start"], "end": end}
    return out
