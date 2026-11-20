# Placing B-roll: reference

## Resolve API, verified on 21.2

Spike run 2026-11-20 on Resolve Studio 21.2.0.6, scratch project `broll-spike`, 25 fps, timeline start 90000 (01:00:00:00). `mp` = MediaPool, `tl` = Timeline, `s0 = tl.GetStartFrame()`.

**1. Placing a clip on V2: works.**
`mp.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": a, "endFrame": b, "trackIndex": 2, "recordFrame": s0 + f, "mediaType": 1}])`
- `recordFrame` is **absolute**: it includes `s0`. `{200, 250, recordFrame: s0+30}` gave item 90030..90080. `recordFrame: 5` placed the item at frame 5, before the timeline start, without any error.
- `endFrame` is **exclusive**, as on V1: 200..250 gives 50 frames, `GetSourceStartFrame() == 200`, `GetSourceEndFrame() == 250`.
- `mediaType: 1` puts video only; no audio item was created.
- The track must exist first. Use `tl.AddTrack("video")` (returns True, and `GetTrackCount("video")` goes 1 to 2). Appending with `trackIndex: 3` on a 2-track timeline **returned an item object, but nothing was placed** and no track was added. Check `GetTrackCount` before appending.
- **Overlap does not overwrite.** Appending 0..50 at s0+7020 over an existing item at s0+7000..7050 left the old item intact. The new item was clipped to the free part (97050..97070, 20 f). Clear the range first (`DeleteClips`) when replacing.

**2. Stills: `startFrame`/`endFrame` are ignored. Workaround: set mark in/out.**
- With a fresh PNG, 0..37, 10..47, 0..200, 0..1 and 100..137 all gave **125 frames**, which is the 5 s standard still duration. `GetSourceStartFrame`/`GetSourceEndFrame` both read 0, and `GetLeftOffset()` reads 90000.
- Workaround (exact): `png.SetMarkInOut(0, n - 1)`, then append **without** `startFrame`/`endFrame`, then `png.ClearMarkInOut()`. n = 37 gave 37 frames and n = 300 gave 300. After `ClearMarkInOut` the next append was 125 again.
- Trimming after the append also works, but only to shorten: `item.SetRightOffset(item.GetRightOffset() + (125 - n))` took 125 to 37.
- **Never `SetClipProperty("Out", …)` on a still.** It returned True, then the clip's next append was 1 frame, and later mark in/out appends on it were wrong (38 for n = 37, 10 for n = 36). Only a fresh import was clean.
- Neither the project settings `stillDuration` nor `timelineStillDuration` exist (`SetSetting` returns False).

**3. Nesting a timeline on V1 leaves the source alone: works.**
`mp.AppendToTimeline([{"mediaPoolItem": src_tl.GetMediaPoolItem()}])` nests it. `Timeline.GetMediaPoolItem()` exists, so no bin walk is needed. Afterwards the source timeline's V1 items (start, end, uid) and its `GetMarkers()` were unchanged.

**4. `GetUniqueId()` stability: works for everything the API can do. UI moves and trims are unverified.**
- **Save, close and reopen:** 33 items in 5 timelines were snapshotted (uid, track, start, end, left offset, ZoomX, clip colour, name, plus markers). Then `SaveProject`, `CloseProject`, `LoadProject("broll-spike-2")`, `LoadProject("broll-spike")`. The snapshot after was identical: same uids, no diffs.
- **API trims:** after `SetLeftOffset(120)` (start 93000 → 93020, source 100 → 120) and `SetRightOffset(+20)` the uid was unchanged.
- **Other API changes:** `SetProperty("ZoomX", 1.3)`, `SetClipColor` and a take switch also left the uid unchanged.
- **API moves:** not possible. `SetStart`, `SetEnd` and `SetDuration` are not callable (`'NoneType' object is not callable`).
- **Unverified:** an editor moving or trimming an item in the UI. Read-back should still match on uid first, and fall back to matching on media path + source range.
- `hasattr(item, X)` is always True on Resolve proxies, so it can't be used for feature detection.

**5. `GetProperty()` keys: works.** `item.GetProperty()` returns: Pan, Tilt, ZoomX, ZoomY, ZoomGang, RotationAngle, AnchorPointX, AnchorPointY, Pitch, Yaw, FlipX, FlipY, CropLeft, CropRight, CropTop, CropBottom, CropSoftness, CropRetain, DynamicZoomEase, CompositeMode, Opacity, Distortion, RetimeProcess, MotionEstimation, Scaling, ResizeFilter, TransformEnabled, CroppingEnabled, DynamicZoomEnabled, CompositeEnabled, LensCorrectionEnabled, RetimeAndScalingEnabled.
- **Speed:** not a property (`GetProperty("Speed")` is False). It is readable with `item.GetSpeed()` → `{'Percentage': 100.0}`. `SetSpeed(50)` returned False.
- **Clip colour:** not a property. Read it with `item.GetClipColor()` (`''` when unset) and set it with `item.SetClipColor("Teal")`.
- `SetProperty("ZoomX", 1.5)` works.

