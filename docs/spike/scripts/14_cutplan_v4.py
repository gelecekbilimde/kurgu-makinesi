"""Rough-cut planner v4: transcript decides WHAT to keep, audio decides WHERE the cut goes.

Frame-native throughout (integer camera frames, half-open [start,end) ranges).

0. Hallucination filter: words with < 10% active frames under them are dropped (ASR invents
   stock phrases over silence, e.g. "İzlediğiniz için teşekkür ederim." on a silent track).
1. Word-level decisions (same as v3, plus R2b):
   R1  "bir daha" retake markers -> drop abandoned attempt + marker. Attempt start = earlier
       word matching the restart (first word within NEAR_F, first TWO words up to WINDOW_F),
       else the nearer of sentence start / last pause >= PAUSE_F (transcripts may lack
       punctuation). Attempts longer than MAX_RETAKE_F are NOT removed: only the marker is cut
       and the passage is flagged for review (a wrong removal is worse than an extra take).
   R2  repeated sentence opening -> last take wins
   R2b repeated 3-word phrase (any position) within REPEAT_MAX_SPAN_F (10 s) -> last take wins
       (catches retakes whose "bir daha" the transcript missed)
   R3  orphan fragments between cuts
2. Audio islands: runs of frames louder than ACTIVE_DB (gaps < MERGE_F merged).
3. Ownership: a word owns the chain of islands that ends at the island containing (or just
   before) its END frame, chained backwards while island gaps <= MAX_GAP_F and not past the
   previous word's end. ASR word starts are unreliable (late by up to ~8 frames, or stretched
   over seconds of silence), word ends are better.
4. An island owned by kept words is kept; owned only by removed words or by nobody (breath,
   cough, noise) is dropped. Mixed islands are split at the quietest frame between the last
   removed word and the first kept word.
5. Breath trim. A "breath frame" is quieter than BREATH_DB and weakly voiced (< BREATH_VOICE).
   Tail: sentence-final syllables fade out at -33..-40 dB with weak voicing (unvoiced Turkish
   endings), which is NOT breath (review round 2). So the tail uses a quieter threshold:
   drop a trailing run (>= TAIL_MIN_RUN_F) of frames below TAIL_BREATH_DB only.
   Head: drop a leading run of breath frames (inhale before a word) only if it is at least
   HEAD_MIN_RUN_F long (a 1-2 frame unvoiced onset is a consonant, e.g. 't', 'k', not a breath),
   at most HEAD_TRIM_MAX_F. Padding only extends through true silence (< PAD_SIL_DB), so it
   never reaches into a breath (-45..-50 dB) that follows or precedes a piece; except that every
   piece end gets at least MIN_RELEASE_F frames of release so no ending stops dead.
6. Pieces = kept islands padded PRE_F/POST_F; neighbours merged when the gap between islands
   <= MAX_GAP_F and contains no dropped (noise/removed) island.
7. Second opinion: the same word-level rules run on a SECOND transcript (e.g. Resolve's pass on
   the synced camera clip, already in camera frames). Its removed spans are subtracted from the
   kept audio too (cut points snapped to the quietest frame within +-3). Needed because one ASR
   pass can collapse a whole retake into a single long "word" (seen: "Kasım" = 4.7 s).
9. End hold: the last piece of the clip is held END_HOLD_F frames past its last sound (500 ms rounded
   UP to whole frames: 13 f at 25 fps; reviewer asked for 500 ms instead of 1 s) (capped
   at the camera clip end). A word-final stop can release ~8 frames after the closure ("kavşak":
   burst at +8 f) and the very end of a video needs room anyway (review round 3).
8. Suspicious words (longer than LONG_WORD_F) are reported for human review.
Usage: python 14_cutplan_v4.py transcript.json audio.wav clipname out.json OFFSET_F CLIP_END_F [fps]
                               [--second transcript2.json OFFSET2_F]
"""
import json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from audio_frames import frame_features

args = sys.argv[1:]
second = None
if "--second" in args:
    k = args.index("--second"); second = (args[k + 1], int(args[k + 2])); del args[k:k + 3]
