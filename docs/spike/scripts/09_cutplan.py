"""Build a rough-cut plan from a Resolve word-level transcription (throwaway spike), v3.

v3: FRAME-NATIVE. All positions are integer frames at the project/camera frame rate.
Transcript timecodes are converted straight to frame numbers (no seconds, no rounding),
the sync offset is a whole number of frames, and every pad/threshold is in frames.
Keep ranges are half-open [start, end): end is exclusive, matching Resolve's
AppendToTimeline clipInfo (duration = endFrame - startFrame).

Input transcript should come from the clean recorder WAV; OFFSET_F maps WAV frames -> camera
source frames (372/087: Resolve reported -9.5 frames linked-audio offset, measured +0.38 s
= +9.5 frames for words; rounded to +10). CLIP_END_F = camera clip length in frames.

Rules:
  R1 "bir daha" marker: for each run of markers, cut from the start of the abandoned attempt
     through the marker. Attempt start = latest earlier word (after previous cut, within
     WINDOW_F) matching the first word after the marker; else start of the sentence.
  R2 repeated opening (retake without a marker): if a sentence's first 3 words reappear as the
     opening of a later sentence within REPEAT_MAX_SPAN_F, drop from the earlier opening to the
     later one ("last take wins").
  R3 orphans: a kept island of <= 2 words / < ORPHAN_F frames between two cuts is dropped.
  R4 head/tail + pauses: drop before first / after last kept word; gaps > MAX_GAP_F shortened.
Usage: python3 09_cutplan.py transcript.json clipname out_plan.json OFFSET_F CLIP_END_F [fps]
"""
import json, re, sys

tpath, clip, out = sys.argv[1:4]
OFFSET_F, CLIP_END_F = int(sys.argv[4]), int(sys.argv[5])
FPS = int(sys.argv[6]) if len(sys.argv) > 6 else 25
# all in frames (values chosen for 25 fps)
PAD_IN_F, PAD_OUT_F, MAX_GAP_F = 3, 5, 11
WINDOW_F, REPEAT_MAX_SPAN_F, ORPHAN_F = 30 * FPS, 20 * FPS, int(1.5 * FPS)


