# Build a rough-cut timeline in Resolve from a cut plan; add review markers at retake cuts.
# Usage: ./rv.sh 12_build_timeline.py <bin> <plan.json> <timeline name>
import DaVinciResolveScript as d, json, sys
BIN, PLAN, NAME = sys.argv[1:4]
plan = json.load(open(PLAN, encoding="utf-8"))
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
f = [s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName() == BIN][0]
clip = {c.GetName(): c for c in f.GetClipList()}[plan["clip"]]
assert float(p.GetSetting("timelineFrameRate")) == plan["fps"], "project fps != plan fps"

for i in range(1, p.GetTimelineCount() + 1):   # replace a previous run with the same name
    tl = p.GetTimelineByIndex(i)
    if tl and tl.GetName() == NAME:
        mp.DeleteTimelines([tl]); break
tl = mp.CreateEmptyTimeline(NAME); p.SetCurrentTimeline(tl)

assert plan.get("units") == "frames", "plan must be frame-native (v3+)"
# keep_frames are half-open [a, b); AppendToTimeline's endFrame is exclusive too (verified: b-1 gave 1 frame short)
infos = [{"mediaPoolItem": clip, "startFrame": a, "endFrame": b} for a, b in plan["keep_frames"]]
items = mp.AppendToTimeline(infos)
print("appended items:", len(items), "(expected video+audio per piece:", len(infos), "pieces)")
print("tracks: video", tl.GetTrackCount("video"), "audio", tl.GetTrackCount("audio"))
for k in range(1, tl.GetTrackCount("audio") + 1):
    its = tl.GetItemListInTrack("audio", k) or []
    print(f"  A{k}: {len(its)} items, type={tl.GetTrackSubType('audio', k)}")

# verify durations against the plan
vids = tl.GetItemListInTrack("video", 1)
want = [b - a for a, b in plan["keep_frames"]]
got = [it.GetDuration() for it in vids]
print("durations match plan:", want == got, "| total frames", sum(got), "=", "%.2fs" % (sum(got) / plan["fps"]))
if want != got:
    print(" first mismatches:", [(w, g) for w, g in zip(want, got) if w != g][:5])

# review markers at each cut point that removed a retake/orphan (merged when several land on one cut)
rec, cut_at = 0, {}
for (a, b) in plan["keep_frames"]:
    cut_at[a] = rec; rec += b - a
notes = {}
for rm in plan["removed"]:
    if rm["kind"] == "pause":
        continue
    nxt = min((a for a in cut_at if a >= rm["end_f"]), default=None)
    if nxt is not None:
        notes.setdefault(cut_at[nxt], []).append(rm)
COL = {"retake-marker": "Red", "retake-repeat": "Yellow", "orphan": "Purple"}
n = 0
for fr, rms in sorted(notes.items()):
    note = " | ".join(f'{x["kind"]} ({x["how"]}): {x["text"]}' for x in rms)
    color = "Cyan" if any(x.get("source") == "second" for x in rms) else COL[rms[-1]["kind"]]
    n += bool(tl.AddMarker(fr, color, f"{len(rms)} cut(s)", note, 1))
print("markers added:", n, "for", sum(len(v) for v in notes.values()), "removed takes")

# camera scratch audio (A1, stereo) off; recorder WAV (A2, mono) stays
print("disable A1 scratch audio:", tl.SetTrackEnable("audio", 1, False))