tpath, wav, clip, out = args[0:4]
OFFSET_F, CLIP_END_F = int(args[4]), int(args[5])
FPS = int(args[6]) if len(args) > 6 else 25
P = dict(ACTIVE_DB=-45.0, MERGE_F=3, MAX_GAP_F=11, PRE_F=2, POST_F=3,
         BREATH_DB=-33.0, BREATH_VOICE=0.5, TAIL_BREATH_DB=-42.0, PAD_SIL_DB=-50.0, MIN_RELEASE_F=2, END_HOLD_F=-(-500 * FPS // 1000), TAIL_TRIM_MAX_F=8, TAIL_MIN_RUN_F=3, HEAD_MIN_RUN_F=3, HEAD_TRIM_MAX_F=12, SNAP_F=3, LONG_WORD_F=int(1.6 * FPS), HALLU_MIN_ACTIVE=0.1,
         WINDOW_F=30 * FPS, NEAR_F=10 * FPS, PAUSE_F=12, MAX_RETAKE_F=15 * FPS, REPEAT_MAX_SPAN_F=10 * FPS, ORPHAN_F=int(1.5 * FPS))
G = type("G", (), P)


def tc2f(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * FPS + f


def fmt(fr):
    s, f = divmod(int(fr), FPS)
    return "%d:%02d:%02d" % (s // 60, s % 60, f)


def norm(x):
    return re.sub(r"[^\wçğıöşüâî]", "", x.lower().replace("i̇", "i"))


# ---------------- words + word-level decisions ----------------------------------------
def load_words(path, offset):
    t = json.load(open(path, encoding="utf-8"))
    W = [dict(s=tc2f(w["start"]) + offset, e=tc2f(w["end"]) + offset, x=w["text"].strip())
         for seg in t["segments"] for w in seg.get("words", [])
         if "start" in w and w["text"].strip() != "(...)"]
    outside = [w for w in W if w["s"] < 0 or w["e"] > CLIP_END_F]
    W = [w for w in W if not (w["s"] < 0 or w["e"] > CLIP_END_F)]
    for i, w in enumerate(W):
        w["n"], w["keep"], w["i"] = norm(w["x"]), True, i
    return W, outside


def decide(W, source):
    """Apply R1/R2/R2b/R3 to word list W in place; return (removed spans, review flags)."""
    removed, flags = [], []

    def cut(a, b, kind, how):
        for j in range(a, b + 1):
            W[j]["keep"] = False
        removed.append(dict(kind=kind, start_f=W[a]["s"], end_f=W[b]["e"], how=how, source=source,
                            text=" ".join(w["x"] for w in W[a:b + 1])))

    def is_marker(i):
        return i + 1 < len(W) and W[i]["n"] == "bir" and W[i + 1]["n"] == "daha"

    def nmatch(j, r, n):
        """words j.. match restart words r.. for n words (exact or 5-char prefix)"""
        for q in range(n):
            if j + q >= len(W) or r + q >= len(W):
                return False
            a, b = W[j + q]["n"], W[r + q]["n"]
            if not a or not (a == b or (len(b) >= 5 and a[:5] == b[:5])):
                return False
        return True

    last_cut_end, i = -1, 0
    while i < len(W):                                   # R1
        if not is_marker(i):
            i += 1
            continue
        m0 = i
        while is_marker(i):
            i += 2
        m1, restart = i - 1, i
        # fallback boundary: the nearer of sentence start and the last real pause (>= PAUSE_F)
        k = m0 - 1
        while k > last_cut_end and not re.search(r"[.?!]$", W[k]["x"]):
            k -= 1
        sent_start = k + 1
        # last real pause in the AUDIO before the marker (>= PAUSE_F silent frames); word gaps are
        # useless when a transcript has back-to-back word timings
        fr, run = W[m0]["s"] - 1, 0
        lo = W[last_cut_end]["e"] if last_cut_end >= 0 else 0
        while fr > lo and run < G.PAUSE_F:
            run = run + 1 if not active[fr] else 0
            fr -= 1
        pause_at = fr + run if run >= G.PAUSE_F else lo
        pause_start = next((j for j in range(last_cut_end + 1, m0) if W[j]["e"] > pause_at + 1), m0)
        start, how = max(sent_start, pause_start), "sentence/pause start"
        if restart < len(W):
            for j in range(m0 - 1, last_cut_end, -1):   # near: first word; far: first two words
                dist = W[m0]["s"] - W[j]["s"]
                if dist > G.WINDOW_F:
                    break
                if nmatch(j, restart, 1 if dist <= G.NEAR_F else 2):
                    start, how = j, "matched '%s'" % " ".join(w["x"] for w in W[restart:restart + (1 if dist <= G.NEAR_F else 2)])
                    break
        if W[m1]["e"] - W[start]["s"] > G.MAX_RETAKE_F:   # too long to trust: cut marker only, flag rest
            flags.append(dict(kind="long-retake-review", start_f=W[start]["s"], end_f=W[m0]["s"], source=source,
                              how=f"{how}, {(W[m1]['e'] - W[start]['s']) / FPS:.0f}s > {G.MAX_RETAKE_F / FPS:.0f}s: kept, please review",
                              text=" ".join(w["x"] for w in W[start:m0])))
            cut(m0, m1, "retake-marker", "marker only (long retake flagged)")
        else:
            cut(start, m1, "retake-marker", how)
        last_cut_end = m1

    changed = True                                     # R2 + R2b
    while changed:
        changed = False
        K = [w for w in W if w["keep"]]
        for a in range(len(K) - 2):
            key = tuple(w["n"] for w in K[a:a + 3])
            if not all(key) or max(len(x) for x in key) < 4:
                continue
            for b in range(a + 1, len(K) - 2):
                if K[b]["s"] - K[a]["s"] > G.REPEAT_MAX_SPAN_F:
                    break
                if tuple(w["n"] for w in K[b:b + 3]) == key:
                    if all(K[j + 1]["i"] == K[j]["i"] + 1 for j in range(a, b)):
                        cut(K[a]["i"], K[b]["i"] - 1, "retake-repeat",
                            "phrase '%s' repeated" % " ".join(w["x"] for w in K[a:a + 3]))
                        changed = True
                    break
            if changed:
                break

    isl, cur = [], []                                   # R3
    for w in W:
        if w["keep"]:
            cur.append(w)
        else:
            if cur:
                isl.append(cur)
            cur = []
    for s_ in isl:
        f0, l0 = s_[0]["i"], s_[-1]["i"]
        if f0 > 0 and not W[f0 - 1]["keep"] and l0 + 1 < len(W) and not W[l0 + 1]["keep"] \
                and len(s_) <= 2 and s_[-1]["e"] - s_[0]["s"] < G.ORPHAN_F:
            cut(f0, l0, "orphan", "fragment between cuts")
    return removed, flags


db, voice = frame_features(wav, FPS, OFFSET_F, CLIP_END_F)
active = db >= G.ACTIVE_DB


def drop_hallucinated(W):
    """0. Words with (almost) no sound under them are ASR hallucinations (Whisper-style models
    invent stock phrases over silence, e.g. 'İzlediğiniz için teşekkür ederim.' x7 on a silent
    recorder track). Rule: < HALLU_MIN_ACTIVE of the frames in [s-2, e+2) are active."""
    keep, gone = [], []
    for w in W:
        a, b = max(0, w["s"] - 2), min(CLIP_END_F, w["e"] + 2)
        frac = active[a:b].mean() if b > a else 0.0
        (keep if frac >= G.HALLU_MIN_ACTIVE else gone).append(w)
    for i, w in enumerate(keep):
        w["i"] = i
    return keep, gone


W, outside = load_words(tpath, OFFSET_F)
W, hallucinated = drop_hallucinated(W)
removed, review_flags = decide(W, "primary")
second_removed = []
if second:
    W2, _ = load_words(*second)
    W2, _h2 = drop_hallucinated(W2)
    second_removed, flags2 = decide(W2, "second")
    review_flags += flags2
long_words = [dict(start_f=w["s"], end_f=w["e"], text=w["x"]) for w in W if w["e"] - w["s"] > G.LONG_WORD_F]

# ---------------- audio islands ----------------------------------------------------------
islands, f = [], 0
while f < CLIP_END_F:
    if active[f]:
        g = f
        while g < CLIP_END_F and active[g]:
            g += 1
        if islands and f - islands[-1][1] < G.MERGE_F:
            islands[-1][1] = g
        else:
            islands.append([f, g])
        f = g
    else:
        f += 1
islands = [dict(s=a, e=b, owners=set()) for a, b in islands]


def island_at_or_before(fr):
    best = None
    for k, I in enumerate(islands):
        if I["s"] <= fr:
            best = k
        else:
            break
    return best


for w in W:                                          # ownership chains
    k = island_at_or_before(w["e"] - 1)
    if k is None:
        continue
    prev_end = W[w["i"] - 1]["e"] if w["i"] > 0 else -1
    if islands[k]["e"] < w["s"] - G.MAX_GAP_F:      # nearest island ends long before the word: none
        continue
    islands[k]["owners"].add(w["i"])
    while k > 0 and islands[k]["s"] - islands[k - 1]["e"] <= G.MAX_GAP_F and islands[k - 1]["e"] > max(prev_end, w["s"] - G.MAX_GAP_F) \
            and islands[k - 1]["s"] >= w["s"] - 2 * G.MAX_GAP_F:
        k -= 1
        islands[k]["owners"].add(w["i"])

# keep / drop / split
segs = []   # [start, end, kind] kind in {"keep","drop"}
for I in islands:
    own = sorted(I["owners"])
    if not own:
        segs.append([I["s"], I["e"], "noise"]); continue
    flags = [W[o]["keep"] for o in own]
    if all(flags):
        segs.append([I["s"], I["e"], "keep"]); continue
    if not any(flags):
        segs.append([I["s"], I["e"], "removed"]); continue
    # mixed: split at quietest frame between runs of removed/kept owners (in word order)
    pos = I["s"]
    for a, b in zip(own, own[1:]):
        if W[a]["keep"] != W[b]["keep"]:
            lo, hi = max(pos + 1, W[a]["e"] - 3), min(I["e"] - 1, W[b]["s"] + 3)
            split = min(range(lo, hi + 1), key=lambda fr: db[fr]) if hi >= lo else W[b]["s"]
            segs.append([pos, split, "keep" if W[a]["keep"] else "removed"])
            pos = split
    segs.append([pos, I["e"], "keep" if W[own[-1]]["keep"] else "removed"])

# second opinion: subtract its removed spans (those not already covered by primary removals)
def covered(span):
    return any(r["start_f"] <= span["start_f"] + 5 and r["end_f"] >= span["end_f"] - 5 for r in removed)


def snap(fr):
    lo, hi = max(0, fr - G.SNAP_F), min(CLIP_END_F - 1, fr + G.SNAP_F)
    return min(range(lo, hi + 1), key=lambda x: db[x])


extra = [r for r in second_removed if not covered(r)]
for r in extra:
    a, b = snap(r["start_f"]), snap(r["end_f"])
    new = []
    for sg in segs:
        if sg[2] != "keep" or sg[1] <= a or sg[0] >= b:
            new.append(sg); continue
        if sg[0] < a: new.append([sg[0], a, "keep"])
        new.append([max(sg[0], a), min(sg[1], b), "removed"])
        if sg[1] > b: new.append([b, sg[1], "keep"])
    segs = new
removed += extra

# breath trim on kept segments
def breath(fr):
    return db[fr] < G.BREATH_DB and voice[fr] < G.BREATH_VOICE


trims = head_trims = 0
for sg in segs:
    if sg[2] != "keep":
        continue
    n = 0
    while n < G.TAIL_TRIM_MAX_F and sg[1] - 1 - n > sg[0] and db[sg[1] - 1 - n] < G.TAIL_BREATH_DB \
            and voice[sg[1] - 1 - n] < G.BREATH_VOICE:
        n += 1
    if n >= G.TAIL_MIN_RUN_F:
        sg[1] -= n; trims += n
    run = 0
    while run < G.HEAD_TRIM_MAX_F and sg[0] + run < sg[1] - 1 and breath(sg[0] + run):
        run += 1
    if run >= G.HEAD_MIN_RUN_F:
        sg[0] += run; head_trims += run
    sg.append(sg[0])  # remember trimmed edges for padding rules
    sg.append(sg[1])


def pad_before(fr, n):
    """extend start back by up to n frames, but only through silent (inactive) frames"""
    k = 0
    while k < n and fr - k - 1 >= 0 and db[fr - k - 1] < G.PAD_SIL_DB:
        k += 1
    return fr - k


def pad_after(fr, n):
    k = 0
    while k < n and fr + k < CLIP_END_F and (k < G.MIN_RELEASE_F or db[fr + k] < G.PAD_SIL_DB):
        k += 1
    return fr + k


# assemble pieces
pieces = []
for k, s in enumerate(segs):
    if s[2] != "keep":
        continue
    a, b = pad_before(s[0], G.PRE_F), pad_after(s[1], G.POST_F)
    if pieces:
        pa, pb, last_k = pieces[-1]
        between = segs[last_k + 1:k]
        noisy = any(x[2] != "keep" for x in between)
        if s[0] - segs[last_k][1] <= G.MAX_GAP_F and not noisy:
            pieces[-1] = [pa, b, k]; continue
        a = max(a, pb)
    pieces.append([a, b, k])
if pieces:                                                   # 9. end hold
    last_seg = segs[pieces[-1][2]]
    pieces[-1][1] = max(pieces[-1][1], min(CLIP_END_F, last_seg[1] + G.END_HOLD_F))
keep = [[a, b] for a, b, _ in pieces if b > a]

noise = [s for s in segs if s[2] == "noise"]
removed.sort(key=lambda r: r["start_f"])
plan = dict(version=4, review_flags=review_flags, long_words=long_words, hallucinated=" ".join(w["x"] for w in hallucinated), second_transcript=second[0] if second else None, units="frames", range="half-open [start,end)", clip=clip, fps=FPS,
            offset_f=OFFSET_F, clip_end_f=CLIP_END_F, keep_frames=keep, removed=removed,
            noise_islands=[[x[0], x[1]] for x in noise], tail_trim_frames=trims, head_trim_frames=head_trims,
            dropped_outside_clip=" ".join(w["x"] for w in outside),
            kept_text=" ".join(w["x"] for w in W if w["keep"]), params=P)
json.dump(plan, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

tot = sum(b - a for a, b in keep)
print(f"{clip}: source {CLIP_END_F} f ({fmt(CLIP_END_F)}) -> rough cut {tot} f ({fmt(tot)}), {len(keep)} pieces")
for kind in ["retake-marker", "retake-repeat", "orphan"]:
    print(f"  {kind}: {sum(r['kind'] == kind for r in removed)}")
print(f"  added from second transcript: {len(extra)}")
for fl in review_flags:
    print(f"  REVIEW {fl['source'][:3]} {fmt(fl['start_f'])}-{fmt(fl['end_f'])} [{fl['how']}] {fl['text'][:70]}")
if hallucinated:
    print(f"  dropped {len(hallucinated)} words with no sound under them (ASR hallucination): {' '.join(w['x'] for w in hallucinated)[:120]}")
for w in long_words:
    print(f"  LONG WORD (review) {fmt(w['start_f'])}-{fmt(w['end_f'])} {w['end_f'] - w['start_f']} f: {w['text']}")
print(f"  audio islands: {len(islands)}  noise islands dropped: {len(noise)}  breath frames trimmed: tail {trims}, head {head_trims}")
for r in plan["removed"]:
    print(f"  {r['kind']:14} {r['source'][:3]} {fmt(r['start_f'])}-{fmt(r['end_f'])} [{r['how']}] {r['text'][:75]}")
