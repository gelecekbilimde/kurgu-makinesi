"""Rough-cut planner v5: transcript decides WHAT to keep, audio decides WHERE the cut goes.

Frame-native throughout (integer camera frames, half-open [start,end) ranges).
v5 = v4 (audio islands, ownership, breath trim, padding, second opinion, end hold; see 14_cutplan_v4.py)
with a rewritten retake engine, driven by the episode review (log Part 7, 36 reviewer markers):

0. Hallucinations: words with no sound under them (v4) + Whisper stock phrases ("İzlediğiniz için
   teşekkür ederim", "Altyazı M.K.", "abone ol") dropped even when a cough sits under them.
1. Units: words are grouped into units split at sentence punctuation (incl. "...") and at audio
   pauses >= PAUSE_F. A "bir daha" inside a unit splits it, so a unit is either speech or cue.
2. Cue units: "bir daha" (+ absorbed "dur/tekrar/şöyle/yapalım/olmadı/bu/burayı" after it); short
   units with "tekrar/dur/durun/pardon/olmadı/baştan"; short units with a meta verb
   ("yapalım/yapmayalım/çekelim"); discard units ("boşver/neyse/uzatmayalım/uzadı").
   Consecutive cue units form one CLUSTER (e.g. "Bir daha, bir daha dur. Bol yapmayalım burayı. Tekrar.").
3. Restart text R = the speech after the cluster (skipping later cue units, so a chain of failed
   attempts is compared with the FINAL take), extended with the next clip's head when the clip ends.
4. Attempt = the speech the restart replaces, found by walking back unit by unit from the cluster:
   - the unit right before the cluster is always part of it (fixes v4 cutting only "Bir daha."
     when the cue is its own sentence), unless R's first content word appears inside it, then the
     attempt starts at that word (v4's restart match, now ignoring stop words: "bir" matched "bir");
   - earlier units are included while their content overlaps R (IDF-weighted stem overlap >= OVERLAP)
   - never past the previous cut, never more than WINDOW_F back.
   Strong clusters ("bir daha", discard words) always cut. Weak clusters ("Tekrar.", "Durun.", meta
   verbs) cut only when the previous unit overlaps R (evidence of a real retake), else become a
   suggestion. Discard clusters ("Neyse boşver, uzatmayalım") remove back to the previous cut.
   Attempts longer than MAX_RETAKE_F: only the immediate unit + cue are cut; the rest is flagged.
5. Abandoned units: a unit trailing off in "..." whose content the next words repeat -> cut.
6. Heading numbers read aloud on their own ("3.3") -> cut.
7. Cross-clip retake: when the clip's last unit is re-said at the head of the next clip -> cut it
   (walk back like a cue).
8. R2/R2b repeated phrases (v4); R3 orphans now run AFTER the second transcript's cuts are applied
   to the primary words, and allow up to 3 words / 2.5 s.
9. Suggestions (never auto-removed, become ranged markers for the editor): "swallowed retake"
   = a long word with far more speech under it than its letters (> SWALLOW_DENS active frames per
   letter; ASR collapsed a silent restart into it); weak cues without evidence; long retakes.
10. Editor overrides (--edits file): source-frame ranges the reviewer marked for removal.
Usage: python 23_cutplan_v5.py transcript.json audio.wav clipname out.json OFFSET_F CLIP_END_F [fps]
          [--second transcript2.json OFFSET2_F] [--next next_transcript.json NEXT_OFFSET_F]
          [--edits edits.json]
"""
import json, math, re, sys, os
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
from audio_frames import frame_features

args = sys.argv[1:]


def opt(name, n):
    if name not in args:
        return None
    k = args.index(name); v = args[k + 1:k + 1 + n]; del args[k:k + 1 + n]
    return v


