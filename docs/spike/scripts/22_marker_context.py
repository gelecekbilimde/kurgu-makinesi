"""Show each review marker in context, in both transcripts, with audio pauses (spike analysis).

For every marker in review-markers.json prints the words around its source range:
  [[ ... ]]  the reviewer's range (= failed bit)
  ~word      word the current plan already removes (word midpoint outside keep_frames)
  |          audio pause >= PAUSE_F silent frames between words (number = pause length in frames)
Caches per-clip audio features as out/episode/<clip>-frames.npz.
Usage: .venv/bin/python 22_marker_context.py [marker name ...]
"""
import json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from audio_frames import frame_features

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out"); EP = os.path.join(OUT, "episode")
ingest = json.load(open(os.path.join(OUT, "ingest.json"), encoding="utf-8"))
M = json.load(open(os.path.join(EP, "review-markers.json"), encoding="utf-8"))
only = set(sys.argv[1:])
PAUSE_F, ACTIVE_DB, PRE, POST = 12, -45.0, 75, 100


def tc2f(tc, fps=25):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * fps + f


def words(path, off):
    t = json.load(open(path, encoding="utf-8"))
    return [(tc2f(w["start"]) + off, tc2f(w["end"]) + off, w["text"].strip()) for s in t["segments"]
            for w in s.get("words", []) if w["text"].strip() != "(...)"]


def features(clip, plan):
    cache = os.path.join(EP, clip.split(".")[0] + "-frames.npz")
    if os.path.exists(cache):
        z = np.load(cache); return z["db"], z["voice"]
    db, voice = frame_features(ingest[clip]["wav_path"], plan["fps"], plan["offset_f"], plan["clip_end_f"])
    np.savez_compressed(cache, db=db, voice=voice)
    return db, voice


cache = {}
for m in M:
    if only and m["name"] not in only:
        continue
    clip = m["clip"]
    if clip not in cache:
        plan = json.load(open(os.path.join(EP, clip[5:8] + "-plan.json"), encoding="utf-8"))
        rec = ingest[clip]["rec"]
        cache[clip] = (plan, words(os.path.join(EP, rec + "-Track2-tr.json"), plan["offset_f"]),
                       words(os.path.join(EP, clip.split(".")[0] + "-tr.json"), 0), features(clip, plan))
    plan, W1, W2, (db, _) = cache[clip]
    active = db >= ACTIVE_DB
    a, b = m["src"]
    if b is None or b <= a:                      # range runs past the clip end
        b = plan["clip_end_f"]
    kept = np.zeros(plan["clip_end_f"], bool)
    for x, y in plan["keep_frames"]:
        kept[x:y] = True

    def line(W):
        out, prev_e, opened, closed = [], None, False, False
        for s, e, x in W:
            if e < a - PRE or s > b + POST:
                continue
            if prev_e is not None:
                gap = int((~active[prev_e:max(prev_e, s)]).sum()) if s > prev_e else 0
                if gap >= PAUSE_F:
                    out.append(f"|{gap}")
            mid = (s + e) // 2
            if not opened and mid >= a:
                out.append("[["); opened = True
            if opened and not closed and mid >= b:
                out.append("]]"); closed = True
            out.append(("" if kept[min(mid, len(kept) - 1)] else "~") + x)
            prev_e = e
        if opened and not closed:
            out.append("]]")
        return " ".join(out)

    print(f"\n### {m['name']} {clip} src {a}-{b} ({m['dur_s']}s): {m['note'].strip()}")
    print("  WAV:", line(W1))
    print("  CAM:", line(W2))
