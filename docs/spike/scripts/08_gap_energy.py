"""Measure audio energy inside the gaps between transcribed words (throwaway spike).

If the transcription model drops hesitations ("ııı", "eee"), those sounds still exist in the
audio: a gap with voiced energy = untranscribed sound (filler, breath, noise); a quiet gap = pause.
Also lists every spoken 'bir daha' (host's verbal retake marker).
Usage: python3 08_gap_energy.py transcript.json audio.wav [fps]
"""
import json, math, re, sys, wave

tpath, wpath = sys.argv[1], sys.argv[2]
FPS = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0
t = json.load(open(tpath, encoding="utf-8"))


def tc2s(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return h * 3600 + m * 60 + s + f / FPS


def fmt(sec):
    return "%d:%05.2f" % (sec // 60, sec % 60)


w = wave.open(wpath)
sr, sw, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
full = 2 ** (sw * 8 - 1)


def frames_db(a, b, win=0.05):
    """dBFS per 50 ms window between a and b seconds (first channel)."""
    w.setpos(int(a * sr))
    raw = w.readframes(max(0, int((b - a) * sr)))
    step = sw * ch
    n = int(win * sr)
    out = []
    for i in range(0, len(raw) - step * n + 1, step * n):
        acc = 0
        cnt = 0
        for j in range(i, i + step * n, step * 4):  # subsample x4
            v = int.from_bytes(raw[j:j + sw], "little", signed=True)
            acc += v * v
            cnt += 1
        out.append(20 * math.log10(math.sqrt(acc / max(cnt, 1)) / full + 1e-12))
    return out


words = [(tc2s(x["start"]), tc2s(x["end"]), x["text"].strip())
         for s in t["segments"] for x in s.get("words", [])
         if "start" in x and x["text"].strip() != "(...)"]

# noise floor / speech level reference
allw = frames_db(0, min(w.getnframes() / sr, 344))
srt = sorted(allw)
floor, speech = srt[len(srt) // 10], srt[len(srt) * 9 // 10]
thr = floor + (speech - floor) * 0.45
print(f"noise floor ~{floor:.1f} dBFS, speech ~{speech:.1f} dBFS, 'voiced' threshold {thr:.1f} dBFS")

voiced_gaps = []
quiet = 0
for (s1, e1, x1), (s2, e2, x2) in zip(words, words[1:]):
    g = s2 - e1
    if g < 0.25:
        continue
    db = frames_db(e1 + 0.04, s2 - 0.04)
    v = sum(1 for d in db if d > thr) * 0.05
    if v >= 0.2:
        voiced_gaps.append((e1, s2, g, v, x1, x2))
    else:
        quiet += 1
print(f"\ngaps >=0.25s: {len(voiced_gaps) + quiet}; quiet (pause) {quiet}; with >=0.2s voiced sound {len(voiced_gaps)}")
for e1, s2, g, v, x1, x2 in voiced_gaps:
    print(f"  {fmt(e1)}-{fmt(s2)} gap {g:.2f}s voiced {v:.2f}s   ...{x1} | {x2}...")

print("\n'bir daha' markers:")
for i in range(len(words) - 1):
    if re.sub(r"\W", "", words[i][2].lower()) == "bir" and re.sub(r"\W", "", words[i + 1][2].lower()) == "daha":
        ctx_b = " ".join(x[2] for x in words[max(0, i - 6):i])
        ctx_a = " ".join(x[2] for x in words[i + 2:i + 8])
        print(f"  {fmt(words[i][0])}  ...{ctx_b} [BİR DAHA] {ctx_a}...")
