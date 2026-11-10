# Build one episode timeline from several frame-native cut plans (in the given order).
# Usage: ./rv.sh 20_build_episode.py <timeline name> <bin>:<plan.json> [<bin>:<plan.json> ...]
# Markers: Blue = clip boundary; Red = "bir daha" retake; Yellow = repeated phrase; Purple = orphan;
#          Cyan = cut found only by the second (camera-clip) transcript;
#          Pink = long retake (> MAX_RETAKE_F) NOT removed, needs a human decision.
import DaVinciResolveScript as d, json, sys
NAME, specs = sys.argv[1], [a.split(":", 1) for a in sys.argv[2:]]
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
bins = {s.GetName(): s for s in mp.GetRootFolder().GetSubFolderList()}
fps = float(p.GetSetting("timelineFrameRate"))
for i in range(1, p.GetTimelineCount() + 1):
    tl = p.GetTimelineByIndex(i)
    if tl and tl.GetName() == NAME:
        mp.DeleteTimelines([tl]); break
tl = mp.CreateEmptyTimeline(NAME); p.SetCurrentTimeline(tl)

COL = {"retake-marker": "Red", "retake-repeat": "Yellow", "orphan": "Purple"}
rec, want, markers = 0, [], []
infos = []
for bin_name, plan_path in specs:
    plan = json.load(open(plan_path, encoding="utf-8"))
    assert plan.get("units") == "frames" and plan["fps"] == fps, plan_path
    clip = {c.GetName(): c for c in bins[bin_name].GetClipList()}[plan["clip"]]
    markers.append((rec, "Blue", plan["clip"], f"clip {plan['clip']}: {plan['clip_end_f']} f source -> "
                    f"{sum(b - a for a, b in plan['keep_frames'])} f"))
    cut_at = {}
    for a, b in plan["keep_frames"]:
        infos.append({"mediaPoolItem": clip, "startFrame": a, "endFrame": b})
        cut_at[a] = rec; want.append(b - a); rec += b - a
    notes = {}
    for rm in plan["removed"]:
        if rm["kind"] == "pause":
            continue
        nxt = min((a for a in cut_at if a >= rm["end_f"]), default=None)
        if nxt is not None:
            notes.setdefault(cut_at[nxt], []).append(rm)
    seen = set()
    for fl in plan.get("review_flags", []):                 # pink: long retake kept for review
        key = (fl["start_f"] // 25, fl["end_f"] // 25)
        if key in seen:
            continue                                         # same passage flagged by both transcripts
        seen.add(key)
        hit = [(a, b) for a, b in plan["keep_frames"] if a <= fl["start_f"] < b] or \
              [(a, b) for a, b in plan["keep_frames"] if a >= fl["start_f"]][:1]
        if hit:
            a, b = hit[0]
            at = cut_at[a] + max(0, fl["start_f"] - a)
            markers.append((at, "Pink", "REVIEW long retake?", f'{fl["how"]}: {fl["text"]}'))
    for fr, rms in sorted(notes.items()):
        color = "Cyan" if any(x.get("source") == "second" for x in rms) else COL[rms[-1]["kind"]]
        markers.append((fr + 1 if fr in (m[0] for m in markers) else fr, color, f"{len(rms)} cut(s)",
                        " | ".join(f'{x["kind"]} ({x["how"]}): {x["text"]}' for x in rms)))

items = mp.AppendToTimeline(infos)
got = [it.GetDuration() for it in tl.GetItemListInTrack("video", 1)]
print("pieces:", len(infos), "appended:", len(items), "| durations match plans:", got == want,
      "| total", sum(got), "f = %.2f s" % (sum(got) / fps))
print("audio tracks:", [(k, tl.GetTrackSubType("audio", k), len(tl.GetItemListInTrack("audio", k) or []))
                        for k in range(1, tl.GetTrackCount("audio") + 1)])
n = sum(bool(tl.AddMarker(fr, c, nm, note, 1)) for fr, c, nm, note in markers)
print("markers added:", n, "of", len(markers))
for k in range(1, tl.GetTrackCount("audio") + 1):      # disable camera scratch (stereo) tracks
    if tl.GetTrackSubType("audio", k) == "stereo":
        print(f"disable A{k} (stereo, camera scratch):", tl.SetTrackEnable("audio", k, False))
