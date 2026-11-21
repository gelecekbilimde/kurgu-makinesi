# cutting-shorts reference

## Resolve API facts

Spike run 2026-11-21 on Resolve Studio 21.2.0.6 (Linux), throwaway project `shorts-spike`, 25 fps, timeline start 90000 (01:00:00:00). Builds on placing-b-roll's "Resolve API, verified on 21.2" (append rules, exclusive end frames, stills, `AddTrack`, uids), which is not repeated here. `mp` = MediaPool, `t` = Timeline, `s0 = t.GetStartFrame()`.

Re-run: `bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh .claude/skills/cutting-shorts/scripts/spike_api.py demo/cop/raw/COP/P1011088.MOV` prints one `OK`/`FAIL` line per fact below (last runs: 0 FAIL; without the camera path the video-only check prints `SKIP`). Facts marked "(exploration)" come from the one-off probes of the spike and are not re-checked by `spike_api.py`.

**1. Vertical timeline: works.**
`t = mp.CreateEmptyTimeline(name)`, then `t.SetSetting("useCustomSettings", "1")`, `t.SetSetting("timelineResolutionWidth", "1080")`, `t.SetSetting("timelineResolutionHeight", "1920")`, `t.SetSetting("timelineFrameRate", "25")`: all return True.
- Read back with `t.GetSetting(k)`: `'1'`, `'1080'`, `'1920'`, and `25.0` (frame rate is a float, the others strings).
- `timelineOutputResolutionWidth/Height` follow on their own: `'1080'` / `'1920'` (exploration).
- The project's own resolution stays 1920x1080 (`p.GetSetting("timelineResolutionWidth")`).
- `timelinePlaybackFrameRate` cannot be set per timeline: `SetSetting` returned False, `GetSetting` `''` (exploration).
- The timeline frame rate was set on a fresh, empty timeline; setting it on a timeline with media was not tried.

**2. Transform units: Pan is in timeline pixels, Tilt is not.**
Measured with a 3840x2160 25 fps test pattern (ffmpeg `drawbox` squares centred on known source pixels), appended `mediaType: 1` on the vertical timeline, `it.SetProperty("ZoomX"/"ZoomY"/"Pan"/"Tilt", v)` (all True, read back exactly), then `r.OpenPage("color")`, `t.SetCurrentTimecode("01:00:00:10")`, `p.ExportCurrentFrameAsStill(png)`: it wrote a 1080x1920 RGB PNG of the timeline frame. Box centres were found by scanning the PNG.
- Precondition: input scaling `t.GetSetting("timelineInputResMismatchBehavior") == "scaleToFit"` (the default; `demo` reads `scaleToFit` too). Item `Scaling` property is 0.
- Formula, source pixel `(sx, sy)` of a `SW x SH` clip on a `W x H` timeline, when the clip fits by width (true for 16:9 into 1080x1920):
  - `s = (W / SW) * Zoom`
  - `x = W/2 + (sx - SW/2) * s + Pan`
  - `y = H/2 + (sy - SH/2) * s - Tilt * (SH * W / SW) / H`
