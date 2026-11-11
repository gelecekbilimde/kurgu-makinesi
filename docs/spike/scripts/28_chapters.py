"""Chapter timelines + A-roll master for one episode (spike).

The episode manifest <plandir>/episode.json lists the clips in order (bin + plan file), the timeline
name prefix and which chapters are FROZEN (signed off):
  {"prefix": "COP31", "clips": [{"bin": "spike-372", "plan": "087-plan.json"}, ...], "frozen": []}
Chapters come from <plandir>/sections.json (26_sections.py).

Commands (run through ./rv.sh):
  chapters [N ...]  rebuild the chapter timelines "<prefix> chN <title>" from the plans (all chapters,
                    or only N ...), in bin "<prefix> chapters". FROZEN chapters are never rebuilt: from
                    the moment a chapter is signed off, its timeline is the editor's, not the script's.
  master            rebuild "<prefix> A-roll": in chapter order, a frozen chapter goes in as its NESTED
                    chapter timeline (hand edits survive), any other chapter as flat pieces from the plans.
  freeze N ... / unfreeze N ...   update the manifest.
Every timeline built here gets a map <plandir>/timelines/<name>.json ([timeline frame, clip, a, b] per
flat piece; nested chapters listed separately) so 29_markers_to_edits.py can read its markers back.
Markers and colours as in 27_build_episode_v2.py.
"""
import json, os, re, sys
CMD, PLANDIR, ARGS = sys.argv[1], sys.argv[2], sys.argv[3:]
MAN = os.path.join(PLANDIR, "episode.json")
man = json.load(open(MAN, encoding="utf-8"))
if CMD in ("freeze", "unfreeze"):
    fr = set(man.get("frozen", []))
    fr = fr | {int(x) for x in ARGS} if CMD == "freeze" else fr - {int(x) for x in ARGS}
    man["frozen"] = sorted(fr)
    json.dump(man, open(MAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("frozen chapters:", man["frozen"]); sys.exit()

import DaVinciResolveScript as d
CHAPTER_COLORS = ["Orange", "Lime", "Teal", "Violet", "Pink", "Navy", "Tan", "Olive"]
COL = {"retake-marker": "Red", "retake-repeat": "Rose"}
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
root = mp.GetRootFolder()
bins = {s.GetName(): s for s in root.GetSubFolderList()}
fps = float(p.GetSetting("timelineFrameRate"))
sec = json.load(open(os.path.join(PLANDIR, "sections.json"), encoding="utf-8"))
label = {(c, a, b): (ch, h) for c, a, b, ch, h in sec["pieces"]}
PRE = man["prefix"]
CH_BIN = f"{PRE} chapters"
if CH_BIN not in bins:
    bins[CH_BIN] = mp.AddSubFolder(root, CH_BIN)
os.makedirs(os.path.join(PLANDIR, "timelines"), exist_ok=True)

clips = []                                    # (plan, media pool item)
for c in man["clips"]:
    plan = json.load(open(os.path.join(PLANDIR, c["plan"]), encoding="utf-8"))
    assert plan.get("units") == "frames" and plan["fps"] == fps, c["plan"]
    clips.append((plan, {x.GetName(): x for x in bins[c["bin"]].GetClipList()}[plan["clip"]]))


def chapter_name(ch):
    """'COP31 ch1 Açılış': Resolve refuses some characters in timeline names (CreateEmptyTimeline
    returned None for '§' / ':' / '?'), so: text before the first ':', letters, digits, spaces, ,'-"""
    title = re.sub(r"^\d+\.\s*", "", sec["chapters"][ch]).split(":")[0]
    title = re.sub(r"[^\w\s,'-]", "", title).strip()
    return f"{PRE} ch{ch + 1} {title}"[:80]


def entries(chapters):
    """flat pieces of the given chapters, in episode order: (plan, mpi, a, b, ch, h)"""
    out = []
    for plan, mpi in clips:
        for a, b in plan["keep_frames"]:
            ch, h = label[(plan["clip"], a, b)]
            if ch in chapters:
                out.append((plan, mpi, a, b, ch, h))
    return out


def piece_markers(ents, rec0):
    """markers for a run of flat pieces starting at timeline frame rec0"""
    mk, rec, prev = [], rec0, None
    keys = {(e[0]["clip"], e[2]) for e in ents}
    cut_at = {}
    for plan, mpi, a, b, ch, h in ents:
        if prev is None or plan["clip"] != prev[0]:
            mk.append((rec, "Blue", plan["clip"], f"clip {plan['clip']} (source frame {a})", 1))
        if prev is None or ch != prev[1]:
            mk.append((rec, "Green", sec["chapters"][ch], "chapter start", 1))
        if prev is None or h != prev[2]:
            hd = sec["headings"][h]
            if hd["level"] == 3:
                mk.append((rec, "Sky", hd["title"], "subsection start", 1))
        prev = (plan["clip"], ch, h)
        cut_at[(plan["clip"], a)] = (rec, b); rec += b - a
    for plan, mpi in clips:
        kf = plan["keep_frames"]
        mine = [(a, b) for a, b in kf if (plan["clip"], a) in keys]
        if not mine:
            continue

        def tl_frame(src):
            for a, b in mine:
                if a <= src < b:
                    return cut_at[(plan["clip"], a)][0] + src - a
            return None
        notes = {}
        for rm in plan["removed"]:
            nxt = min((a for a, b in kf if a >= rm["end_f"]), default=None)   # next piece in the WHOLE plan
            if nxt is not None and (plan["clip"], nxt) in keys:
                notes.setdefault(cut_at[(plan["clip"], nxt)][0], []).append(rm)
        for fr, rms in sorted(notes.items()):
            color = "Cyan" if any(x.get("source") == "second" for x in rms) else COL.get(rms[-1]["kind"], "Purple")
            mk.append((fr, color, f"{len(rms)} cut(s)",
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
                mk.append((t0, color, name, f'{s["kind"]}: {s["how"]} | «{s["text"]}» '
                           f'-> recolour Yellow to remove, delete to keep', max(1, t1 - t0)))
    return mk


def fresh(name):
    for i in range(1, p.GetTimelineCount() + 1):
        tl = p.GetTimelineByIndex(i)
        if tl and tl.GetName() == name:
            mp.DeleteTimelines([tl]); break
    mp.SetCurrentFolder(bins[CH_BIN])
    tl = mp.CreateEmptyTimeline(name)
    # never carry on without our own timeline: AppendToTimeline would append to whatever timeline is
    # current (this happened once and appended chapter 1 to "COP31 episode rough v2")
    assert tl, f"Resolve refused to create timeline {name!r}"
    p.SetCurrentTimeline(tl)
    return tl


def finish(tl, mk, colours, scratch_items):
    """colours: chapter per video item (in order); scratch_items: indexes of A1 items to mute"""
    ok = 0
    for i, it in enumerate(tl.GetItemListInTrack("video", 1) or []):
        ok += bool(it.SetClipColor(CHAPTER_COLORS[colours[i] % len(CHAPTER_COLORS)]))
    for k in range(1, tl.GetTrackCount("audio") + 1):
        for i, it in enumerate(tl.GetItemListInTrack("audio", k) or []):
            if i < len(colours):
                it.SetClipColor(CHAPTER_COLORS[colours[i] % len(CHAPTER_COLORS)])
    used, n = set(), 0
    for fr, c, nm, note, dur in sorted(mk, key=lambda m: m[0]):
        while fr in used:
            fr += 1
        used.add(fr)
        n += bool(tl.AddMarker(fr, c, nm, note, dur))
    return ok, n


def write_map(name, flat, nested):
    json.dump(dict(timeline=name, fps=fps, flat=flat, nested=nested),
              open(os.path.join(PLANDIR, "timelines", name.replace("/", "_") + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


frozen = set(c - 1 for c in man.get("frozen", []))
if CMD == "chapters":
    todo = [int(x) - 1 for x in ARGS] or list(range(len(sec["chapters"])))
    for ch in todo:
        name = chapter_name(ch)
        if ch in frozen:
            print(f"§{ch + 1} frozen, not rebuilt: {name}"); continue
        ents = entries({ch})
        tl = fresh(name)
        items = mp.AppendToTimeline([{"mediaPoolItem": e[1], "startFrame": e[2], "endFrame": e[3]} for e in ents])
        got = [it.GetDuration() for it in tl.GetItemListInTrack("video", 1)]
        want = [e[3] - e[2] for e in ents]
        ok, n = finish(tl, piece_markers(ents, 0), [e[4] for e in ents], [])
        for k in range(1, tl.GetTrackCount("audio") + 1):
            if tl.GetTrackSubType("audio", k) == "stereo":
                tl.SetTrackEnable("audio", k, False)
        rec, flat = 0, []
        for e in ents:
            flat.append([rec, e[0]["clip"], e[2], e[3]]); rec += e[3] - e[2]
        write_map(name, flat, [])
        print(f"§{ch + 1} {name}: {len(items)}/{len(ents)} pieces, durations match: {got == want}, "
              f"{sum(got)} f = {sum(got) // fps // 60:.0f}:{sum(got) // fps % 60:02.0f}, markers {n}")

elif CMD == "master":
    name = f"{PRE} A-roll"
    tl = fresh(name)
    tls = {c.GetName(): c for c in bins[CH_BIN].GetClipList() if c.GetClipProperty("Type") == "Timeline"}
    rec, flat, nested, mk, colours = 0, [], [], [], []
    for ch in range(len(sec["chapters"])):
        if ch in frozen:
            mpi = tls[chapter_name(ch)]
            it = mp.AppendToTimeline([{"mediaPoolItem": mpi}])
            n = int(mpi.GetClipProperty("Frames"))
            mk.append((rec, "Green", sec["chapters"][ch], "chapter start (FROZEN: nested chapter timeline)", 1))
            nested.append([rec, chapter_name(ch), n]); colours.append(ch); rec += n
            print(f"§{ch + 1} nested (frozen): {n} f, appended {bool(it)}")
        else:
            ents = entries({ch})
            mp.AppendToTimeline([{"mediaPoolItem": e[1], "startFrame": e[2], "endFrame": e[3]} for e in ents])
            mk += piece_markers(ents, rec)
            for e in ents:
                flat.append([rec, e[0]["clip"], e[2], e[3]]); colours.append(ch); rec += e[3] - e[2]
            print(f"§{ch + 1} flat from plans: {len(ents)} pieces")
    ok, n = finish(tl, mk, colours, [])
    # camera scratch audio: mute the scratch ITEMS of flat pieces (not the track: a nested chapter's
    # audio may share the track)
    muted = 0
    for k in range(1, tl.GetTrackCount("audio") + 1):
        if tl.GetTrackSubType("audio", k) != "stereo":
            continue
        for it in tl.GetItemListInTrack("audio", k) or []:
            mpi = it.GetMediaPoolItem()
            if mpi and mpi.GetClipProperty("Type") != "Timeline":
                muted += bool(it.SetClipEnabled(False))
    write_map(name, flat, nested)
    print(f"{name}: {rec} f = {rec // fps // 60:.0f}:{rec // fps % 60:02.0f}, timeline end check "
          f"{tl.GetEndFrame() - tl.GetStartFrame() + 1}, markers {n}, scratch items muted {muted}")
    print("audio tracks:", [(k, tl.GetTrackSubType("audio", k), len(tl.GetItemListInTrack("audio", k) or []))
                            for k in range(1, tl.GetTrackCount("audio") + 1)])
