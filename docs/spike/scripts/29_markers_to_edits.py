"""Editor's ranged markers -> per-clip edit files for the planner (spike).

Reads the ranged markers of one colour (default Yellow = "remove this range") from a timeline that
has a map in <plandir>/timelines/<timeline>.json (written by 28_chapters.py), maps each range through
the timeline's flat pieces back to source frames, and merges them into
<plandir>/edits/<clip>-edits.json  {"remove": [[a, b], ...]}  (half-open source frames).
A range spanning several pieces / clips becomes one source range per piece. Point markers (duration 1)
and ranges on a NESTED (frozen) chapter are reported, not applied.
Then: 24_plan_episode.py (re-plan with --edits) -> 26_sections.py -> 28_chapters.py chapters / master.
Usage: ./rv.sh 29_markers_to_edits.py <timeline name> <plandir> [colour] [--dry]
"""
import DaVinciResolveScript as d, json, os, sys
args = [a for a in sys.argv[1:] if a != "--dry"]; DRY = "--dry" in sys.argv
NAME, PLANDIR = args[0], args[1]; COLOR = args[2] if len(args) > 2 else "Yellow"
m = json.load(open(os.path.join(PLANDIR, "timelines", NAME.replace("/", "_") + ".json"), encoding="utf-8"))
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject()
tl = [p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1) if p.GetTimelineByIndex(i).GetName() == NAME][0]
flat, nested = m["flat"], m["nested"]
new, notes = {}, []
for fr, mk in sorted(tl.GetMarkers().items()):
    fr, dur = int(fr), int(mk.get("duration", 1))
    if mk["color"] != COLOR:
        continue
    if dur <= 1:
        notes.append(f"point marker at {fr} ignored (a range is needed): {mk['note'].strip()[:70]}"); continue
    t0, t1, hit = fr, fr + dur, 0
    for rec, clip, a, b in flat:
        lo, hi = max(t0, rec), min(t1, rec + b - a)
        if lo < hi:
            new.setdefault(clip, []).append([a + lo - rec, a + hi - rec]); hit += hi - lo
    for rec, name, n in nested:
        if max(t0, rec) < min(t1, rec + n):
            notes.append(f"range at {fr} lies on frozen chapter {name!r}: edit it there by hand")
    print(f"marker {fr}+{dur}: {hit} f mapped -> {mk['note'].strip()[:70]}")
os.makedirs(os.path.join(PLANDIR, "edits"), exist_ok=True)
for clip, rs in sorted(new.items()):
    path = os.path.join(PLANDIR, "edits", clip.split(".")[0] + "-edits.json")
    old = json.load(open(path, encoding="utf-8"))["remove"] if os.path.exists(path) else []
    merged = sorted({tuple(x) for x in old + rs})
    print(f"{clip}: {len(rs)} new range(s), {len(merged)} total -> {path}{' (dry run)' if DRY else ''}")
    if not DRY:
        json.dump(dict(remove=[list(x) for x in merged]), open(path, "w", encoding="utf-8"), indent=1)
for n in notes:
    print("NOTE", n)
