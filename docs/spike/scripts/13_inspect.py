"""Inspect review notes: map timeline TC -> source frame; print per-frame energy + words (spike).
Usage: python3 13_inspect.py plan.json transcript.json audio.wav TL_TC_FROM TL_TC_TO [TL_START=01:00:00:00]
Prints, for each source frame around the range: timeline TC, source frame, dBFS bar, word.
"""
import json, math, re, sys, wave

plan_p, tr_p, wav_p, a_tc, b_tc = sys.argv[1:6]
TL0 = sys.argv[6] if len(sys.argv) > 6 else "01:00:00:00"
plan = json.load(open(plan_p, encoding="utf-8")); FPS = plan["fps"]; OFF = plan["offset_f"]


def tc2f(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * FPS + f


def f2tc(fr):
    s, f = divmod(fr, FPS); return "%02d:%02d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60, f)


# timeline frame -> source frame
pieces, rec = [], 0
for a, b in plan["keep_frames"]:
    pieces.append((rec, a, b)); rec += b - a


def tl2src(t):
    for r0, a, b in pieces:
        if r0 <= t < r0 + (b - a):
            return a + (t - r0), (r0, a, b)
    return None, None


w = wave.open(wav_p); sr, sw, ch = w.getframerate(), w.getsampwidth(), w.getnchannels(); full = 2 ** (sw * 8 - 1)


def db(src_f):
    """dBFS of camera source frame src_f (WAV frame = src_f - OFF)."""
    a = (src_f - OFF) / FPS
    if a < 0: return -120
    w.setpos(int(a * sr)); raw = w.readframes(int(sr / FPS)); step = sw * ch
    acc = cnt = 0
    for j in range(0, len(raw) - step, step * 4):
        v = int.from_bytes(raw[j:j + sw], "little", signed=True); acc += v * v; cnt += 1
    return 20 * math.log10(math.sqrt(acc / max(cnt, 1)) / full + 1e-12)


tr = json.load(open(tr_p, encoding="utf-8"))
words = [(tc2f(x["start"]) + OFF, tc2f(x["end"]) + OFF, x["text"]) for s in tr["segments"] for x in s.get("words", [])
         if "start" in x and x["text"].strip() != "(...)"]

if a_tc.startswith("src:"):   # inspect by source frame instead of timeline TC
    sa, sb, pa, pb = int(a_tc[4:]), int(b_tc[4:]), None, None
else:
    ta, tb = tc2f(a_tc) - tc2f(TL0), tc2f(b_tc) - tc2f(TL0)
    sa, pa = tl2src(ta); sb, pb = tl2src(tb)
print(f"timeline {a_tc}..{b_tc} -> source frames {sa}..{sb}  pieces {pa} {pb}")
lo, hi = min(sa, sb if sb is not None else sa) - 8, max(sa, sb if sb is not None else sa) + 8
kept = set()
for r0, a, b in pieces:
    kept.update(range(a, b))
for f in range(lo, hi):
    d = db(f)
    wd = [x for s, e, x in words if s <= f < e]
    bar = "#" * max(0, int((d + 70) / 1.5))
    print(f"{f2tc(f)} {f:6d} {'K' if f in kept else '.'} {d:6.1f} {bar:<45} {' '.join(wd)}")
