# Read the reviewer's markers from an episode timeline and map each (incl. ranged ones) back to
# clip + source frames, with the kept words inside the range and the kept words right after it.
# Usage: ./rv.sh 21_read_episode_markers.py <timeline name> <color|all> <plan.json> [<plan.json> ...]
# Words come from the plan's primary transcript (recorder WAV, shifted by offset_f).
# Our own markers are skipped by name ("N cut(s)", "REVIEW long retake?", clip names).
import DaVinciResolveScript as d, json, os, re, sys
NAME, COLOR, PLANS = sys.argv[1], sys.argv[2], sys.argv[3:]
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "out")
ingest = json.load(open(os.path.join(OUT, "ingest.json"), encoding="utf-8"))


def tc2f(tc, fps):
    h, m, s, f = (int(x) for x in re.split("[:;]", tc))
    return (h * 3600 + m * 60 + s) * fps + f


def primary(plan):
    if plan["clip"] in ingest:
        return os.path.join(OUT, "episode", ingest[plan["clip"]]["rec"] + "-Track2-tr.json")
    return os.path.join(OUT, "372-track2-resolve-tr.json")                     # clip 087 (spike)


pieces, rec = [], 0                      # (tl_start, src_a, src_b, clip_idx)
plans, words = [], []
for k, path in enumerate(PLANS):
    pl = json.load(open(path, encoding="utf-8")); plans.append(pl)
    fps, off = pl["fps"], pl["offset_f"]
    t = json.load(open(primary(pl), encoding="utf-8"))
    words.append([(tc2f(w["start"], fps) + off, tc2f(w["end"], fps) + off, w["text"].strip())
                  for s in t["segments"] for w in s.get("words", []) if w["text"].strip() != "(...)"])
    for a, b in pl["keep_frames"]:
        pieces.append((rec, a, b, k)); rec += b - a


def tl_words(t0, t1):
    """Kept words whose midpoint lies on timeline frames [t0, t1)."""
    out = []
    for r0, a, b, k in pieces:
        lo, hi = max(t0, r0), min(t1, r0 + b - a)
        if lo >= hi:
            continue
        s0, s1 = a + lo - r0, a + hi - r0
        out += [w[2] for w in words[k] if s0 <= (w[0] + w[1]) / 2 < s1]
    return out


def where(t):
    for r0, a, b, k in pieces:
        if r0 <= t < r0 + b - a:
            return k, a + t - r0
    return None, None


r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject()
tl = [p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1)
      if p.GetTimelineByIndex(i).GetName() == NAME][0]
fps = int(float(p.GetSetting("timelineFrameRate")))
ours = re.compile(r"^(\d+ cut\(s\)|REVIEW long retake\?|P\d+\.MOV|\d+.*\.wav)$", re.I)
res = []
for fr, m in sorted(tl.GetMarkers().items()):
    fr, dur = int(fr), int(m.get("duration", 1))
    if (COLOR != "all" and m["color"] != COLOR) or ours.match(m["name"]):
        continue
    k, src = where(fr); _, src_end = where(fr + dur - 1)
    s, f = divmod(fr + 3600 * fps, fps)
    item = dict(tc="%02d:%02d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60, f), tl=[fr, fr + dur],
                dur_s=round(dur / fps, 2), color=m["color"], name=m["name"], note=m["note"],
                clip=plans[k]["clip"] if k is not None else None, src=[src, None if src_end is None else src_end + 1],
                before=" ".join(tl_words(fr - 3 * fps, fr)), inside=" ".join(tl_words(fr, fr + dur)),
                after=" ".join(tl_words(fr + dur, fr + dur + 5 * fps)))
    res.append(item)
    print(json.dumps(item, ensure_ascii=False))
json.dump(res, open(os.path.join(OUT, "episode", "review-markers.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
