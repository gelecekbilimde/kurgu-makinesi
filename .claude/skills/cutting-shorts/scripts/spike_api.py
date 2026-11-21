#!/usr/bin/env python3
"""Re-runnable live probe of the Resolve API facts cutting-shorts relies on (reference.md, "Resolve API facts").

Run with Resolve open: bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh spike_api.py [camera.mov]
Works only in the throwaway project `shorts-spike` (created if missing, its spike timelines rebuilt each run),
then loads the project that was open before. Needs ffmpeg (test pattern, still measurement); its temp files are removed at the end.
Prints one line per fact: `OK` or `FAIL` with the observed values (`SKIP` for the camera check without a clip).
When `shorts-spike` itself was open, the reload check loads another project of the folder (only loaded, never changed)."""
import os
import shutil
import subprocess
import sys
import tempfile

import DaVinciResolveScript as dvr

SPIKE = "shorts-spike"
FPS = 25
W, H = 1080, 1920           # vertical timeline
SW, SH = 3840, 2160         # 16:9 UHD source (camera)
FAILS = []


def check(label, ok, seen):
    print(("OK   " if ok else "FAIL ") + label + ": " + repr(seen))
    if not ok:
        FAILS.append(label)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def pattern(path):
    """UHD clip, black with a 40x40 red box centred on source pixel (1920,1080) and lime on (1700,700)."""
    ffmpeg("-f", "lavfi", "-i", f"color=c=black:s={SW}x{SH}:r={FPS}:d=4", "-vf",
           "drawbox=x=1900:y=1060:w=40:h=40:c=red:t=fill,drawbox=x=1680:y=680:w=40:h=40:c=lime:t=fill",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", path)


def centres(png):
    """{colour: (cx, cy)} of the red and lime boxes in an exported still (pure-python PPM scan)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", png, "-f", "image2pipe", "-vcodec", "ppm", "-"],
                         capture_output=True, check=True).stdout
    head = raw.split(b"\n", 3)
    w, h = map(int, head[1].split())
    px = head[3]
    acc = {"red": [], "lime": []}
    for y in range(h):
        row = px[y * w * 3:(y + 1) * w * 3]
        for x in range(w):
            r, g, b = row[3 * x], row[3 * x + 1], row[3 * x + 2]
            if r > 150 and g < 90 and b < 90:
                acc["red"].append((x, y))
            elif g > 150 and r < 90 and b < 90:
                acc["lime"].append((x, y))
    out = {"size": (w, h)}
    for k, pts in acc.items():
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            out[k] = ((min(xs) + max(xs) + 1) / 2, (min(ys) + max(ys) + 1) / 2)
    return out


def predicted(sx, sy, zoom, pan, tilt):
    """Formula under test: scaleToFit 16:9 UHD into 1080x1920 (see reference.md)."""
    s = W / SW * zoom
    return 540 + (sx - SW / 2) * s + pan, 960 + (sy - SH / 2) * s - tilt * (SH * W / SW) / H


def main():
    cam = sys.argv[1] if len(sys.argv) > 1 else None
    tmp = tempfile.mkdtemp(prefix="shorts-spike-")
    r = dvr.scriptapp("Resolve")
    pm = r.GetProjectManager()
    before = pm.GetCurrentProject().GetName()
    p = pm.LoadProject(SPIKE) or pm.CreateProject(SPIKE)
    assert p and p.GetName() == SPIKE, "could not open " + SPIKE
    p.SetSetting("timelineFrameRate", str(FPS))
    mp = p.GetMediaPool()
    old = [p.GetTimelineByIndex(i + 1) for i in range(p.GetTimelineCount())]
    old = [t for t in old if t.GetName().startswith("spike ")]
    if old:
        mp.DeleteTimelines(old)

    def vertical(name):
        t = mp.CreateEmptyTimeline(name)
        for k, v in (("useCustomSettings", "1"), ("timelineResolutionWidth", str(W)),
                     ("timelineResolutionHeight", str(H)), ("timelineFrameRate", str(FPS))):
            assert t.SetSetting(k, v), k
        return t

    def subs(t):
        return [(it.GetName(), it.GetStart(), it.GetEnd(), it.GetUniqueId())
                for i in range(1, t.GetTrackCount("subtitle") + 1) for it in (t.GetItemListInTrack("subtitle", i) or [])]

    try:
        # Step 1: vertical timeline
        t = vertical("spike vertical")
        got = {k: t.GetSetting(k) for k in ("useCustomSettings", "timelineResolutionWidth",
                                             "timelineResolutionHeight", "timelineFrameRate")}
        check("1 vertical settings read back", got == {"useCustomSettings": "1", "timelineResolutionWidth": "1080",
                                                       "timelineResolutionHeight": "1920", "timelineFrameRate": 25.0}, got)
        check("1 project resolution untouched",
              (p.GetSetting("timelineResolutionWidth"), p.GetSetting("timelineResolutionHeight")) == ("1920", "1080"),
              (p.GetSetting("timelineResolutionWidth"), p.GetSetting("timelineResolutionHeight")))

        # Step 2: transform units (pattern clip, still export on the Color page)
        pat_path = os.path.join(tmp, "pattern.mp4")
        pattern(pat_path)
        pat = mp.ImportMedia([pat_path])[0]
        p.SetCurrentTimeline(t)
        it = mp.AppendToTimeline([{"mediaPoolItem": pat, "startFrame": 0, "endFrame": 50, "trackIndex": 1,
                                   "recordFrame": t.GetStartFrame(), "mediaType": 1}])[0]
        check("2 input scaling is scaleToFit", t.GetSetting("timelineInputResMismatchBehavior") == "scaleToFit",
              t.GetSetting("timelineInputResMismatchBehavior"))
        r.OpenPage("color")
        t.SetCurrentTimecode("01:00:00:10")
        zfill = (H / SH) / (W / SW)
        for zoom, pan, tilt in ((1.0, 0, 0), (zfill, 0, 0), (zfill, 200, 0), (zfill, -150, -100), (2.0, 0, 300)):
            for k, v in (("ZoomX", zoom), ("ZoomY", zoom), ("Pan", pan), ("Tilt", tilt)):
                assert it.SetProperty(k, v), k
            png = os.path.join(tmp, f"still-{zoom:.3f}-{pan}-{tilt}.png")
            assert p.ExportCurrentFrameAsStill(png), "ExportCurrentFrameAsStill"
            c = centres(png)
            want = {"red": predicted(1920, 1080, zoom, pan, tilt), "lime": predicted(1700, 700, zoom, pan, tilt)}
            ok = c["size"] == (W, H) and all(abs(c[k][0] - want[k][0]) <= 1 and abs(c[k][1] - want[k][1]) <= 1
                                              for k in want)
            check(f"2 zoom {zoom:.4f} pan {pan} tilt {tilt}: centres match formula", ok,
                  {k: (c.get(k), tuple(round(v, 1) for v in want[k])) for k in want})
        mp.DeleteClips([pat])
        r.OpenPage("edit")

        # Step 3: subtitles from an SRT
        srt = os.path.join(tmp, "cues.srt")
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,400\nBirinci satır çığ\nikinci satır Şüö\n\n"
                    "2\n00:00:03,040 --> 00:00:05,000\nİkinci altyazı\n")
        sm = mp.ImportMedia([srt])[0]
        check("3 SRT imports as a Subtitle clip", sm.GetClipProperty("Type") == "Subtitle", sm.GetClipProperty("Type"))
        ts = vertical("spike subtitles")
        p.SetCurrentTimeline(ts)
        mp.AppendToTimeline([sm])
        s0 = ts.GetStartFrame()
        got = [(n, a - s0, b - s0) for n, a, b, _ in subs(ts)]
        check("3 cues land at s0 + SRT frames, line break = U+2028", got == [
            ("Birinci satır çığ ikinci satır Şüö", 25, 60), ("İkinci altyazı", 76, 125)], got)
        check("3 Timeline.ImportIntoTimeline(srt) refuses", ts.ImportIntoTimeline(srt, {}) is False, "False")
        tv = vertical("spike subtitles after video")
        p.SetCurrentTimeline(tv)
        vid = mp.ImportMedia([pat_path])[0]
        mp.AppendToTimeline([{"mediaPoolItem": vid, "startFrame": 0, "endFrame": 100, "trackIndex": 1,
                              "recordFrame": tv.GetStartFrame() + 200, "mediaType": 1}])
        end = tv.GetEndFrame()
        mp.AppendToTimeline([{"mediaPoolItem": sm, "recordFrame": tv.GetStartFrame()}])
        got = [a - end for _, a, _, _ in subs(tv)]
        check("3 on a non-empty timeline cues go after GetEndFrame() (recordFrame ignored)", got == [25, 76], got)
        it0 = ts.GetItemListInTrack("subtitle", 1)[0]
        uid = it0.GetUniqueId()
        check("3 TimelineItem.SetName on a cue is refused", it0.SetName("x") is False and it0.GetUniqueId() == uid,
              it0.GetName())
        check("3 cue has no media pool item", it0.GetMediaPoolItem() is None, None)
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nyeni metin\n")
        again = mp.ImportMedia([srt])
        check("3 re-importing a changed SRT at the same path returns the stale clip",
              len(again) == 1 and again[0].GetMediaId() == sm.GetMediaId(), again[0].GetName() if again else None)
        mp.DeleteClips([sm, vid])
        check("3 cues stay on the timeline after their pool clip is deleted", len(subs(ts)) == 2, len(subs(ts)))
        snap = subs(ts)
        assert pm.SaveProject(), "SaveProject"
        other = before if before != SPIKE else next(n for n in pm.GetProjectListInCurrentFolder() if n != SPIKE)
        away = pm.LoadProject(other) is not None and pm.GetCurrentProject().GetName() == other
        p = pm.LoadProject(SPIKE)
        mp = p.GetMediaPool()
        ts = [p.GetTimelineByIndex(i + 1) for i in range(p.GetTimelineCount())
              if p.GetTimelineByIndex(i + 1).GetName() == "spike subtitles"][0]
        check(f"3 cue uids/text/frames survive save, load '{other}' (read only), load {SPIKE}",
              away and p.GetName() == SPIKE and subs(ts) == snap, [(n, a, b, u[:8]) for n, a, b, u in subs(ts)])

        # Step 4: markers on a timeline with nested timelines
        tp = vertical("spike parent")
        p.SetCurrentTimeline(tp)
        child = [p.GetTimelineByIndex(i + 1) for i in range(p.GetTimelineCount())
                 if p.GetTimelineByIndex(i + 1).GetName() == "spike vertical"][0]
        child.AddMarker(5, "Blue", "child", "", 1, "child:1")
        mp.AppendToTimeline([{"mediaPoolItem": child.GetMediaPoolItem(), "trackIndex": 1,
                              "recordFrame": tp.GetStartFrame(), "mediaType": 1}])
        check("4 nested child's markers are not the parent's", tp.GetMarkers() == {}, tp.GetMarkers())
        check("4 AddMarker with duration + customData", tp.AddMarker(10, "Fuchsia", "aday", "not", 30, "short:c1"), True)
        check("4 second marker on the same frame refused", tp.AddMarker(10, "Green", "x", "", 1, "short:x") is False,
              False)
        check("4 GetMarkers keys are frames from the timeline start", tp.GetMarkers() == {10: {
            "color": "Fuchsia", "duration": 30, "note": "not", "name": "aday", "customData": "short:c1"}}, tp.GetMarkers())
        check("4 GetMarkerByCustomData returns the marker without its frame",
              tp.GetMarkerByCustomData("short:c1") == {"color": "Fuchsia", "duration": 30, "note": "not",
                                                        "name": "aday", "customData": "short:c1"},
              tp.GetMarkerByCustomData("short:c1"))
        n = tp.GetEndFrame() - tp.GetStartFrame()
        check("4 AddMarker past the timeline end is accepted", tp.AddMarker(n + 20, "Fuchsia", "p", "", 5, "short:p"), n)

        # Step 5: SetName, mediaType 1
        check("5 Timeline.SetName", tp.SetName("spike renamed") and tp.GetName() == "spike renamed", tp.GetName())
        check("5 SetName to a taken name refused", tp.SetName("spike vertical") is False, tp.GetName())
        if cam:
            cam = os.path.abspath(cam)
            cm = next((c for c in mp.GetRootFolder().GetClipList() if c.GetClipProperty("File Path") == cam), None)
            cm = cm or mp.ImportMedia([cam])[0]
            tc = vertical("spike camera")
            p.SetCurrentTimeline(tc)
            mp.AppendToTimeline([{"mediaPoolItem": cm, "startFrame": 0, "endFrame": 50, "trackIndex": 1,
                                  "recordFrame": tc.GetStartFrame(), "mediaType": 1}])
            na = sum(len(tc.GetItemListInTrack("audio", i) or []) for i in range(1, tc.GetTrackCount("audio") + 1))
            check("5 mediaType 1 places video only", len(tc.GetItemListInTrack("video", 1)) == 1 and na == 0, na)
        else:
            print("SKIP 5 mediaType 1 places video only: no camera clip given")
        pm.SaveProject()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        pm.LoadProject(before)
        print(f"back in project '{pm.GetCurrentProject().GetName()}'; {len(FAILS)} FAIL")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
