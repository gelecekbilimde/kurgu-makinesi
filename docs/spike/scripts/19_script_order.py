"""Where in the script does each clip's kept speech land? (spike)

Maps every kept sentence of each plan to a script position with a 3-gram index over the
read-aloud script text (corrections table, headings and [EKRAN] lines excluded). Reports per clip
the script range it covers, plus script passages covered by more than one clip (= a section
re-recorded in a later clip: a cross-clip retake) and script sentences nobody said.
Usage: python 19_script_order.py script.txt plan1.json [plan2.json ...]
"""
import json, re, sys
from collections import defaultdict


def norm(x):
    return re.sub(r"[^\wçğıöşüâî]", "", x.lower().replace("i̇", "i"))


lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("[Heading2] 1."))
body, sections = [], []
for l in lines[start:]:
    if l.startswith("[Heading"):
        sections.append((len(body), re.sub(r"^\[\w+\]\s*", "", l)))
        continue
    if "[EKRAN" in l or not l.strip():
        continue
    l = re.sub(r"^\[\w+\]\s*", "", l)
    l = re.sub(r"\([^)]*\)", "", l)          # pronunciation hints "(kap)"
    body += [norm(w) for w in l.split() if norm(w)]
idx = defaultdict(list)
for i in range(len(body) - 2):
    idx[tuple(body[i:i + 3])].append(i)


def section_of(pos):
    name = "?"
    for p, n in sections:
        if p <= pos:
            name = n
    return name


cover = defaultdict(set)
for path in sys.argv[2:]:
    plan = json.load(open(path, encoding="utf-8"))
    words = [norm(w) for w in plan["kept_text"].split() if norm(w)]
    hits = []
    for i in range(len(words) - 2):
        for pos in idx.get(tuple(words[i:i + 3]), []):
            hits.append(pos)
    if not hits:
        print(f"{plan['clip']}: no script match (off-script or unusable audio)")
        continue
    hits.sort()
    lo, hi = hits[len(hits) // 20], hits[-1 - len(hits) // 20]   # trim 5% outliers
    for h in hits:
        if lo <= h <= hi:
            cover[h // 10].add(plan["clip"])
    matched = len(hits)
    print(f"{plan['clip']}: {len(words)} kept words, {matched} 3-gram hits, script words {lo}-{hi} of {len(body)}"
          f"  [{section_of(lo)} … {section_of(hi)}]")

dup = sorted(b for b, c in cover.items() if len(c) > 1)
if dup:
    print("\nscript passages covered by more than one clip (possible cross-clip retakes):")
    runs, cur = [], [dup[0], dup[0]]
    for b in dup[1:]:
        if b <= cur[1] + 1:
            cur[1] = b
        else:
            runs.append(cur); cur = [b, b]
    runs.append(cur)
    for a, b in runs:
        clips = sorted(set().union(*(cover[x] for x in range(a, b + 1))))
        print(f"  words {a * 10}-{b * 10 + 9} [{section_of(a * 10)}]: {', '.join(clips)}  «{' '.join(body[a * 10:a * 10 + 12])}…»")
gaps = [b for b in range(len(body) // 10) if b not in cover]
print(f"\nscript blocks (10 words) not covered by any clip: {len(gaps)} of {len(body) // 10}")
runs = []
for b in gaps:
    if runs and b == runs[-1][1] + 1:
        runs[-1][1] = b
    else:
        runs.append([b, b])
for a, b in runs:
    if b - a >= 1:
        print(f"  words {a * 10}-{b * 10 + 9} [{section_of(a * 10)}] «{' '.join(body[a * 10:a * 10 + 12])}…»")
