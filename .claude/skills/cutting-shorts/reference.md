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

**6. Later observations (Tasks 10-11, `demo`).**
- `GetIsTrackEnabled` reads False for **every** track of a timeline that is not current (seen on a short and on a frozen chapter). Read or set track enables only while that timeline is current (`mute_scratch` runs right after `sync_short`, on our timeline).
- An SRT appended to a timeline that already has cues landed right after the **last cue** (c4: last cue ended at 1141, the one-cue SRT at `00:00:00,000` landed at 1141..1268), not after the timeline end (1216, the end card). Either way a cue cannot be placed at a chosen frame on a non-empty timeline: `recordFrame`, `trackIndex` 1/2, `mediaType`, `startFrame/endFrame` were all ignored (probe on a throwaway timeline: each append went after the last cue).
- `AppendToTimeline` `startFrame`/`endFrame` are in the clip's own frames: a 29.97 fps stock item 189 timeline frames long needs `endFrame = startFrame + round(189 * 29.97 / 25)`.

## Files in `episodes/<ep>/shorts/` (all frames, half-open `[start, end)`, `"units": "frames"`)
- `layout/ch<N>.json`: `{"units", "timeline", "frames", "pieces": [[rec, clip, a, b]]}`, the frozen chapter's V1 (the B-roll skill's format), written by `read`.
- `broll/ch<N>.json`: `{"units", "timeline", "items": [{"track", "start", "end", "file", "src_in", "src_out", "props", "kind", "src_size", "hold_of"?}]}`, the chapter's `… B-roll` timeline V2 and up, read live; `kind` = the fetched asset's kind (`stock | graphic | kaynak | placeholder`), `still` for a graphic's hold still, `editor` for a file the B-roll skill never fetched; `src_size` = `[w, h]` from the media pool's `Resolution`; a graphic's hold still carries `hold_of` (the graphic's file).
- `sentences.json`: `{"units", "chapters": {"<N>": [{"start", "end", "text"}]}}` on the chapter timeline. A sentence ends after `. ? ! …` or before a pause longer than 12 frames at 25 fps.
- `candidates.json`: `{"units", "candidates": [Candidate]}`. Candidate = `{"id": "c<n>", "rank", "title", "pieces": [{"chapter", "start", "end"}], "teaser": {"chapter", "start", "end"}, "reason", "teaser_rating", "accepted", "frozen", "header"}`. Ranges are on the chapter timelines. `check` assigns missing ids and snaps; `accept` writes `accepted` and ranges; `freeze`/`unfreeze` write `frozen`. Never overwritten as a whole.
- `<id>/media.json`: the job `prepare` hands to `shorts_media.py` (camera items, cut-outs).
- `<id>/crop.json`: `{"units", "timeline": [1080, 1920], "items": [{"rec", "clip", "src_in", "src_out", "segment", "camera", "src_size", "face": {"cx", "cy", "h"} | null, "transform": {"ZoomX", "ZoomY", "Pan", "Tilt"}}]}`. One crop per piece (segment) and camera clip: face = median over 9 sampled frames of each camera item of that clip in that piece, in source pixels, so the framing holds across the A-roll cuts inside a piece. Transform = exact height fill (ZoomX = ZoomY = 3.160494 for UHD), face centre centred horizontally (Pan clamped to the image edge), Tilt 0; `null` face = centre crop.
- `<id>/assets.json`: `{"units", "id", "end_card_frames", "crop", "captions", "cues": [{"start", "end", "text"}], "teaser_cutout": [{"file", "rec", "end"}], "graphics": [{"role", "file", "range", "placeholder", "vertical"}], "replace": {"<long-form file>": "<vertical re-render>"}, "needed": ["<Gereken şablonlar line>"]}`. `role` = `teaser-caption | end-card | header | watermark`. Cue and graphic ranges are on the short.
- `<id>/captions.srt`: the passage cues, times exact on the frame grid (`frame * 1000 / fps` ms), lines joined with `\n` (Resolve reads them back with U+2028).
- `<id>/grafik/`, `<id>/stills/`, `<id>/siyah/`: renders, placeholder stills (`<role>-<sha1[:8]>.png`, keyed by everything drawn on them), black-padded copies (`<stem>-<sha1[:8]>-siyah.png|mp4`, keyed by source path, size and mtime). `teaser-cutout-<sha1[:8]>.mov` (`teaser-cutout-<k>-<sha1[:8]>.mov` when the teaser crosses camera items): ProRes 4444 with alpha, the speaker cut out over the teaser frames, keyed by camera file, source range, crop and source size. A file whose content changes gets a new name because Resolve's media pool returns the clip already imported from a path, with its old length.
- `plan.json`: `{"units", "shorts": {"<id>": {"timeline": uid, "timeline_name", "items": [Item], "subtitles": [Cue], "segments": [...]}}}`, see the `splan.py` docstring. Item = the B-roll skill's plan item plus `anchor`, `flag`, `background`; Cue = `{"start", "end", "text", "uid", "editor", "deleted", "anchor"}`. `editor: true` = the editor's (changed, added or deleted by them): never touched again.