- So `Pan` = timeline pixels, positive moves the image right, independent of zoom. `Tilt` is positive = up, also independent of zoom, but one unit = `fitted image height / timeline height` pixels: 0.31640625 px for UHD 16:9 on 1080x1920.
- Evidence (UHD pattern, measured centre vs formula, all within 0.5 px): zoom 1 → red (1920,1080) at (540, 960), lime (1700,700) at (478.5, 853.5). Zoom 3.1605 Pan 200 → red (739.5, 960). Zoom 3.1605 Pan -150 Tilt -100 → red (389.5, 991.5), lime (194.5, 653.5). Zoom 2 Tilt 300 → red (540, 865). Zoom 3.1605 Tilt 1000 → red y 643.5, lime y 305.5 (exploration). Tilt 300 moved the image 95 px at zoom 1, 2 and 3.1605 alike.
- Tilt's factor, checked at zoom 1 with Tilt 300 (exploration): UHD source on 1080x1920 → 95 px up (0.3164); 2160x2160 square source → 169 px (0.5625); 1080x1920 source → 300 px (1.0); UHD source on a 1920x1080 timeline → 300 px (1.0), and Pan 300 → 300 px there too. All four equal `fitted height / timeline height`.
- Inferred, not measured: for a clip that fits by height (narrower than the timeline's aspect) Pan probably scales the same way by `fitted width / W`; every Pan measured here had a width-fitting clip.
- **Zoom that fills the height:** `Zoom = (H / SH) / (W / SW) = 1920*3840 / (2160*1080) = 3.160493827…` (`ZoomX = ZoomY`, `ZoomGang` is True by default). Source scale is then 1920/2160 = 0.8889, so the frame shows 1215 of the 3840 source columns.
- Camera check (P1011088.MOV, 3840x2160 25 fps, exploration): at fill zoom, mean brightness of the outermost column/row of the still was 108.7/88.0 (left/right) and 126.3/73.6 (top/bottom), so no black edge. **Pan limit at fill zoom is ±1166.67** (`(3840*0.8889 - 1080) / 2`, inferred from the formula): Pan 1160 had no black edge (left column 99.5), Pan 1300 gave a black left column (0.0). Tilt 100 at fill zoom gave a black bottom row (0.0): at fill zoom Tilt must stay 0.
- To centre source column `cx` at fill zoom: `Pan = (1920 - cx) * 0.8889`, clamped to ±1166 (inferred from the formula).

**3. Subtitles: `ImportMedia([srt])` + `AppendToTimeline` works; cues land at the SRT frames only on an empty timeline.**
- `mp.ImportMedia([srt])` returns one clip with `GetClipProperty("Type") == "Subtitle"` (`Start TC` = first cue, `Frames` `''`, `FPS` None).
- `mp.AppendToTimeline([clip])` on an **empty** timeline creates subtitle track 1 (`t.GetTrackCount("subtitle")` 0 → 1) and puts each cue at `s0 + SRT time × fps`: 00:00:01,000–00:00:02,400 → 90025..90060, 00:00:03,040–00:00:05,000 → 90076..90125. `GetEnd()` is exclusive (= start + `GetDuration()`).
- **On a timeline that already has anything, the cues go after `t.GetEndFrame()`** (end + SRT time), not at the SRT times: with video at 90200..90300 the first cue landed at 90325, with or without an empty subtitle track made by `t.AddTrack("subtitle")`, and with `{"mediaPoolItem": clip, "trackIndex": 1}`. A second SRT on a timeline with cues also went after the end (90250 after a track ending at 90225). `recordFrame` is ignored (`recordFrame: s0+500` still gave 90025 on an empty timeline). → **Append the captions SRT first, to the new empty timeline, then place video with `recordFrame`** (after the SRT, video appended with `recordFrame: s0 + 200` landed at 90200..90300 and the cues stayed at 90025..90175, exploration; video overlapping the cues' frame range was not tried, but it sits on a different track).
- `t.ImportIntoTimeline(srt, {})` returns False and adds nothing.
- Read-back: `t.GetItemListInTrack("subtitle", 1)`; per cue `GetName()` = the cue text, `GetStart()`, `GetEnd()`, `GetDuration()`, `GetUniqueId()` (a full UUID like `07aac07b-8590-45ce-8f4f-dc31c125617f`). A two-line cue reads back with the line break as **U+2028** (`'Birinci satır çığ ikinci satır Şüö'`); Turkish letters (ç ğ ı İ ş ü ö) are intact.
- Rounding: times on the frame grid land exactly. Half-frame times rounded unevenly (exploration): 06,020 (150.5 f) → 150, 06,060 (151.5) → 151, 06,500 (162.5) → 163, 00,500 (12.5) → 13; 07,030 (175.75) → 176, 08,019 (200.475) → 200, 08,981 (224.525) → 225. Write SRT times as exact frame times (`frame * 1000 / fps` ms, an integer at 25 fps).
- `item.SetName("x")` on a cue returns False (text unchanged, uid unchanged). `GetRightOffset()` on a cue returns None (exploration), `GetMediaPoolItem()` returns None. So the API cannot edit a cue; text and timing edits are the editor's.
- `t.DeleteClips([cue])` removes that cue only (exploration).
- uids, text and frames of the cues are identical after `SaveProject`, `LoadProject("demo")` (only loaded; `GetCurrentProject().GetName()` confirmed the switch) and `LoadProject("shorts-spike")` again: e.g. 90025..90060 `7584c850`, 90076..90125 `04b339b0` read the same before and after. Re-verified in two probe runs (one started from `demo`, one from `shorts-spike`); the exploration also showed it via `broll-spike`.
- **Re-importing a changed SRT at the same path returns the old clip** (same `GetMediaId()`; old text, exploration: a timeline appended from it showed `ilk sürüm`, not the new `ikinci sürüm`). `mp.DeleteClips([clip])` then `ImportMedia` gives the new text (exploration). Deleting the pool clip leaves the cues already on timelines in place.
- Step 6 fallback (`captions.srt` + "File › Import › Subtitle" line) is **not needed**: subtitles can be placed by script.

**4. Markers on a timeline with nested timelines: API side works.**
Parent vertical timeline with two nested timelines on V1 (`mp.AppendToTimeline([{"mediaPoolItem": child.GetMediaPoolItem(), "trackIndex": 1, "recordFrame": …, "mediaType": 1}])`, no audio item created).
- `t.AddMarker(40, "Fuchsia", "aday 1", "not", 250, "short:c1")` → True. `t.GetMarkers()` → `{40: {'color': 'Fuchsia', 'duration': 250, 'note': 'not', 'name': 'aday 1', 'customData': 'short:c1'}}`: keys are frames from the timeline start (not absolute), duration in frames. `"Green"` works the same.
- `t.GetMarkerByCustomData("short:c1")` → the same dict **without the frame**; unknown customData → None. To find a marker's frame, scan `GetMarkers()`.
- A second `AddMarker` on an occupied frame returns False.
- `AddMarker` past the timeline end (frame 825 on a 775-frame timeline) and with a duration past the end (500 + 5000) both return True (the duration case is exploration): validate ranges ourselves.
- `t.UpdateMarkerCustomData(400, "short:c2b")` → True, `GetMarkerCustomData(400)` → `'short:c2b'` (exploration). `DeleteMarkerByCustomData("short:long")` removes only that one (exploration).
- A marker on a nested child timeline (`child.AddMarker(10, "Blue", …)`) does not show in the parent's `GetMarkers()` (`{}`).

**5. `Timeline.SetName` and video-only appends: work.**
- `t.SetName("COP31 short 01")` → True; `GetName()` and lookup by name give the new name. `SetName` to a name another timeline has → False, name unchanged.
- Camera clip (has audio) appended with `mediaType: 1` → 1 video item, 0 audio items (the timeline has an empty audio track 1). Without `mediaType` → video + audio item (exploration).

**Still to verify by hand (UI)**
- Marker: change an engine marker's colour to Green and resize it in the UI, then `GetMarkers()`: expected (not observed) the same key with `color: 'Green'` and the new `duration`, customData kept. If a resize from the left moves the key, the marker must be matched by customData.
- Subtitle cue: edit a cue's text in the UI, then `GetName()` (does it return the edited text?) and `GetUniqueId()` (same uid?). Same for a UI trim/move of a cue.
