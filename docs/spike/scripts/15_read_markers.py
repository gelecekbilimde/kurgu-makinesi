# Read timeline markers (e.g. the reviewer's own) and map each to source frame + piece.
# Usage: ./rv.sh 15_read_markers.py <timeline name> <plan.json> [color]
import DaVinciResolveScript as d, json, sys
NAME, PLAN = sys.argv[1:3]; COLOR = sys.argv[3] if len(sys.argv) > 3 else None
plan = json.load(open(PLAN, encoding="utf-8"))
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject()
tl = [p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1) if p.GetTimelineByIndex(i).GetName() == NAME][0]
pieces, rec = [], 0
for a, b in plan["keep_frames"]:
    pieces.append((rec, a, b)); rec += b - a
out = []
for fr, m in sorted(tl.GetMarkers().items()):
    if COLOR and m["color"] != COLOR:
        continue
    fr = int(fr)
    hit = [(r0, a, b) for r0, a, b in pieces if r0 <= fr < r0 + b - a]
    r0, a, b = hit[0] if hit else (None, None, None)
    src = a + fr - r0 if hit else None
    s, f = divmod(fr + 90000, 25)
    out.append(dict(tl_frame=fr, tc="%02d:%02d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60, f), color=m["color"],
                    name=m["name"], note=m["note"], src=src, piece=[a, b],
                    to_piece_end=(b - src) if hit else None))
    print(out[-1])
