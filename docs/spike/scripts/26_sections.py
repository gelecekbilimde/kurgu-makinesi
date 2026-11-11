"""Assign every kept piece of an episode to a script section (spike).

The script's headings split it into chapters: [Heading2] "1. Açılış..." … "6. COP31 dünyayı
değiştirebilir mi?" (stop before "Kaynakça"), each with [Heading3] subsections. Every read-aloud
script word belongs to the latest heading above it.
1. Each kept piece's words (primary transcript, word midpoint inside the piece) are matched to the
   script with a 3-gram index (as in 19_script_order.py); every hit votes for the heading it lands in.
2. The host follows the script order (checked in log §30), so labels must never go backwards: a
   dynamic programme picks the non-decreasing heading sequence that disagrees with the fewest votes.
   Pieces without votes (improvised speech) simply inherit their neighbours' heading.
Output: <plandir>/sections.json = {"chapters": [...], "headings": [...], "pieces": [[clip, a, b, h2, h3], ...]}
Usage: python 26_sections.py script.txt <plandir> plan1.json [plan2.json ...]
"""
import json, os, re, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out")
ing = json.load(open(os.path.join(OUT, "ingest.json"), encoding="utf-8"))


def norm(x):
    return re.sub(r"[^\wçğıöşüâî]", "", x.lower().replace("i̇", "i"))


def tc2f(tc, fps=25):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc)); return (h * 3600 + m * 60 + s) * fps + f


script, plandir, plans = sys.argv[1], sys.argv[2], sys.argv[3:]
lines = open(script, encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("[Heading2] 1."))
body, heads = [], []                     # heads: (level, title, parent chapter index)
chap = -1
for l in lines[start:]:
    m = re.match(r"^\[Heading([23])\]\s*(.*)", l)
    if m:
        if m.group(2).startswith("Kaynakça"):
            break
        if m.group(1) == "2":
            chap += 1
        heads.append((int(m.group(1)), m.group(2).strip(), chap))
        continue
    if "[EKRAN" in l or not l.strip():
        continue
    l = re.sub(r"^\[\w+\]\s*", "", l); l = re.sub(r"\([^)]*\)", "", l)
    body += [(norm(w), len(heads) - 1) for w in l.split() if norm(w)]
idx = defaultdict(list)
for i in range(len(body) - 2):
    idx[tuple(b[0] for b in body[i:i + 3])].append(body[i][1])
chapters = [t for lv, t, _ in heads if lv == 2]

pieces = []                              # (clip, a, b, votes{head: n})
for path in plans:
    p = json.load(open(path, encoding="utf-8"))
    clip = p["clip"]
    tr = os.path.join(OUT, "episode", ing[clip]["rec"] + "-Track2-tr.json") if clip in ing \
        else os.path.join(OUT, "372-track2-resolve-tr.json")
    t = json.load(open(tr, encoding="utf-8"))
    W = [((tc2f(w["start"]) + tc2f(w["end"])) // 2 + p["offset_f"], norm(w["text"])) for s in t["segments"]
         for w in s.get("words", []) if norm(w["text"])]
    for a, b in p["keep_frames"]:
        ws = [n for m, n in W if a <= m < b]
        votes = defaultdict(int)
        for i in range(len(ws) - 2):
            hs = idx.get(tuple(ws[i:i + 3]), [])
            for h in set(hs):                # a 3-gram found in several headings votes for each once
                votes[h] += 1
        pieces.append((clip, a, b, dict(votes), ws[:5]))

# monotone labelling: minimise votes against the chosen heading, headings non-decreasing
H, N = len(heads), len(pieces)
INF = float("inf")
cost = [[sum(v for h, v in pc[3].items() if h != k) for k in range(H)] for pc in pieces]
TRANS = {"gelelim", "peki", "gelin", "şimdi"}
dp = [[INF] * H for _ in range(N)]; back = [[0] * H for _ in range(N)]
for k in range(H):
    dp[0][k] = cost[0][k]
for i in range(1, N):
    best, arg = INF, 0
    for k in range(H):
        if dp[i - 1][k] < best:
            best, arg = dp[i - 1][k], k
        dp[i][k], back[i][k] = best + cost[i][k], arg
k = min(range(H), key=lambda x: dp[N - 1][x]); lab = [0] * N
for i in range(N - 1, -1, -1):
    lab[i] = k; k = back[i][k]
# 3. a boundary between two headings can sit anywhere in the run of vote-less pieces before the
# first piece voting for the new heading (same cost); the DP puts it as late as possible. Move it
# to the first piece in that run that opens with a transition word ("Gelelim Türkiye'ye...",
# "Peki zirvenin...") or has a word of the new heading's title among its first five words
# ("yansımaları neler olabilir?" for "Zirvenin ... yansımaları") - chapters are introduced by the
# host, often off-script.
for i in range(1, N):
    if lab[i] != lab[i - 1]:
        j = i
        while j - 1 > 0 and not pieces[j - 1][3] and lab[j - 1] == lab[i - 1]:
            j -= 1
        title = {norm(x) for x in re.split(r"[\s:,]+", heads[lab[i]][1]) if len(norm(x)) >= 6}
        for t in range(j, i):
            if pieces[t][4] and (pieces[t][4][0] in TRANS or title & set(pieces[t][4])):
                for x in range(t, i):
                    lab[x] = lab[i]
                break

out = dict(chapters=chapters, headings=[dict(level=lv, title=t, chapter=c) for lv, t, c in heads],
           pieces=[[c, a, b, heads[l][2], l] for (c, a, b, _, _), l in zip(pieces, lab)])
json.dump(out, open(os.path.join(plandir, "sections.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
voted = sum(bool(pc[3]) for pc in pieces)
agree = sum(v for pc, l in zip(pieces, lab) for h, v in pc[3].items() if h == l)
allv = sum(v for pc in pieces for v in pc[3].values())
print(f"{N} pieces, {voted} with script votes; {agree}/{allv} votes agree with the monotone labels")
rec = 0
for i, (c, a, b, _, first) in enumerate(pieces):
    if i == 0 or lab[i] != lab[i - 1]:
        lv, t, ch = heads[lab[i]]
        s_ = rec // 25
        print(f"  {s_ // 60:3d}:{s_ % 60:02d}  {'  ' if lv == 3 else ''}{t}   ({c} src {a}: {' '.join(first)}…)")
    rec += b - a
