"""Analyse a Resolve transcription JSON for A-roll cleanup signals (throwaway spike).

Reports:
  - filler tokens (Turkish hesitations) and whether the model emitted any at all
  - silences ('(...)' words / segments) and long gaps between words
  - repeated phrases close together (retake candidates: host restarts a sentence)
Usage: python3 07_analyze.py transcript.json [fps]
"""
import json, re, sys
from collections import Counter

path = sys.argv[1]
FPS = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
t = json.load(open(path, encoding="utf-8"))


def tc2s(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return h * 3600 + m * 60 + s + f / FPS


def fmt(sec):
    return "%d:%05.2f" % (sec // 60, sec % 60)


words = []
for seg in t["segments"]:
    for w in seg.get("words", []):
        if "start" in w and "end" in w:
            words.append((tc2s(w["start"]), tc2s(w["end"]), w["text"].strip()))

speech = [w for w in words if w[2] != "(...)"]
print(f"language={t.get('language')}  segments={len(t['segments'])}  words={len(speech)}")
dur = words[-1][1] if words else 0
print(f"span={fmt(dur)}  speaking time={fmt(sum(e - s for s, e, _ in speech))}")

# --- fillers -----------------------------------------------------------------
FILL = re.compile(r"^[\[\(]?(ı+|i+|e+h*|ee+|a+h*|ı+h|hı+|hm+|mm+|ımm*|şey|yani|işte)[\]\)]?[.,!?…]*$", re.I)
fills = [w for w in speech if FILL.match(w[2])]
print(f"\nfiller-like tokens: {len(fills)}")
print("  by text:", Counter(w[2].lower() for w in fills).most_common(15))
for s, e, x in fills[:25]:
    print(f"  {fmt(s)}  {x}")

# --- gaps --------------------------------------------------------------------
gaps = []
for (s1, e1, x1), (s2, e2, x2) in zip(speech, speech[1:]):
    if s2 - e1 >= 0.7:
        gaps.append((e1, s2, s2 - e1))
print(f"\ngaps >= 0.7s between words: {len(gaps)}, total {sum(g[2] for g in gaps):.1f}s")
for a, b, g in sorted(gaps, key=lambda x: -x[2])[:10]:
    print(f"  {fmt(a)} -> {fmt(b)}  {g:.1f}s")

# --- repeated phrases (retake candidates) -------------------------------------
norm = [re.sub(r"[^\wçğıöşü]", "", w[2].lower()) for w in speech]
N = 4
seen = {}
retakes = []
for i in range(len(norm) - N + 1):
    gram = tuple(norm[i:i + N])
    if "" in gram:
        continue
    if gram in seen and speech[i][0] - speech[seen[gram]][0] < 90:
        retakes.append((seen[gram], i))
    seen[gram] = i
# collapse overlapping hits
merged = []
for a, b in retakes:
    if merged and b - merged[-1][1] <= N:
        continue
    merged.append((a, b))
print(f"\nrepeated {N}-word phrases within 90s (retake candidates): {len(merged)}")
for a, b in merged[:20]:
    first = " ".join(w[2] for w in speech[a:a + 8])
    print(f"  first {fmt(speech[a][0])} | again {fmt(speech[b][0])} | {first}")

print("\n--- first 600 chars of text ---")
print(" ".join(w[2] for w in speech)[:600])
