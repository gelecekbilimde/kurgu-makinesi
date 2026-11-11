# Build an episode timeline from v5 plans + sections.json: clip colour per chapter, chapter/subsection
# markers, cut markers, and RANGED markers for what the editor must decide.
# Usage: ./rv.sh 27_build_episode_v2.py "<timeline name>" <sections.json> <bin>:<plan.json> [...]
#
# Clip colours (one per script chapter, video + audio items): see CHAPTER_COLORS.
# Markers:
#   Blue    clip boundary                       Green  chapter start (Heading2)   Sky  subsection (Heading3)
#   Red     retake removed (cue: "bir daha", "tekrar", "dur", ...)
#   Rose    repeated phrase removed (last take wins)
#   Purple  other removal: orphan fragment, abandoned "...", heading number, cross-clip retake
#   Cyan    cut found only by the second (camera-clip) transcript
#   Fuchsia RANGED: suggested failed bit, NOT removed (e.g. a silent restart the transcript swallowed)
#   Pink    RANGED: long retake (> 30 s) NOT removed
#   Yellow  reserved for the editor: a ranged Yellow marker = "remove this range" (read back by
#           21_read_episode_markers.py); recolour a Fuchsia/Pink one to Yellow to accept it.
import DaVinciResolveScript as d, json, sys
NAME, SECT, specs = sys.argv[1], sys.argv[2], [a.split(":", 1) for a in sys.argv[3:]]
CHAPTER_COLORS = ["Orange", "Lime", "Teal", "Violet", "Pink", "Navy", "Tan", "Olive"]
COL = {"retake-marker": "Red", "retake-repeat": "Rose", "orphan": "Purple", "abandoned": "Purple",
       "heading-number": "Purple", "cross-clip-retake": "Purple", "editor": "Purple"}
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
bins = {s.GetName(): s for s in mp.GetRootFolder().GetSubFolderList()}
fps = float(p.GetSetting("timelineFrameRate"))
sec = json.load(open(SECT, encoding="utf-8"))
label = {(c, a, b): (ch, h) for c, a, b, ch, h in sec["pieces"]}
for i in range(1, p.GetTimelineCount() + 1):
    tl = p.GetTimelineByIndex(i)
    if tl and tl.GetName() == NAME:
        mp.DeleteTimelines([tl]); break
tl = mp.CreateEmptyTimeline(NAME)
assert tl, f"Resolve refused to create timeline {NAME!r}"   # else AppendToTimeline hits the current one
p.SetCurrentTimeline(tl)

rec, want, markers, infos, chap_of = 0, [], [], [], []
prev_lab = None
for bin_name, plan_path in specs:
    plan = json.load(open(plan_path, encoding="utf-8"))
    assert plan.get("units") == "frames" and plan["fps"] == fps, plan_path
    clip = {c.GetName(): c for c in bins[bin_name].GetClipList()}[plan["clip"]]
    markers.append((rec, "Blue", plan["clip"], f"clip {plan['clip']}: {plan['clip_end_f']} f source -> "
                    f"{sum(b - a for a, b in plan['keep_frames'])} f", 1))
    cut_at = {}
    for a, b in plan["keep_frames"]:
        ch, h = label[(plan["clip"], a, b)]
        if prev_lab is None or ch != prev_lab[0]:
            markers.append((rec, "Green", sec["chapters"][ch], "chapter start", 1))
        if prev_lab is None or h != prev_lab[1]:
            hd = sec["headings"][h]
            if hd["level"] == 3:
                markers.append((rec, "Sky", hd["title"], "subsection start", 1))
        prev_lab = (ch, h)
        infos.append({"mediaPoolItem": clip, "startFrame": a, "endFrame": b})
        chap_of.append(ch)
        cut_at[a] = rec; want.append(b - a); rec += b - a

    def tl_frame(src):
        """timeline frame of a source frame that is kept (None if removed)"""
        for a, b in plan["keep_frames"]:
            if a <= src < b:
                return cut_at[a] + src - a
        return None

    notes = {}
    for rm in plan["removed"]:
        if rm["kind"] == "pause":
            continue
        nxt = min((a for a in cut_at if a >= rm["end_f"]), default=None)
        if nxt is not None:
            notes.setdefault(cut_at[nxt], []).append(rm)
    for fr, rms in sorted(notes.items()):
        color = "Cyan" if any(x.get("source") == "second" for x in rms) else COL.get(rms[-1]["kind"], "Purple")
        markers.append((fr, color, f"{len(rms)} cut(s)",
                        " | ".join(f'{x["kind"]} ({x["how"]}): {x["text"]}' for x in rms), 1))
    seen = set()
    for kind, color, items in (("suggestion", "Fuchsia", plan.get("suggestions", [])),
                               ("review", "Pink", plan.get("review_flags", []))):
        for s in items:
            key = (s["start_f"] // 25, s["end_f"] // 25)
            if key in seen:
                continue
            seen.add(key)
            kept = [x for x in range(max(0, s["start_f"]), max(s["end_f"], s["start_f"] + 1)) if tl_frame(x) is not None]
            if not kept:
                continue
            t0, t1 = tl_frame(kept[0]), tl_frame(kept[-1]) + 1
            name = "failed bit? (suggested)" if kind == "suggestion" else "REVIEW long retake?"
            markers.append((t0, color, name, f'{s["kind"]}: {s["how"]} | «{s["text"]}» '
                            f'-> recolour Yellow to remove, delete to keep', max(1, t1 - t0)))

items = mp.AppendToTimeline(infos)
vid = tl.GetItemListInTrack("video", 1)
got = [it.GetDuration() for it in vid]
print("pieces:", len(infos), "appended:", len(items), "| durations match plans:", got == want,
      "| total", sum(got), "f = %.2f s" % (sum(got) / fps))
ok = 0
for k in range(1, tl.GetTrackCount("audio") + 1):        # colour video + audio items by chapter
    for tr in [("audio", k)] + ([("video", 1)] if k == 1 else []):
        for i, it in enumerate(tl.GetItemListInTrack(*tr) or []):
            ok += bool(it.SetClipColor(CHAPTER_COLORS[chap_of[i] % len(CHAPTER_COLORS)]))
print("clip colours set:", ok)
used = set()
n = 0
for fr, c, nm, note, dur in sorted(markers, key=lambda m: m[0]):
    while fr in used:                                     # one marker per frame in Resolve
        fr += 1
    used.add(fr)
    n += bool(tl.AddMarker(fr, c, nm, note, dur))
print("markers added:", n, "of", len(markers), "| by colour:",
      {c: sum(m[1] == c for m in markers) for c in sorted({m[1] for m in markers})})
for k in range(1, tl.GetTrackCount("audio") + 1):        # disable camera scratch (stereo) tracks
    if tl.GetTrackSubType("audio", k) == "stereo":
        print(f"disable A{k} (stereo, camera scratch):", tl.SetTrackEnable("audio", k, False))