## Track layout of a short (1080x1920, episode fps)
| Track | What |
|---|---|
| V1 | camera items with their audio (A1 stereo scratch, disabled on a fresh timeline; A2 the recorder WAV) |
| V2 | full-screen B-roll from the long-form V2 (stock centre-cropped to fill; graphics re-rendered vertical, or fitted to the width as a black-padded copy and flagged), end card |
| V3 | overlays from the long-form V3 (vertical re-render, else fitted to the width with nothing behind, flagged) |
| V4 | teaser caption (`teaser-caption` template, word by word) |
| V5 | teaser cut-out (speaker over the caption) |
| V6 | watermark (passage only) |
| V7 | header (`"header": true` only) |
| V(n+4) | a long-form chapter's own editor track Vn (n > 3) |
| Subtitle 1 | passage captions: ≤ 2 lines, ≤ 18 characters a line (Resolve's default subtitle size fits 1080 px; the API cannot set the size), never over the teaser or end card; a cue shorter than 1 s (fps frames) is lengthened into the following gap or merged with a neighbour when the lines still fit. Script spelling only for words that match the script exactly, or differ by a unit or apostrophe suffix one to one (`1,5` → `1,5°C`); any other spoken word keeps the transcript's spelling |

No B-roll over the teaser. B-roll is copied video-only (`mediaType: 1`), at 100 % speed, without opacity or composite mode: an item that had another speed, opacity < 100 or a composite mode is flagged (`uzun videoda hız %150: %100 hızla kopyalandı`, `uzun videodaki opaklık/karışım modu kopyalanmadı`). A long-form placeholder, and an item without a file (Text+, generator, compound clip, Fusion), is not copied (the speaker shows; Fuchsia marker + "Kopyalanmayan öğeler").

## Summary lines (`build`, stderr)
```
c4: dondurulmuş, atlandı                        (frozen; first)
c1 '<timeline>': <a> eklendi, <r> kaldırıldı, <k> korundu (<e> düzenleyici öğesi)
  Uyarı: <problem>                              (e.g. renamed timeline, collision "yer dolu", ffmpeg failure)
Kontrol edilecekler:                            (flagged items incl. the watermark, the subtitles re-import note)
  - c1: V2:ch3:805#1 (291-553): dikey sürümü olmayan grafik genişliğe sığdırıldı (arkası siyah)
Kopyalanmayan öğeler:                           (long-form placeholders and file-less items)
  - c4: bölüm 4 [5003, 5317) V3 R023-2-YAZI-4fa6176b.png
  - c4: bölüm 4 [5400, 5480) V3 dosyasız öğe (Text+, jeneratör, bileşik klip)
Kayan düzenleyici öğeleri:                      (editor items/cues whose words moved; Fuchsia marker, left in place)
Gereken şablonlar:
  - teaser-caption: ...
-> episodes/<ep>/shorts/plan.json
```
Each section prints `yok` when empty. `prepare` prints `<id>: N kamera parçası, N altyazı, N dikey B-roll grafiği, N yer tutucu -> assets.json`, `Not:` lines and its own `Gereken şablonlar`. `prepare` stops a short with `<id>: hata: …` (others go on) for a camera piece missing from `episode.json`'s clips or a missing layout field; it writes `captions.srt` and `assets.json` only after every media step succeeded. Re-running `prepare` re-renders the graphics under new `-N` names, so the next build replaces those items once (`N eklendi, N kaldırıldı`).

## Acceptance run (Task 11, 2026-11-21, `episodes/cop31-broll`, Resolve `demo`, COP31B only)
**The editor's UI work was simulated through the API** (review markers: delete + `AddMarker` with the new colour/duration and the same customData; edits as in the B-roll skill's Task 9), not done by hand.
1. Long-form snapshot before (every non-short COP31B timeline, review timeline excluded: uid, every video/audio/subtitle item `(uid, start, duration, left offset)`, markers): 9 timelines, 613 items, 126 markers.
2. `read` → ch3 48 pieces / 5 B-roll items, ch4 39 / 3. `candidates` → 147 sentences. The candidate step (Claude standing in for the subagent, following the prompt in SKILL.md) appended 4 candidates to the existing c1/c2. `check` → `6 aday, 0 hatalı`; ids c3..c6; lengths 30.5-42.5 s, teasers 1.96-3.16 s; a scan of every piece and teaser boundary against the chapter words: **0 inside a word**.
3. `review` → `COP31B short adayları`, 2 chapters, 16369 frames, **14 markers** (8 pieces + 6 teasers; c1/c2 Green as accepted before, the rest Fuchsia).
4. Editor: c2 markers back to Fuchsia, c4 markers Green, c4's first piece marker resized 495 → 759 frames. `accept` → `Kabul edilen adaylar: c1, c4`; c4 piece 0 = ch4 `[5001, 5757)` (end snapped from 5760), passage 42.5 s.
5. `prepare` (c1, c4; 3 min 20 s) → c4: `9 kamera parçası, 15 altyazı, 0 dikey B-roll grafiği, 2 yer tutucu`; Gereken şablonlar: teaser-caption, end-card. `build` → `c1: 3 eklendi, 3 kaldırıldı, 9 korundu` (the two G012 padded copies under their new hashed names, and the re-rendered watermark), `c4: 14 eklendi`. Only c1 and c4 built (c2's earlier timeline untouched). Rebuild → both `0 eklendi, 0 kaldırıldı`.
6. c4 timeline: 1080x1920 at 25.0, 1216 frames. V1 9 camera items at Zoom 3.160494, Pan -69..+17, Tilt 0 (face centred: checked on ffmpeg crops of the crop windows); teaser 0..79 first; V2 stock `R023-2` (2560x1440) 578..767 at the fill zoom, Pan 0 (centre crop); V2 end card placeholder 1141..1216 showing "COP31"; V4 teaser-caption placeholder 0..79, V5 cut-out 0..79, V6 watermark 79..1141; 15 cues 81..1141 (passage only). Markers: reason + teaser at 0, joins at 79 and 835, the uncopied R023 YAZI placeholder 81+314. c1: V2 `G012-1-…-siyah.mp4` 291..553 and its hold 553..797 fitted with black and flagged (Fuchsia ranged markers + Kontrol lines), watermark a summary line only.
7. **teaser-caption with a real `words` field:** the making-graphics fixture `words-demo` copied to `graphics/templates/starter/teaser-caption/` (name, a `words` field, overlay, vertical), `prepare c4` → batch row with 4 words timed `0..23, 23..42, 42..65, 65..76`, rendered `teaser-caption-1.mov` (ProRes 4444 alpha, 2160x3840, 79 frames) and only end-card still needed; `build c4` → `2 eklendi, 2 kaldırıldı`, V4 0..79 = `teaser-caption-1.mov`. Template folder removed again, `prepare c4` + `build` → placeholder back, then `0/0`.
8. Editor edits: c4: cue 450..577 deleted and the corrected text (`%40'ı`) imported as a one-cue SRT (it lands at 1141..1268, after the last cue, see fact 6); stock moved 578 → 880..1069 (delete + append, same source range and zoom); Yellow marker at 600. c1: G012 hold still deleted. `build` → `c1: 0 eklendi, 0 kaldırıldı, 12 korundu (1 düzenleyici öğesi)`, `c4: 0/0, 15 korundu (2 düzenleyici öğesi)`. Both timelines identical to the edited state (items, uids, cues, Yellow marker); only c1's flag marker over the deleted hold went (flags are for our live items). plan.json: c1 hold and c4 stock `editor deleted`, `E1` the moved stock, the old cue `editor deleted`, the new cue `editor`. Two more builds: 0/0, identical.
9. `freeze c4` → build prints `c4: dondurulmuş, atlandı`, c4 timeline identical; `unfreeze` → 0/0.
10. Long-form snapshot after 10 builds, 1 review, 1 accept: **identical** (`cmp`). Project saved, `demo` on the Edit page.

## Demo episode findings (2026-11-24, `COP31 Demo`)
- **Captions at 32 characters overflowed 1080 px.** Resolve's default subtitle style takes about 46-52 px per character, so `captions.MAX_CHARS` is 18.
- **A `number` graphic could not be re-rendered vertically:** its archived value is decoded (`{"base", "exp", "text"}`). `graphics._request_fields` sends the text back.
- `ExportCurrentFrameAsStill` leaves the subtitle track out; check captions in a render (`ExportSubtitle: True, SubtitleFormat: "BurnIn"`).
- **Render target:** paths outside Resolve's media storage (here anything but `~/Videos`) raised a modal "render path inaccessible", `AddRenderJob` returned `''`, and the API answered `None` until the dialog was closed.
- **Pan of a clip that fits by height** scales by `fitted width / timeline width`, as inferred above: the 760x520 watermark on 1920x1080 needed Pan 1020 for 838 px (measured on the render).
- A word the transcript stretches over silence (`1995'ten`, `Yani`) is dropped from the captions though it is spoken; the editor adds it.
- A passage snapped 2 frames before a word can pick up 2 frames of the graphic before it; delete that item on the short.

## Still to verify by hand (UI)
- The subtitle track's Stroke setting (green border) and whether a rebuild keeps it.
- Marker: change an engine marker's colour to Green and resize it in the UI, then `GetMarkers()`: expected (not observed) the same key with `color: 'Green'` and the new `duration`, customData kept. If a resize from the left moves the key, the marker must be matched by customData. (`accept` relies on this.)
- Subtitle cue: edit a cue's text in the UI, then `GetName()` (does it return the edited text?) and `GetUniqueId()` (same uid?). Same for a UI trim/move of a cue. The acceptance replaced a cue instead (delete + new cue elsewhere).
- A real UI move or trim of a B-roll item on a short (does it keep the uid?). Either way it reads as the editor's.
- Re-importing `captions.srt` by hand after the "altyazılar değişti" note: the next build should clear the note.
- The look of a full short in the viewer: teaser caption behind the head with a real `teaser-caption` template, end card, watermark scale.