**6. Deleting items and our markers: works.**
- `tl.DeleteClips([item])` removed only that item; the other V2 items and V1 were untouched.
- `tl.AddMarker(frame, "Yellow", name, note, 1, "broll:row1")` stores `customData`. `GetMarkerByCustomData("broll:row1")` returns it, and `DeleteMarkerByCustomData("broll:row1")` removes only that marker: an editor marker without customData stayed. A marker with customData survived save and reload.

**7. Take Selector: works, with strict rules.** Calls: `item.AddTake(mpi, start, end)`, `GetTakesCount()`, `GetTakeByIndex(i)` → `{mediaPoolItem, startFrame, endFrame}`, `SelectTakeByIndex(i)`, `GetSelectedTakeIndex()`, `FinalizeTake()`.
- **Persistence:** takes survive save, close, project switch and reopen (3 takes, ranges intact). The uid is unchanged after take switches. `item.GetMediaPoolItem()`, `GetName()` and the source frames follow the selected take.
- **The `AddTake` end is inclusive.** `AddTake(vid, 100, 120)` made the item 21 frames long. The original take reads back as `0, 49` for a 0..50 append.
- **The item length follows the shortest take selected and never grows back.** Selecting a 21 f take shrank a 50 f item to 21. Selecting a longer take later kept 21. Longer takes (300..350, 400..480 on a 50 f item) kept 50.
- **A still as a take on a video item is destructive.** It is stored as `0, 0` even with mark in/out set. Selecting it collapsed the item to **1 frame**, and switching back stayed at 1 frame. A still as the *base* item (placed with mark in/out) with video takes kept its length.
- **`GetTakesCount()` returns 0 when the timeline is not current.** Reads gave 0 and then 3 after `SetCurrentTimeline`. Make the timeline current before reading takes.
- **`GetSelectedTakeIndex()` is 0 after a reload.** The selected content persists (left offset 100 = take 2), but the index does not. Identify the chosen take from `item.GetMediaPoolItem()` + `GetSourceStartFrame()`, not from the index.
- **`FinalizeTake()`** keeps the selected take and drops the rest (count goes to 0).
- **Safe recipe (verified):** every take has the item's exact length, added as `AddTake(mpi, a, a + n - 1)`. Every candidate is a video file: a still is first rendered to an mp4 of exactly n frames (`ffmpeg -loop 1 -i x.png -frames:v n -r 25 -c:v libx264 -pix_fmt yuv420p x.mp4`). With this recipe, switching 2 → 3 → 1 → 3 kept the item at 50 f, and the media path followed each switch. One quirk: a 50-frame mp4 take read `GetSourceEndFrame() == 49` while the item stayed 50 f long.

**8. Reading a non-current timeline: works** (except takes, see 7). On a timeline object that is not current:
- `GetItemListInTrack("video", 1)` with `GetStart()`, `GetDuration()`, `GetLeftOffset()` and `GetMediaPoolItem().GetName()` all return correct values. So do `GetProperty`, `GetSourceStartFrame`/`GetSourceEndFrame`, `GetSpeed` and `GetTrackTypeAndIndex()` (→ `['video', 2]`).

**Other facts later code relies on**
- **Source range of a placed item:**
  - `GetSourceStartFrame()` and `GetSourceEndFrame()` (exclusive) are in source frames.
  - `GetLeftOffset()` equals the source start for video.
  - `GetRightOffset()` is the number of source frames left after the out point (500-frame clip, 100..200 → 300).
  - `GetSourceStartTime()`/`GetSourceEndTime()` give seconds (8.0, 10.0).
  - For stills these read 0/0 and the left offset is 90000, so they are meaningless.
- **Media path:** `item.GetMediaPoolItem().GetClipProperty("File Path")` gives the absolute path.
- **`tl.GetEndFrame()` is exclusive:** 100 frames from 90000 → 90100.
- **Importing into a named sub-bin:** `B = mp.AddSubFolder(root, name)` (or find it in `root.GetSubFolderList()`), then `mp.SetCurrentFolder(B)`, `mp.ImportMedia([path])[0]`, and `mp.SetCurrentFolder(root)`.
- **Finding an existing media-pool item by path:** walk `GetClipList()`/`GetSubFolderList()` and compare `GetClipProperty("File Path")`. This found the same item again (equal `GetUniqueId()`). Re-importing is not needed.
- **Clip properties:** `Frames` (string, e.g. '500'; '1' for a still), `Type` ('Video' / 'Still' / 'Timeline'), `FPS`. A PNG imported in one run read FPS 24.0; later imports read 25.0. Don't rely on a still's FPS.
- **Still duration at append time:** not settable through start/end. Use mark in/out (see 2).

**Candidates: takes.** Item 7 works: takes persist across save and reopen, the uid is stable across switches, and the selected take is readable through the item's media-pool item. Later tasks must use the safe recipe:
- render every still candidate to an mp4 of exactly the row's length;
- add all takes with the same length and an inclusive end;
- make the timeline current before reading takes;
- identify the chosen take by media path + source start, never by `GetSelectedTakeIndex()`.

Per-row bins remain the fallback if a still ever has to be a take.
