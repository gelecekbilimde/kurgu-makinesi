"""Score a set of episode plans against the reviewer's markers (spike evaluation).

Ground truth: out/episode/review-markers.json (ranged markers made on the v1 timeline; a range =
failed bit to remove). Each marker's timeline range is mapped back through the v1 plans' pieces to
per-clip source ranges.
For the new plans in out/<dir> it reports:
  per marker: % of its frames the new plan removes, and % covered by suggestions/review flags
  extra removals: frames kept by v1 but removed now, outside every marker (+-MARGIN) -> must be
                  checked by ear (possible over-cuts), printed with the words under them.
  restored: frames v1 removed but the new plan keeps (a retake slipping back in?).
Usage: python 25_eval_markers.py <newdir> [--quiet]
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out"); EP = os.path.join(OUT, "episode")
NEW = os.path.join(OUT, sys.argv[1]); QUIET = "--quiet" in sys.argv
CLIPS = ["087", "088", "089", "090", "091", "094"]; MARGIN = 5
ing = json.load(open(os.path.join(OUT, "ingest.json"), encoding="utf-8"))
v1 = {c: json.load(open(os.path.join(EP, c + "-plan.json"), encoding="utf-8")) for c in CLIPS}
v2 = {c: json.load(open(os.path.join(NEW, c + "-plan.json"), encoding="utf-8")) for c in CLIPS}
M = json.load(open(os.path.join(EP, "review-markers.json"), encoding="utf-8"))


def tc2f(tc):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc)); return (h * 3600 + m * 60 + s) * 25 + f


def words(c):
    p = v1[c]; full = p["clip"]
    path = os.path.join(OUT, "372-track2-resolve-tr.json") if c == "087" else \
        os.path.join(EP, ing[full]["rec"] + "-Track2-tr.json")
    t = json.load(open(path, encoding="utf-8"))
    return [(tc2f(w["start"]) + p["offset_f"], tc2f(w["end"]) + p["offset_f"], w["text"].strip())
            for s in t["segments"] for w in s.get("words", []) if w["text"].strip() != "(...)"]


def mask(plan):
    m = bytearray(plan["clip_end_f"])
    for a, b in plan["keep_frames"]:
        m[a:b] = b"\x01" * (b - a)
    return m


pieces, rec = [], 0
for c in CLIPS:
    for a, b in v1[c]["keep_frames"]:
        pieces.append((rec, a, b, c)); rec += b - a


def tl_to_src(t0, t1):
    out = []
    for r0, a, b, c in pieces:
        lo, hi = max(t0, r0), min(t1, r0 + b - a)
        if lo < hi:
            out.append((c, a + lo - r0, a + hi - r0))
    return out


k1 = {c: mask(v1[c]) for c in CLIPS}; k2 = {c: mask(v2[c]) for c in CLIPS}
sug = {c: bytearray(v2[c]["clip_end_f"]) for c in CLIPS}
for c in CLIPS:
    for s in v2[c].get("suggestions", []) + v2[c].get("review_flags", []):
        a, b = max(0, s["start_f"]), min(v2[c]["clip_end_f"], max(s["end_f"], s["start_f"] + 1))
        sug[c][a:b] = b"\x01" * (b - a)
marked = {c: bytearray(v2[c]["clip_end_f"]) for c in CLIPS}
tot_f = tot_rm = tot_sg = 0
print(f"{'marker':11} clip  len   removed  suggested")
for m in M:
    parts = tl_to_src(*m["tl"]) if m["tl"][1] - m["tl"][0] > 1 else []
    if not parts:                                            # point marker: note only
        c = m["clip"][5:8]; s = m["src"][0]
        print(f"{m['name']:11} {c}  point  kept={bool(k2[c][s])}  ({m['note'].strip()[:60]})")
        continue
    n = rm = sg = 0
    for c, a, b in parts:
        for x in range(a, b):
            n += 1; rm += not k2[c][x]; sg += bool(k2[c][x] and sug[c][x])
        lo, hi = max(0, a - MARGIN), min(len(marked[c]), b + MARGIN)
        marked[c][lo:hi] = b"\x01" * (hi - lo)
    tot_f += n; tot_rm += rm; tot_sg += sg
    print(f"{m['name']:11} {parts[0][0]}  {n:4}f  {100 * rm / n:5.0f}%  {100 * sg / n:5.0f}%")
print(f"ALL ranged: {tot_f} f, removed {100 * tot_rm / tot_f:.0f}%, suggested {100 * tot_sg / tot_f:.0f}%")

print("\nextra removals (kept in v1, removed now, outside markers):")
total = 0
for c in CLIPS:
    W = words(c)
    x, spans = 0, []
    n = len(k1[c])
    while x < n:
        if k1[c][x] and not k2[c][x] and not marked[c][x]:
            y = x
            while y < n and k1[c][y] and not k2[c][y] and not marked[c][y]:
                y += 1
            spans.append((x, y)); x = y
        else:
            x += 1
    spans = [s for s in spans if s[1] - s[0] >= 6]          # ignore edge jitter < 6 frames
    sub = sum(b - a for a, b in spans); total += sub
    print(f"  {c}: {len(spans)} spans, {sub} f")
    if QUIET:
        continue
    for a, b in spans:
        txt = " ".join(w[2] for w in W if a <= (w[0] + w[1]) // 2 < b)
        why = [r for r in v2[c]["removed"] if r["end_f"] > a and r["start_f"] < b]
        print(f"    {a}-{b} ({(b - a) / 25:.1f}s) «{txt[:90]}»  <- {', '.join(sorted({r['kind'] + ':' + r['how'][:40] for r in why}))[:160]}")
print(f"  total {total} f = {total / 25:.1f}s")

print("\nrestored (removed in v1, kept now; retakes slipping back in?):")
total = 0
for c in CLIPS:
    W = words(c)
    x, spans, n = 0, [], len(k1[c])
    while x < n:
        if not k1[c][x] and k2[c][x]:
            y = x
            while y < n and not k1[c][y] and k2[c][y]:
                y += 1
            spans.append((x, y)); x = y
        else:
            x += 1
    spans = [s for s in spans if s[1] - s[0] >= 6]
    sub = sum(b - a for a, b in spans); total += sub
    print(f"  {c}: {len(spans)} spans, {sub} f")
    if QUIET:
        continue
    for a, b in spans:
        txt = " ".join(w[2] for w in W if a <= (w[0] + w[1]) // 2 < b)
        print(f"    {a}-{b} ({(b - a) / 25:.1f}s) «{txt[:110]}»")
print(f"  total {total} f = {total / 25:.1f}s")