second = opt("--second", 2); second = (second[0], int(second[1])) if second else None
nxt = opt("--next", 2); nxt = (nxt[0], int(nxt[1])) if nxt else None
edits = opt("--edits", 1); edits = edits[0] if edits else None
tpath, wav, clip, out = args[0:4]
OFFSET_F, CLIP_END_F = int(args[4]), int(args[5])
FPS = int(args[6]) if len(args) > 6 else 25
P = dict(ACTIVE_DB=-45.0, MERGE_F=3, MAX_GAP_F=11, PRE_F=2, POST_F=3,
         BREATH_DB=-33.0, BREATH_VOICE=0.5, TAIL_BREATH_DB=-42.0, PAD_SIL_DB=-50.0, MIN_RELEASE_F=2,
         END_HOLD_F=-(-500 * FPS // 1000), TAIL_TRIM_MAX_F=8, TAIL_MIN_RUN_F=3, HEAD_MIN_RUN_F=3,
         HEAD_TRIM_MAX_F=12, SNAP_F=3, LONG_WORD_F=int(1.6 * FPS), HALLU_MIN_ACTIVE=0.1,
         WINDOW_F=30 * FPS, NEAR_F=10 * FPS, PAUSE_F=12, PAUSE_NOPUNCT_F=6, IMM_MAX_F=6 * FPS, MAX_RETAKE_F=30 * FPS,
         REPEAT_MAX_SPAN_F=20 * FPS, R_FIRST=6, FIRST_OVERLAP=0.4,
         ORPHAN_WORDS=3, ORPHAN_F=int(2.5 * FPS), OVERLAP=0.5, OVERLAP2=0.35, WEAK_EVIDENCE=0.3, R_MIN=25, R_MAX=120,
         SWALLOW_DENS=8.0, SWALLOW_GAP_F=3, SPLIT_TOL_DB=2.0, DANGLING_WORDS=2)
G = type("G", (), P)

STOP = set("""ve bir bu da de ki mi mı mu mü ne o şu ile için gibi ama yani işte peki şimdi daha çok en her
olarak olan var yok değil ya ise kadar sonra önce burada orada şey diye evet hayır tabi tabii aslında
zaten hem veya sadece bile çünkü eğer gelelim bakalım isterseniz arkadaşlar biz siz ben sen onlar
bunu bunun buna şunu onu onun dedik dediğimiz mesela örneğin diğer""".split())
ABSORB = {"dur", "durun", "tekrar", "şöyle", "yapalım", "olmadı", "bu", "burayı", "pardon"}  # only as a whole unit tail
TRIG = {"tekrar", "dur", "durun", "pardon", "olmadı", "baştan"}
META = {"yapalım", "yapmayalım", "çekelim"}
DISCARD = {"boşver", "neyse", "uzatmayalım", "uzadı"}
DEBUG = os.environ.get("PLAN_DEBUG") == "1"
HALLU_PHRASES = ["izlediğiniz için teşekkür ederim", "altyazı mk", "abone ol"]


def tc2f(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * FPS + f


def fmt(fr):
    s, f = divmod(int(fr), FPS)
    return "%d:%02d:%02d" % (s // 60, s % 60, f)


def norm(x):
    return re.sub(r"[^\wçğıöşüâî]", "", x.lower().replace("i̇", "i"))


def stem(n):
    m = re.match(r"\d+", n)
    return m.group(0) if m else n[:5]               # "2015'te" -> "2015"


def content(n):
    return bool(n) and n not in STOP


db, voice = frame_features(wav, FPS, OFFSET_F, CLIP_END_F)
active = db >= G.ACTIVE_DB


# ---------------- words ------------------------------------------------------------------
def load_words(path, offset, end=CLIP_END_F):
    t = json.load(open(path, encoding="utf-8"))
    W = [dict(s=tc2f(w["start"]) + offset, e=tc2f(w["end"]) + offset, x=w["text"].strip())
         for seg in t["segments"] for w in seg.get("words", [])
         if "start" in w and w["text"].strip() != "(...)"]
    outside = [w for w in W if w["s"] < 0 or w["e"] > end]
    W = [w for w in W if not (w["s"] < 0 or w["e"] > end)]
    for i, w in enumerate(W):
        w["n"], w["keep"], w["i"] = norm(w["x"]), True, i
    return W, outside


def drop_phrases(W):
    """Drop Whisper stock phrases (matched on normalised word sequences)."""
    gone = set()
    for ph in HALLU_PHRASES:
        p = [norm(x) for x in ph.split()]
        for i in range(len(W) - len(p) + 1):
            if [W[i + k]["n"] for k in range(len(p))] == p:
                gone.update(range(i, i + len(p)))
    return [w for i, w in enumerate(W) if i not in gone], [w for i, w in enumerate(W) if i in gone]


def drop_hallucinated(W):
    """Words with (almost) no sound under them, and stock phrases, are ASR hallucinations."""
    keep, gone = [], []
    for w in W:
        a, b = max(0, w["s"] - 2), min(CLIP_END_F, w["e"] + 2)
        frac = active[a:b].mean() if b > a else 0.0
        (keep if frac >= G.HALLU_MIN_ACTIVE else gone).append(w)
    keep, g2 = drop_phrases(keep)
    for i, w in enumerate(keep):
        w["i"] = i
    return keep, gone + g2


def next_head(path, offset, n=60):
    """First n content-bearing words of the next clip (camera frames >= 0), for cross-clip retakes."""
    W, _ = load_words(path, offset, end=10 ** 9)
    W, _ = drop_phrases(W)
    return [w["n"] for w in W[:n]]


# ---------------- retake engine ------------------------------------------------------------
def decide(W, source, head_next):
    removed, flags, sugg = [], [], []
    df = Counter()

    def cut(a, b, kind, how):
        for j in range(a, b + 1):
            W[j]["keep"] = False
        removed.append(dict(kind=kind, start_f=W[a]["s"], end_f=W[b]["e"], how=how, source=source,
                            text=" ".join(w["x"] for w in W[a:b + 1])))

    # 1. units ---------------------------------------------------------------------------
    U, cur = [], []
    punct = sum(bool(re.search(r"[.?!…]$", w["x"])) for w in W)
    nopunct = punct * 40 < len(W)
    pause_f = G.PAUSE_NOPUNCT_F if nopunct else G.PAUSE_F    # no punctuation: split at shorter pauses
    for i, w in enumerate(W):
        if cur:
            pv = W[cur[-1]]
            gap = int((~active[pv["e"]:max(pv["e"], w["s"])]).sum())
            if re.search(r"[.?!…]$", pv["x"]) or gap >= pause_f:
                U.append(cur); cur = []
        cur.append(i)
    if cur:
        U.append(cur)
    # split at "bir daha" spans
    U2 = []
    for u in U:
        k, start = 0, 0
        while k < len(u) - 1:
            if W[u[k]]["n"] == "bir" and W[u[k + 1]]["n"] == "daha":
                e = k + 2
                while e + 1 < len(u) and W[u[e]]["n"] == "bir" and W[u[e + 1]]["n"] == "daha":
                    e += 2
                if all(W[i]["n"] in ABSORB | {"bir", "daha"} for i in u[e:]):
                    e = len(u)                       # "Bir daha şöyle yapalım." / "Bir daha olmadı bu."
                else:
                    while e < len(u) and W[u[e]]["n"] in ABSORB - {"bu", "burayı"}:
                        e += 1                       # "bir daha şöyle yapalım yetmez..." but not "bir daha. Bu yüzden"

                if u[start:k]:
                    U2.append(u[start:k])
                U2.append(u[k:e]); start = k = e
            else:
                k += 1
        if u[start:]:
            U2.append(u[start:])
    U = U2
    for u in U:
        df.update({stem(W[i]["n"]) for i in u if content(W[i]["n"])})
    NU = max(1, len(U))

    def idf(s):
        return math.log((NU + 1) / (1 + df[s])) + 0.1

    def kind_of(u):
        ns = [W[i]["n"] for i in u]
        if any(ns[k] == "bir" and ns[k + 1] == "daha" for k in range(len(ns) - 1)):
            return "strong"
        if any(n in DISCARD for n in ns) and len(ns) <= 8:
            return "discard"
        if len(ns) <= 4 and any(n in TRIG for n in ns):
            return "weak"
        if len(ns) <= 5 and any(n in META for n in ns) and \
                sum(content(n) and n not in META and n not in TRIG for n in ns) <= 2:
            return "weak"
        return None

    kinds = [kind_of(u) for u in U]

    def stems(idx):
        return [stem(W[i]["n"]) for i in idx if content(W[i]["n"])]

    def score(u, R):
        st = set(stems(u))
        if not st:
            return 0.0
        tot = sum(idf(s) for s in st)
        return sum(idf(s) for s in st if s in R) / tot

    def restart_words(ci, n):
        """content stems after cluster ending at unit ci (skipping cue units), + next clip head."""
        out = []
        for k in range(ci + 1, len(U)):
            if kinds[k] or not any(W[i]["keep"] for i in U[k]):
                continue
            out += stems(U[k])
            if len(out) >= n:
                return out[:n]
        out += [stem(x) for x in (head_next or []) if content(x)]
        return out[:n]

    def first_restart_word(ci):
        for k in range(ci + 1, len(U)):
            if kinds[k] or not any(W[i]["keep"] for i in U[k]):
                continue
            for i in U[k]:
                if content(W[i]["n"]) and W[i]["n"] not in ABSORB | META | TRIG:
                    return W[i]["n"]
        for x in head_next or []:
            if content(x):
                return x
        return None

    def rsize(n_att):
        return max(G.R_MIN, min(G.R_MAX, 3 * n_att + 20))

    def skippable(i):
        return not content(W[i]["n"]) or re.fullmatch(r"\d+\.\d+\.?", W[i]["x"])

    def walk_back(c0, ci, strong, last_cut_unit):
        """units of the attempt replaced by the restart after cluster [c0..ci]; returns (start word, how)"""
        if c0 - 1 <= last_cut_unit:
            return None, "nothing before cue"
        first = U[c0 - 1]
        if nopunct and W[first[-1]]["e"] - W[first[0]]["s"] > G.IMM_MAX_F:   # oversized unit (no punctuation)
            first = [i for i in first if W[i]["s"] >= W[first[-1]]["e"] - G.IMM_MAX_F] or first[-1:]
        n_att = len(stems(first))
        R = set(restart_words(ci, rsize(n_att)))
        if not strong and score(first, R) < G.WEAK_EVIDENCE:
            return None, "weak cue, no evidence"
        rw = first_restart_word(ci)
        if rw:
            hit = [j for j, i in enumerate(first) if W[i]["n"][:4] == rw[:4] and len(W[i]["n"]) >= 4] \
                if len(rw) >= 4 else [j for j, i in enumerate(first) if W[i]["n"] == rw]
            # restart word inside the attempt: start there, unless the words before it are only stop
            # words / a heading number, or are themselves re-said by the restart (then the whole unit)
            if hit and hit[0] > 0 and not all(skippable(i) for i in first[:hit[0]]) \
                    and score(first[:hit[0]], R) < G.OVERLAP:
                return first[hit[0]], f"restart '{rw}' inside attempt"
        if first is not U[c0 - 1]:
            return first[0], "previous unit (last %ds)" % (G.IMM_MAX_F // FPS)
        walked, k = [c0 - 1], c0 - 2
        while k > last_cut_unit and W[U[c0 - 1][0]]["s"] - W[U[k][0]]["s"] <= G.WINDOW_F:
            if kinds[k] or not all(W[i]["keep"] for i in U[k]):
                break
            n_att += len(stems(U[k]))
            R = set(restart_words(ci, rsize(n_att)))
            hits = len(set(stems(U[k])) & R)
            if score(U[k], R) < G.OVERLAP and not (hits >= 2 and score(U[k], R) >= G.OVERLAP2):
                break
            walked.append(k); k -= 1
        # v4's restart match, restricted to unit starts: a unit within NEAR_F that begins with the
        # restart's first word ("Peki bizim ... | Bir daha. | Peki bunun ...")
        r0 = next((W[i]["n"] for k2 in range(ci + 1, len(U)) if not kinds[k2] and any(W[j]["keep"] for j in U[k2])
                   for i in U[k2][:1]), None)
        k = walked[-1] - 1
        while r0 and k > last_cut_unit and not kinds[k] and W[U[c0][0]]["s"] - W[U[k][0]]["s"] <= G.NEAR_F \
                and all(W[i]["keep"] for i in U[k]):
            if W[U[k][0]]["n"] == r0:
                return U[k][0], f"unit starts like the restart ('{W[U[k][0]]['x']}')"
            k -= 1
        # two-word unit-start match up to WINDOW_F ("Peki gelelim nihai soruya ... | Peki gelelim zurnanın ...")
        r01 = next(([W[i]["n"] for i in U[k2][:2]] for k2 in range(ci + 1, len(U))
                    if not kinds[k2] and any(W[j]["keep"] for j in U[k2]) and len(U[k2]) >= 2), None)
        k = walked[-1] - 1
        if r01 and not any(content(x) for x in r01):
            r01 = None                           # "Bir diğer ..." / "Peki gelelim ...": list openers, too weak
        while r01 and k > last_cut_unit and not kinds[k] and W[U[c0][0]]["s"] - W[U[k][0]]["s"] <= G.WINDOW_F \
                and all(W[i]["keep"] for i in U[k]):
            if [W[i]["n"] for i in U[k][:2]] == r01:
                return U[k][0], f"unit starts like the restart ('{' '.join(W[i]['x'] for i in U[k][:2])}')"
            k -= 1
        if len(walked) == 1:
            return first[0], "previous unit"
        # the restart re-says the attempt from its beginning: start at the earliest walked unit that
        # overlaps the first words of the restart (else only the unit right before the cue)
        RF = set(restart_words(ci, G.R_FIRST))
        for k in reversed(walked[1:]):
            if score(U[k], RF) >= G.FIRST_OVERLAP or W[U[k][0]]["n"] == r0:
                return U[k][0], "content overlap with restart"
        return first[0], "previous unit"

    # 2-4. clusters, processed RIGHT TO LEFT: when an earlier cluster is handled, the later failed
    # attempts are already removed, so its restart text R is the final take
    clusters, k = [], 0
    while k < len(U):
        if not kinds[k]:
            k += 1; continue
        c0 = k
        while k + 1 < len(U) and kinds[k + 1]:
            k += 1
        clusters.append((c0, k)); k += 1
    order = [n for n in reversed(range(len(clusters))) if "discard" not in kinds[clusters[n][0]:clusters[n][1] + 1]]
    order += [n for n in reversed(range(len(clusters))) if "discard" in kinds[clusters[n][0]:clusters[n][1] + 1]]
    for n in order:                          # discard clusters last, so the retakes inside a dropped
        c0, ci = clusters[n]                 # digression still see their own restart text
        last_cut_unit = clusters[n - 1][1] if n > 0 else -1
        ks = [kinds[j] for j in range(c0, ci + 1)]
        strong = "strong" in ks or "discard" in ks
        cue_txt = " ".join(W[i]["x"] for j in range(c0, ci + 1) for i in U[j])
        a_end = U[ci][-1]
        if "discard" in ks:
            j = c0 - 1
            while j > last_cut_unit and W[U[c0][0]]["s"] - W[U[j][0]]["s"] <= G.WINDOW_F and not kinds[j]:
                j -= 1
            start, how = (U[j + 1][0] if j + 1 < c0 else None), "discard: back to previous cut"
        else:
            start, how = walk_back(c0, ci, strong, last_cut_unit)
        if DEBUG and start is None:
            print(f"   [{source[:3]}] {fmt(W[U[c0][0]]['s'])} cue-only «{cue_txt}» ({how})")
        if start is None:
            if strong:
                cut(U[c0][0], a_end, "retake-marker", "cue only (" + how + ")")
            else:
                sugg.append(dict(kind="weak-cue", start_f=W[U[c0][0]]["s"], end_f=W[a_end]["e"], source=source,
                                 how=how, text=cue_txt))
            continue
        if W[a_end]["e"] - W[start]["s"] > G.MAX_RETAKE_F:
            imm = U[c0 - 1][0]
            flags.append(dict(kind="long-retake-review", start_f=W[start]["s"], end_f=W[imm]["s"], source=source,
                              how=f"{how}, {(W[a_end]['e'] - W[start]['s']) / FPS:.0f}s > {G.MAX_RETAKE_F / FPS:.0f}s: kept, please review",
                              text=" ".join(w["x"] for w in W[start:imm])))
            start, how = imm, "previous unit only (long retake flagged)"
        cut(start, a_end, "retake-marker", f"{how} [{cue_txt}]")
        if DEBUG:
            print(f"   [{source[:3]}] {fmt(W[start]['s'])} CUT «{' '.join(w['x'] for w in W[start:a_end + 1])[:150]}» ({how})")

    # 5. abandoned "..." units, 6. heading numbers, 7. cross-clip tail ------------------------
    for k, u in enumerate(U):
        if kinds[k] or not all(W[i]["keep"] for i in u):
            continue
        if re.fullmatch(r"\d+\.\d+\.?", W[u[0]]["x"]) and len(u) == 1:
            cut(u[0], u[0], "heading-number", "section number read aloud")
            continue
        gap_after = int((~active[W[u[-1]]["e"]:W[u[-1] + 1]["s"]]).sum()) if u[-1] + 1 < len(W) else 0
        if (W[u[-1]]["x"].endswith("...") or W[u[-1]]["x"].endswith("…")) and gap_after >= G.PAUSE_F // 2:
            R = set(restart_words(k, 12))
            if score(u, R) >= G.OVERLAP:
                cut(u[0], u[-1], "abandoned", "trails off '...', next words repeat it")
    if head_next:
        tail = [k for k, u in enumerate(U) if all(W[i]["keep"] for i in u) and not kinds[k]]
        if tail:
            R = set(stem(x) for x in head_next[:20] if content(x))
            R40 = set(stem(x) for x in head_next[:40] if content(x))
            last = k = tail[-1]
            if score(U[k], R) < G.OVERLAP and len(U[k]) <= 3 and k - 1 in tail and score(U[k - 1], R) >= G.OVERLAP:
                k -= 1                               # sentence split across the clip cut ("Henüz rakamlar | bir Hollanda...")
            if score(U[k], R) >= G.OVERLAP:
                j = k
                while j - 1 in tail and W[U[k][0]]["s"] - W[U[j - 1][0]]["s"] <= G.WINDOW_F \
                        and score(U[j - 1], R40) >= G.OVERLAP:
                    j -= 1
                cut(U[j][0], U[last][-1], "cross-clip-retake", "clip tail re-said at the head of the next clip")

    # 8. R2 + R2b (v4) -------------------------------------------------------------------
    unit_pos = {}
    for u in U:
        for p_, i in enumerate(u):
            unit_pos[i] = p_
    changed = True
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
                    contiguous = all(K[j + 1]["i"] == K[j]["i"] + 1 for j in range(a, b)) \
                        and K[b]["s"] - K[a]["s"] <= G.REPEAT_MAX_SPAN_F // 2
                    if contiguous or (unit_pos[K[b]["i"]] <= 1 and unit_pos[K[a]["i"]] <= 1):   # v5: across removed cue words / up to
                        # 20 s only when the repeat starts a unit (a restart, not an addition mid-sentence)
                        gap = next((j for j in range(K[a]["i"], K[b]["i"]) if not W[j]["keep"]), K[b]["i"])
                        cut(K[a]["i"], gap - 1, "retake-repeat",
                            "phrase '%s' repeated" % " ".join(w["x"] for w in K[a:a + 3]))
                        changed = True
                    break
            if changed:
                break
    return removed, flags, sugg


def orphans(W):
    """R3 on the final word decisions: short kept fragments with removals on both sides."""
    out, isl, cur = [], [], []
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
                and len(s_) <= G.ORPHAN_WORDS and s_[-1]["e"] - s_[0]["s"] < G.ORPHAN_F:
            for w in s_:
                w["keep"] = False
            out.append(dict(kind="orphan", start_f=s_[0]["s"], end_f=s_[-1]["e"], how="fragment between cuts",
                            source="primary", text=" ".join(w["x"] for w in s_)))
    # dangling phrase start: 1-2 kept words that open a phrase (after . ? ! , …) and run straight into
    # removed words, i.e. the rest of their phrase was cut ("…yarıya indirmek, sırayla | <cut>",
    # "…çekildi. Ama şu | <cut>")
    for k, w in enumerate(W):
        if not w["keep"] or k + 1 >= len(W) or W[k + 1]["keep"] or re.search(r"[.?!,…]$", w["x"]):
            continue
        j = k
        while j - 1 >= 0 and W[j - 1]["keep"] and k - j < G.DANGLING_WORDS and not re.search(r"[.?!,…]$", W[j - 1]["x"]):
            j -= 1
        # only when the cut is the editor's or the second transcript's (its attempt start is a guess:
        # "…çekildi. Ama | şu rakama…" left "Ama"), or the restart after the cut opens with the same word (the
        # dangling words belong to the attempt); NOT before a retake whose restart they lead into
        # ("Şimdi gelelim | <attempt> | COP31 bu zincirin neresinde?")
        nk = next((x["n"] for x in W[k + 1:] if x["keep"]), None) or (head[0] if head else None)
        if not (W[k + 1].get("ed") or W[k + 1].get("sec") or nk == W[j]["n"]):
            continue
        if j - 1 >= 0 and W[j - 1]["keep"] and re.search(r"[.?!,…]$", W[j - 1]["x"]) and k - j < G.DANGLING_WORDS:
            for x in W[j:k + 1]:
                x["keep"] = False
            out.append(dict(kind="orphan", start_f=W[j]["s"], end_f=w["e"], how="dangling phrase start before a cut",
                            source="primary", text=" ".join(x["x"] for x in W[j:k + 1])))
    return out


def swallowed(W):
    """9. Suggestions: kept long words with far more speech under them than letters."""
    out = []
    for w in W:
        if not w["keep"] or w["e"] - w["s"] <= G.LONG_WORD_F:
            continue
        dens = active[max(0, w["s"]):w["e"]].sum() / max(1, len(re.sub(r"\W", "", w["x"])))
        if dens <= G.SWALLOW_DENS:
            continue
        # attempt start: back to the last sentence end / pause / cut before the word
        j = w["i"]
        while j - 1 >= 0 and W[j - 1]["keep"] and not re.search(r"[.?!…]$", W[j - 1]["x"]) \
                and int((~active[W[j - 1]["e"]:max(W[j - 1]["e"], W[j]["s"])]).sum()) < G.PAUSE_F:
            j -= 1
        # restart point: end of the first silence (>= SWALLOW_GAP_F) inside the word's first second
        fr, run, rp = w["s"], 0, w["s"]
        while fr < min(w["e"], w["s"] + FPS):
            run = run + 1 if not active[fr] else 0
            fr += 1
            if run >= G.SWALLOW_GAP_F and fr < CLIP_END_F and active[fr]:
                rp = fr; break
        if j == w["i"]:
            continue
        out.append(dict(kind="swallowed-retake", start_f=W[j]["s"], end_f=rp, source="primary",
                        how=f"'{w['x']}' is {(w['e'] - w['s']) / FPS:.1f}s with {dens:.0f} active f/letter: "
                            f"a restart was probably merged into it", text=" ".join(x["x"] for x in W[j:w["i"] + 1])))
    return out


head = next_head(*nxt) if nxt else None
W, outside = load_words(tpath, OFFSET_F)
W, hallucinated = drop_hallucinated(W)
removed, review_flags, suggestions = decide(W, "primary", head)
second_removed = []
if second:
    W2, _ = load_words(*second)
    W2, _h2 = drop_hallucinated(W2)
    second_removed, flags2, sugg2 = decide(W2, "second", head)
    review_flags += flags2
long_words = [dict(start_f=w["s"], end_f=w["e"], text=w["x"]) for w in W if w["e"] - w["s"] > G.LONG_WORD_F]

edit_rm = []
if edits and os.path.exists(edits):
    edit_rm = [list(x) for x in json.load(open(edits, encoding="utf-8")).get("remove", [])]


def covered(span):
    """A second-transcript cut is skipped when the primary already handles it: fully covered (v4), or,
    for cue-driven retake cuts, when it overlaps a primary retake cut at all (the primary has
    punctuation, so its attempt boundary is better than a 6 s guess on an unpunctuated transcript)."""
    if any(r["start_f"] <= span["start_f"] + 5 and r["end_f"] >= span["end_f"] - 5 for r in removed):
        return True
    return span["kind"] == "retake-marker" and any(
        r["kind"] == "retake-marker" and r["start_f"] < span["end_f"] + 5 and r["end_f"] > span["start_f"] - 5 for r in removed)


extra = [r for r in second_removed if not covered(r)]
# apply the second transcript's and the editor's removals to the primary words before R3
for a, b in [(r["start_f"], r["end_f"]) for r in extra]:
    for w in W:
        if w["keep"] and a <= (w["s"] + w["e"]) // 2 < b:
            w["keep"], w["sec"] = False, True
# editor ranges: only words (almost) entirely inside. A swallowed word (ASR stretched it over a whole
# retake) can start inside the editor's range and hold the final take: marking it removed would drop
# its audio islands too (seen: "1,5" = 157 f, the reviewer's range covered its first 81 f).
for a, b in edit_rm:
    for w in W:
        if w["keep"] and w["e"] > w["s"] and (min(b, w["e"]) - max(a, w["s"])) >= 0.9 * (w["e"] - w["s"]):
            w["keep"], w["ed"] = False, True
removed += orphans(W)
suggestions += swallowed(W)

# ---------------- audio islands (v4) --------------------------------------------------------
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
    if islands[k]["e"] < w["s"] - G.MAX_GAP_F:
        continue
    islands[k]["owners"].add(w["i"])
    while k > 0 and islands[k]["s"] - islands[k - 1]["e"] <= G.MAX_GAP_F and islands[k - 1]["e"] > max(prev_end, w["s"] - G.MAX_GAP_F) \
            and islands[k - 1]["s"] >= w["s"] - 2 * G.MAX_GAP_F:
        k -= 1
        islands[k]["owners"].add(w["i"])

segs = []
for I in islands:
    own = sorted(I["owners"])
    if not own:
        segs.append([I["s"], I["e"], "noise"]); continue
    fl = [W[o]["keep"] for o in own]
    if all(fl):
        segs.append([I["s"], I["e"], "keep"]); continue
    if not any(fl):
        segs.append([I["s"], I["e"], "removed"]); continue
    pos = I["s"]
    for a, b in zip(own, own[1:]):
        if W[a]["keep"] != W[b]["keep"]:
            lo, hi = max(pos + 1, W[a]["e"] - 3), min(I["e"] - 1, W[b]["s"] + 3)
            if hi >= lo:
                # v5: among near-quietest frames (within SPLIT_TOL_DB) favour the KEPT word: split as
                # early as possible when the kept word follows, as late as possible when it precedes
                # (review marker 100: the onset of "COP31" was clipped by a split 3 frames too late)
                m = min(db[fr] for fr in range(lo, hi + 1))
                near = [fr for fr in range(lo, hi + 1) if db[fr] <= m + G.SPLIT_TOL_DB]
                # late split only up to 3 f past the kept word's END (ends are reliable; the removed word's
                # START can be 7+ f late: "…oluyor ama. Elek|trikli" leaked into the kept piece)
                split = near[0] if W[b]["keep"] else max([fr for fr in near if fr <= W[a]["e"] + 3] or near[:1])
            else:
                split = W[b]["s"]
            segs.append([pos, split, "keep" if W[a]["keep"] else "removed"])
            pos = split
    segs.append([pos, I["e"], "keep" if W[own[-1]]["keep"] else "removed"])


def snap(fr):
    lo, hi = max(0, fr - G.SNAP_F), min(CLIP_END_F - 1, fr + G.SNAP_F)
    return min(range(lo, hi + 1), key=lambda x: db[x])


def subtract(segs, a, b):
    new = []
    for sg in segs:
        if sg[2] != "keep" or sg[1] <= a or sg[0] >= b:
            new.append(sg); continue
        if sg[0] < a: new.append([sg[0], a, "keep"])
        new.append([max(sg[0], a), min(sg[1], b), "removed"])
        if sg[1] > b: new.append([b, sg[1], "keep"])
    return new


for r in extra:
    segs = subtract(segs, snap(r["start_f"]), snap(r["end_f"]))
removed += extra
for a, b in edit_rm:                                  # editor ranges are exact: no snapping
    segs = subtract(segs, a, b)
    removed.append(dict(kind="editor", start_f=a, end_f=b, how="reviewer marker", source="edits",
                        text=" ".join(w["x"] for w in W if a <= (w["s"] + w["e"]) // 2 < b)))


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


def pad_before(fr, n):
    k = 0
    while k < n and fr - k - 1 >= 0 and db[fr - k - 1] < G.PAD_SIL_DB:
        k += 1
    return fr - k


def pad_after(fr, n):
    k = 0
    while k < n and fr + k < CLIP_END_F and (k < G.MIN_RELEASE_F or db[fr + k] < G.PAD_SIL_DB):
        k += 1
    return fr + k


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
if pieces:
    last_seg = segs[pieces[-1][2]]
    pieces[-1][1] = max(pieces[-1][1], min(CLIP_END_F, last_seg[1] + G.END_HOLD_F))
keep = [[a, b] for a, b, _ in pieces if b > a]

# suggestions only make sense where something is still kept
kept_fr = [0] * (CLIP_END_F + 1)
for a, b in keep:
    for x in range(a, b):
        kept_fr[x] = 1
for s in suggestions:                                 # start at the first frame that is still kept
    while s["start_f"] < s["end_f"] and not kept_fr[max(0, s["start_f"])]:
        s["start_f"] += 1
suggestions = [s for s in suggestions if s["end_f"] - s["start_f"] >= 6           # still something to decide
               and not any(a < s["end_f"] and b > s["start_f"] for a, b in edit_rm)]  # editor already decided

noise = [s for s in segs if s[2] == "noise"]
removed.sort(key=lambda r: r["start_f"])
plan = dict(version=5, review_flags=review_flags, suggestions=suggestions, long_words=long_words,
            hallucinated=" ".join(w["x"] for w in hallucinated), second_transcript=second[0] if second else None,
            next_transcript=nxt[0] if nxt else None, edits=edits, units="frames", range="half-open [start,end)",
            clip=clip, fps=FPS, offset_f=OFFSET_F, clip_end_f=CLIP_END_F, keep_frames=keep, removed=removed,
            noise_islands=[[x[0], x[1]] for x in noise], tail_trim_frames=trims, head_trim_frames=head_trims,
            dropped_outside_clip=" ".join(w["x"] for w in outside),
            kept_text=" ".join(w["x"] for w in W if w["keep"]), params=P)
json.dump(plan, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

tot = sum(b - a for a, b in keep)
print(f"{clip}: source {CLIP_END_F} f ({fmt(CLIP_END_F)}) -> rough cut {tot} f ({fmt(tot)}), {len(keep)} pieces")
print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(Counter(r["kind"] for r in removed).items())))
print(f"  added from second transcript: {len(extra)}; editor ranges: {len(edit_rm)}")
for fl in review_flags:
    print(f"  REVIEW {fl['source'][:3]} {fmt(fl['start_f'])}-{fmt(fl['end_f'])} [{fl['how']}] {fl['text'][:70]}")
for s in suggestions:
    print(f"  SUGGEST {s['kind']} {fmt(s['start_f'])}-{fmt(s['end_f'])} {s['text'][:60]} | {s['how'][:70]}")
if hallucinated:
    print(f"  dropped {len(hallucinated)} hallucinated words: {' '.join(w['x'] for w in hallucinated)[:120]}")