def tc2f(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * FPS + f


def fmt(fr):
    """frames -> m:ss:ff (display only)"""
    s, f = divmod(fr, FPS)
    return "%d:%02d:%02d" % (s // 60, s % 60, f)


def norm(x):
    return re.sub(r"[^\wçğıöşüâî]", "", x.lower().replace("i̇", "i"))


t = json.load(open(tpath, encoding="utf-8"))
assert int(round(float(t.get("fps", FPS)))) == FPS if "fps" in t else True
W = [dict(s=tc2f(w["start"]) + OFFSET_F, e=tc2f(w["end"]) + OFFSET_F, x=w["text"].strip())
     for seg in t["segments"] for w in seg.get("words", [])
     if "start" in w and w["text"].strip() != "(...)"]
outside = [w for w in W if w["s"] < 0 or w["e"] > CLIP_END_F]
W = [w for w in W if not (w["s"] < 0 or w["e"] > CLIP_END_F)]
for i, w in enumerate(W):
    w["n"], w["keep"], w["i"] = norm(w["x"]), True, i
removed = []


def cut(a, b, kind, how):
    for j in range(a, b + 1):
        W[j]["keep"] = False
    removed.append(dict(kind=kind, start_f=W[a]["s"], end_f=W[b]["e"], how=how,
                        text=" ".join(w["x"] for w in W[a:b + 1])))


# --- R1 markers -----------------------------------------------------------------
def is_marker(i):
    return i + 1 < len(W) and W[i]["n"] == "bir" and W[i + 1]["n"] == "daha"


last_cut_end, i = -1, 0
while i < len(W):
    if not is_marker(i):
        i += 1
        continue
    m0 = i
    while is_marker(i):
        i += 2
    m1, restart = i - 1, i
    k = m0 - 1
    while k > last_cut_end and not re.search(r"[.?!]$", W[k]["x"]):
        k -= 1
    start, how = k + 1, "sentence-start"
    if restart < len(W):
        first = W[restart]["n"]
        for j in range(m0 - 1, last_cut_end, -1):
            if W[m0]["s"] - W[j]["s"] > WINDOW_F:
                break
            if W[j]["n"] and (W[j]["n"] == first or (len(first) >= 5 and W[j]["n"][:5] == first[:5])):
                start, how = j, "matched '%s'" % W[restart]["x"]
                break
    cut(start, m1, "retake-marker", how)
    last_cut_end = m1


def sentences():
    out, cur = [], []
    for w in W:
        if not w["keep"]:
            if cur:
                out.append(cur)
            cur = []
            continue
        cur.append(w)
        if re.search(r"[.?!]$", w["x"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


# --- R2 repeated openings -------------------------------------------------------------
changed = True
while changed:
    changed = False
    S = [s for s in sentences() if len(s) >= 3]
    for a_idx, a in enumerate(S):
        key = tuple(w["n"] for w in a[:3])
        for b in S[a_idx + 1:]:
            if b[0]["s"] - a[0]["s"] > REPEAT_MAX_SPAN_F:
                break
            if tuple(w["n"] for w in b[:3]) == key:
                cut(a[0]["i"], b[0]["i"] - 1, "retake-repeat", "opening '%s' repeated" % " ".join(w["x"] for w in a[:3]))
                changed = True
                break
        if changed:
            break

# --- R3 orphans ---------------------------------------------------------------------
isl, cur = [], []
for w in W:
    if w["keep"]:
        cur.append(w)
    else:
        if cur:
            isl.append(cur)
        cur = []
if cur:
    isl.append(cur)
for s in isl:
    first, last = s[0]["i"], s[-1]["i"]
    bounded = first > 0 and not W[first - 1]["keep"] and last + 1 < len(W) and not W[last + 1]["keep"]
    if bounded and len(s) <= 2 and s[-1]["e"] - s[0]["s"] < ORPHAN_F:
        cut(first, last, "orphan", "fragment between cuts")

# --- R4 keep ranges [start, end) in frames + pause compression ---------------------------
kept = [w for w in W if w["keep"]]
keep = []
cur = [max(0, kept[0]["s"] - PAD_IN_F), kept[0]["e"] + PAD_OUT_F]
for a, b in zip(kept, kept[1:]):
    gap, contiguous = b["s"] - a["e"], b["i"] == a["i"] + 1
    if contiguous and gap <= MAX_GAP_F:
        cur[1] = b["e"] + PAD_OUT_F
        continue
    if contiguous:
        cur[1] = min(cur[1], b["s"] - PAD_IN_F)
        removed.append(dict(kind="pause", start_f=cur[1], end_f=b["s"] - PAD_IN_F, how="gap %d frames" % gap, text=""))
    keep.append(cur)
    cur = [max(b["s"] - PAD_IN_F, cur[1]), b["e"] + PAD_OUT_F]
cur[1] = min(cur[1], CLIP_END_F)
keep.append(cur)
keep = [r for r in keep if r[1] > r[0]]
removed.sort(key=lambda r: r["start_f"])

plan = dict(version=3, units="frames", range="half-open [start,end)", clip=clip, fps=FPS,
            offset_f=OFFSET_F, clip_end_f=CLIP_END_F, keep_frames=keep, removed=removed,
            dropped_outside_clip=" ".join(w["x"] for w in outside),
            kept_text=" ".join(w["x"] for w in kept),
            params=dict(PAD_IN_F=PAD_IN_F, PAD_OUT_F=PAD_OUT_F, MAX_GAP_F=MAX_GAP_F, WINDOW_F=WINDOW_F,
                        REPEAT_MAX_SPAN_F=REPEAT_MAX_SPAN_F, ORPHAN_F=ORPHAN_F))
json.dump(plan, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

tot = sum(b - a for a, b in keep)
print(f"{clip}: source {CLIP_END_F} f ({fmt(CLIP_END_F)}) -> rough cut {tot} f ({fmt(tot)}), {len(keep)} pieces")
for kind in ["retake-marker", "retake-repeat", "orphan", "pause"]:
    print(f"  {kind}: {sum(r['kind'] == kind for r in removed)}")
if outside:
    print("  outside camera range (dropped):", plan["dropped_outside_clip"])
for r in removed:
    if r["kind"] != "pause":
        print(f"  {r['kind']:14} {fmt(r['start_f'])}-{fmt(r['end_f'])} [{r['how']}] {r['text'][:90]}")
