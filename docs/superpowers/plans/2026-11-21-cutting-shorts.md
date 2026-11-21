# Cutting Shorts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A project skill `cutting-shorts` that proposes short candidates from an episode's signed-off chapters, lets the editor accept them on a review timeline, and builds each accepted one as a 1080×1920 Resolve timeline (teaser → passage → end card) with the long-form B-roll, subtitles and a word-by-word teaser caption behind the head, rebuilt without losing editor changes.

**Architecture:** Same shape as `placing-b-roll`: `shorts.py` (offline steps, plain `python3`), `shorts_media.py` (face/matte steps, `.venv/bin/python`), `shorts_resolve.py` (Resolve steps through `rv.sh`). One judgment step: a subagent writes `shorts/candidates.json`. Pure modules hold all logic and are unit-tested; Resolve modules are thin and verified live. Read-back reuses `placing-b-roll/scripts/plan.py` (`readback`, `actions`) and `sync.py`.

**Tech Stack:** Python 3.12 stdlib + `unittest`; `.venv` with `mediapipe` + `numpy` for face detection and the speaker matte; FFmpeg; DaVinci Resolve Studio 21.2 API via `rv.sh`; `make_graphic.py --batch`.

**Spec:** `docs/superpowers/specs/2026-11-21-shorts-design.md`

## Global Constraints

- Integer frames, half-open `[start, end)`, `"units": "frames"` in every JSON file. Episode fps from `episode.json` (25 for COP31).
- Vertical timeline 1080×1920 at the episode fps.
- Eligible chapter = in `"frozen"` **and** `"broll_frozen"` of `episode.json`. Nothing else is read for a short.
- Never change a long-form timeline: frozen A-roll chapters, `… B-roll` chapter timelines, `<prefix> B-roll`, `<prefix>` master. Long-form timelines are only read (no `SetCurrentTimeline`, no setters, no markers).
- Passage length 30–45 s (`750..1125` frames at 25 fps; scale by fps), teaser and end card excluded. Teaser `[1.5 s, 3.5 s]`, inside the passage. 5–8 candidates.
- Boundary padding = the rough cutter's: `PRE_F = 2`, `POST_F = 3` (`rough-cutting-a-roll/scripts/cutplan.py`), never past the middle of a word gap.
- Markers: engine = **Fuchsia**, accepted candidate = **Green**, **Yellow is the editor's** and never written. Our markers carry customData `short:<…>`.
- B-roll is copied **video-only** (`mediaType: 1`). No grade, no audio fixes, nothing copied from chapter items beyond cut ranges.
- Captions: Resolve subtitle track, ≤ 2 lines, ≤ 32 characters a line, split at word gaps, script spelling for matched words; none over the teaser or the end card.
- Teaser caption: word by word, timed to speech, via a making-graphics template with the new `words` field; no B-roll during the teaser.
- Graphics only through `make_graphic.py`; missing template (`teaser-caption`, `end-card`, `short-header`) → placeholder + "Gereken şablonlar" line. No design ships in `graphics/`.
- All user-facing output in Turkish, like the sibling skills.
- Tests: `cd .claude/skills/cutting-shorts/tests && python3 -m unittest -q` (offline, stdlib only; media modules take an injectable `runner`/detector so tests need no `.venv`).

## Review Focus

1. **A boundary that lands inside a word or keeps a long pause at a join** after the editor resizes a marker: `accept` must re-snap (Task 3 `test_snap_inside_word_moves_to_gap`, Task 5 `test_accept_resnaps_resized_marker`).
2. **A B-roll item that only partly overlaps a piece, or an editor-trimmed item whose source doesn't start at 0**: the short must show exactly the overlapping source frames (Task 6 `test_partial_overlap_keeps_source_offset`).
3. **A piece that crosses an A-roll cut** (two camera clips under one piece): V1 gets one item per camera segment, contiguous (Task 6 `test_piece_across_aroll_cut`).
4. **A candidate whose chapter lost its sign-off** (`broll_frozen` removed after candidates were written): `check`/`build` refuse that candidate with a message, never build from an unsigned chapter (Task 3 `test_unsigned_chapter_rejected`).
5. **Episode without `"title"`**: `prepare` stops with a clear message instead of rendering an end card with an empty title (Task 8 `test_missing_title_stops`).

---

## File Structure

```
.claude/skills/cutting-shorts/
  SKILL.md, reference.md, requirements.txt (mediapipe, numpy)
  scripts/
    shorts.py           CLI: candidates | check | prepare | freeze | unfreeze   (python3)
    shorts_media.py     CLI: faces | matte                                     (.venv/bin/python)
    shorts_resolve.py   CLI: read | review | accept | build                    (rv.sh)
    eligible.py         eligible chapters, chapter words with raw text, sentences
    cands.py            candidates.json load/save/validate/snap, timeline names
    review.py           review-timeline marker maths (pure)
    mapping.py          short layout: pieces → V1 segments, B-roll overlap/trim, teaser, end card, watermark
    captions.py         script spelling, subtitle cue splitting, SRT writer
    crop.py             face box → Resolve transform (pure)
    faces.py            frame sampling + face detection (injectable detector)
    matte.py            teaser cut-out clip (injectable segmenter)
    graphics.py         vertical re-render requests, teaser caption/end card/header/watermark requests, placeholders
    splan.py            shorts/plan.json: desired items, read-back (via placing-b-roll plan.py), anchors, flags
  tests/  helpers.py, fakes.py, fixtures/, test_*.py
.claude/skills/making-graphics/scripts/manifest.py, kit/hf-kit.js, references/template-contract.md   (words field)
.claude/skills/placing-b-roll/scripts/align.py (raw text option), sync.py (track list), stills.py (size option)
```

Episode files: `shorts/sentences.json`, `shorts/candidates.json`, `shorts/layout/ch<N>.json` (A-roll, live), `shorts/broll/ch<N>.json` (B-roll items, live), `shorts/<id>/` (crop.json, teaser-cutout.mov, captions.srt, graphics, assets.json), `shorts/plan.json`.

---

### Task 1: `words` field type in making-graphics

**Files:**
- Modify: `.claude/skills/making-graphics/scripts/manifest.py` (FIELD_TYPES, `validate`), `.claude/skills/making-graphics/kit/hf-kit.js` (decode), `.claude/skills/making-graphics/references/template-contract.md` (table row)
- Test: `.claude/skills/making-graphics/tests/test_manifest_words.py`, fixture template `tests/fixtures/templates/words-demo/` (manifest + minimal `index.html` that prints the words; test-only, not in `graphics/`)

**Interfaces:**
- Produces: field type `"words"`; given value = JSON list (or JSON string of a list) of `{"text": str, "start": int, "end": int}` (frames from the graphic's start, at the render fps); template gets the same list decoded by `kit.vars()`. Checks: each `text` non-empty, `0 <= start < end <= frames`, starts non-decreasing, optional `max_items`. `make_graphic.py --batch` rows pass it under `fields` unchanged.

- [ ] **Step 1: Write the failing tests** in `test_manifest_words.py`:
  - `test_words_valid` → `validate(t, {"w": [{"text":"Bir","start":0,"end":10},{"text":"iki","start":10,"end":22}]})["w"]` equals the same list.
  - `test_words_json_string` → same list given as `json.dumps(...)` is accepted.
  - `test_words_overlapping_order` → starts `[10, 5]` raises `FieldError` mentioning `w`.
  - `test_words_end_before_start` and `test_words_empty_text` raise `FieldError`.
  - `test_words_past_frames` → `end` greater than the render's frames raises (validate gets `frames` via a new keyword `validate(t, raw, frames=None)`; `None` skips the bound).
  - `test_words_in_kit_types` → staging writes `"words"` into `kit-types` and `vars.json` holds the JSON-encoded list (use the existing staging test pattern with the fixture template).
- [ ] **Step 2:** `cd .claude/skills/making-graphics/tests && python3 -m unittest test_manifest_words -q` → FAIL.
- [ ] **Step 3:** Implement: add `"words"` to `FIELD_TYPES`; `validate(t, raw, frames=None)` handles it; callers in `make_graphic.py` pass the render's frames; `hf-kit.js` decodes `words` like `list` (JSON-parse strings, `""` → `[]`); contract table row "`words` | JSON list of `{text, start, end}` (frames from the graphic's start) | the same list | order, bounds, `max_items`".
- [ ] **Step 4:** Run the whole making-graphics suite → PASS.
- [ ] **Step 5:** Commit `making-graphics: words field type (word-timed captions)`.

### Task 2: Live API spike for vertical timelines and subtitles (Resolve running)

**Files:**
- Create: `.claude/skills/cutting-shorts/scripts/spike_api.py` (kept as a re-runnable probe), `.claude/skills/cutting-shorts/reference.md` (section "Resolve API facts")

Run in a throwaway Resolve project `shorts-spike` (create it, never touch `demo`). Record each answer with the exact calls in `reference.md`; later tasks rely on them.

- [ ] **Step 1:** Vertical timeline: create a timeline, `SetSetting("useCustomSettings","1")`, `timelineResolutionWidth/Height = 1080/1920`, fps; read them back.
- [ ] **Step 2:** Transform units: append a 3840×2160 camera clip; set `ZoomX/ZoomY` to fill height and `Pan/Tilt` to known values; export a still (`ExportCurrentFrameAsStill`) and measure where a known source pixel lands. Record the formula for `Pan`/`Tilt` (timeline pixels vs source pixels) and the zoom that fills 1920 height.
- [ ] **Step 3:** Subtitles: find a working way to put cues on a subtitle track from a script (try `MediaPool.ImportMedia([srt])` + `AppendToTimeline`, and `Timeline.ImportIntoTimeline`), whether cues land at the given frames, and how to read them back (`GetItemListInTrack("subtitle", 1)`, item `GetName()`, start/duration, uid). Record whether an edited cue's text is visible to `GetName()` and whether uids survive edits.
- [ ] **Step 4:** Markers on a timeline with nested timelines: `AddMarker` with duration + customData, `GetMarkers()` after a manual colour change and resize in the UI (do it by hand once; record the returned fields).
- [ ] **Step 5:** `Timeline.SetName` on an existing timeline; `AppendToTimeline` with `mediaType: 1` places video only.
- [ ] **Step 6:** If subtitles can't be placed by script, record it and the fallback chosen: write `captions.srt` and have the build print one line telling the editor to import it (File › Import › Subtitle) — Task 10 then reads back whatever is on the subtitle track. Commit `cutting-shorts: Resolve API facts for vertical timelines and subtitles`.

### Task 3: Eligible chapters, sentences, candidates file and snapping

**Files:**
- Create: `scripts/eligible.py`, `scripts/cands.py`, `scripts/shorts.py` (subcommands `candidates`, `check`, `freeze`, `unfreeze`), `tests/helpers.py` (same pattern as placing-b-roll's, also putting placing-b-roll's `scripts/` on the path), `tests/test_eligible.py`, `tests/test_cands.py`
- Modify: `.claude/skills/placing-b-roll/scripts/align.py`: `chapter_words(ep, layout, raw=False)`; with `raw=True` each tuple gains the original word text as a 4th element. Existing callers unchanged.

**Interfaces:**
- Consumes: `episode.Episode`, `align.chapter_words`, `rows_mod.load`.
- Produces:
  - `eligible.chapters(ep) -> list[int]` (sorted, in `frozen` ∩ `broll_frozen`).
  - `eligible.sentences(words, fps) -> list[dict]` `{"start","end","text"}`: split after words ending in `.?!…` or before a gap `> 12` frames (`PAUSE_F`).
  - `cands.load(path) -> dict` / `cands.save(path, data)`; schema `{"units":"frames","candidates":[{"id","rank","title","pieces":[{"chapter","start","end"}],"teaser":{"chapter","start","end"},"reason","teaser_rating","accepted":false,"frozen":false,"header":false}]}`; `id` is stable, `c1`, `c2`, … assigned by `check` when missing.
  - `cands.snap(start, end, words) -> (start, end, moved: bool)` on one chapter's words.
  - `cands.check(data, words_by_ch, eligible, fps) -> (data, notes: list[str], errors: dict[id, list[str]])`.
  - `cands.timeline_name(prefix, rank, title) -> str` = `f"{prefix} short {rank} {title}"` sanitised as `episode.chapter_timeline_name` does, ≤ 80 chars.
- `shorts.py candidates EP`: needs `shorts/layout/ch<N>.json` (Task 4); writes `shorts/sentences.json` `{"units","chapters":{N:[sentence]}}` and prints it plus each chapter's script rows (id, SES, GÖRÜNTÜ) as JSON for the subagent.

- [ ] **Step 1: Failing tests**
  - `test_eligible_needs_both` → `frozen [3,4]`, `broll_frozen [4]` → `[4]`.
  - `test_sentences_split_on_punct_and_pause`.
  - `test_snap_inside_word_moves_to_gap` → words `(100,120),(130,150)`, start `110` → `128` (= `130 - PRE_F`, not before gap middle `125`); end `140` → `123` (`120 + POST_F`); `moved` True.
  - `test_snap_never_past_gap_middle` → gap `(120,122)`: start → `121`, end → `121`.
  - `test_check_lengths` → passage of 700 frames gets an error `"pasaj 28,0 s (30–45 s olmalı)"`-style message; 900 passes; teaser 100 frames errors; teaser outside every piece errors.
  - `test_unsigned_chapter_rejected` → piece in a chapter not in `eligible` → error for that candidate only.
  - `test_check_assigns_stable_ids_and_keeps_existing`.
  - `test_freeze_unfreeze_cli` → `shorts.py freeze EP c2` sets `frozen: true`; unknown id exits non-zero.
  - `test_timeline_name_sanitised` → `("COP31B", 1, "1,5°C: hedef?")` → `"COP31B short 1 1,5C"`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run full suite + `placing-b-roll/tests` (align change) → PASS.
- [ ] **Step 5:** Commit `cutting-shorts: eligible chapters, sentences, candidates check and snapping`.

### Task 4: Live read of signed-off chapters (A-roll layout + B-roll items)

**Files:**
- Create: `scripts/shorts_resolve.py` (subcommand `read`), `tests/test_read.py`
- Modify: `.claude/skills/placing-b-roll/scripts/sync.py`: `track_items(tl, s0, fps, tracks=(2, 3))`; `None` = every video track above V1. Existing callers unchanged.

**Interfaces:**
- Consumes: `broll_resolve.connect`, `timeline_by_name`, `layout_from_items`; `build.broll_name`; `build.seen_item`.
- Produces: `shorts/layout/ch<N>.json` (same format as the B-roll skill's layout) and `shorts/broll/ch<N>.json` = `{"units","timeline","items":[{"track","start","end","file","src_in","src_out","props","kind"}]}` where `kind` comes from matching `file` against the B-roll skill's `fetched.json` (`stock|graphic|screenshot|placeholder|still`) and is `"editor"` for files the B-roll skill never fetched. `read_items(seen, fetched) -> list[dict]` is the pure part (tested).
- Read-only: no `SetCurrentTimeline`, no setters, no markers on these timelines.

- [ ] **Step 1: Failing tests** (pure part): `test_kind_from_fetched` (stock/graphic/placeholder/hold still), `test_editor_file_is_editor_kind`, `test_track_items_all_upper_tracks` (fake timeline with V1–V4 → items of V2–V4).
- [ ] **Step 2–4:** FAIL → implement → PASS (both suites).
- [ ] **Step 5:** Live: `$RV shorts_resolve.py read episodes/cop31-broll` with ch3/ch4 `broll_frozen` (set it with `broll.py freeze`); compare item counts with the B-roll timelines in Resolve; confirm both timelines unchanged (item uids and marker count before/after). Commit `cutting-shorts: read signed-off chapters live`.

### Task 5: Review timeline and accept

**Files:**
- Create: `scripts/review.py`, `tests/test_review.py`; add `review` and `accept` to `shorts_resolve.py`

**Interfaces:**
- Produces:
  - `review.offsets(chapter_frames: dict[int,int], eligible) -> dict[int,int]` (review-timeline start of each nested chapter).
  - `review.markers(data, offsets) -> list[dict]` (`frameId, color, name, note, duration, customData`): one per piece (`short:<id>:p<i>`) and per teaser (`short:<id>:t`); color `Green` when `accepted`, else `Fuchsia`; `name` = `"<rank>. <title>"` (+ `" · teaser"`); `note` = reason + `"teaser: <rating>"`.
  - `review.read_back(data, markers_from_resolve, offsets) -> (data, notes)`: a candidate is accepted when any of its markers is Green; deleted markers → not accepted; moved/resized → new chapter ranges (a marker that crosses a chapter edge is clamped to the chapter it starts in, with a note).
- `review`: delete and recreate `<prefix> short adayları` (ours only; bin `<prefix> Shorts`), nesting each eligible chapter's B-roll timeline in order, then add `review.markers`.
- `accept`: read markers back, apply `review.read_back`, run `cands.check` (re-snap), save, regenerate the review timeline, print accepted ids.

- [ ] **Step 1: Failing tests:** `test_offsets_cumulative`, `test_marker_per_piece_and_teaser`, `test_green_means_accepted`, `test_deleted_markers_unaccept`, `test_accept_resnaps_resized_marker` (resize lands inside a word → `check` snaps, note printed), `test_marker_across_chapter_edge_clamped`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Live on the COP31 copy with a hand-written two-candidate `candidates.json`: `review`, turn one marker Green and resize it in the UI, `accept`; check `candidates.json`. Commit `cutting-shorts: review timeline and accept`.

### Task 6: Short layout mapping

**Files:**
- Create: `scripts/mapping.py`, `tests/test_mapping.py`

**Interfaces:**
- Consumes: layout and broll files from Task 4; a candidate.
- Produces: `mapping.short_layout(cand, layouts, brolls, fps, end_card_frames) -> dict` with
  - `"segments"`: ordered `[{"part":"teaser"|"passage","chapter","ch_start","ch_end","rec"}]` (teaser first, then each piece; `rec` = start on the short);
  - `"v1"`: `[{"rec","clip","src_in","src_out","segment"}]` camera items (one per camera range; a piece crossing an A-roll cut gives several);
  - `"broll"`: `[{"rec","end","track","file","src_in","src_out","kind","props","anchor":{"chapter","ch_start","ch_end"}}]` for passage segments only, trimmed to the overlap, source offset kept;
  - `"teaser"`, `"end_card"`, `"frames"` (total) ranges on the short.
- `mapping.anchor_of(short_layout, rec_start, rec_end) -> dict | None` (chapter range under a short range; `None` if it spans segments) — used for editor-item anchors.

- [ ] **Step 1: Failing tests:** `test_teaser_first_then_passage`, `test_piece_across_aroll_cut`, `test_partial_overlap_keeps_source_offset` (B-roll item `[100,300)` src `[40,240)`, piece `[200,500)` → `src_in 140`), `test_no_broll_in_teaser`, `test_placeholder_not_copied_listed` (returned in `"skipped"`), `test_end_card_after_passage`, `test_anchor_roundtrip`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `cutting-shorts: short layout mapping`.

### Task 7: Captions

**Files:**
- Create: `scripts/captions.py`, `tests/test_captions.py`

**Interfaces:**
- Produces:
  - `captions.spell(words, script_rows) -> list[str]`: per passage word, the script's raw word where `difflib.SequenceMatcher` on normalised tokens (`align.norm`) gives an equal block, else the transcript's raw word.
  - `captions.cues(words_on_short, fps, max_chars=32, max_lines=2) -> list[{"start","end","text"}]` (`text` uses `\n` between lines): break at line/cue limits, after `.?!…`, and before gaps `> 12` frames; a cue ends at its last word end + `POST_F`, extended to the next cue's start when the gap is ≤ 12 frames; cues never overlap the teaser or end card ranges given.
  - `captions.teaser_words(words_on_short, teaser) -> list[{"text","start","end"}]` relative to the teaser start (the `words` field value).
  - `captions.srt(cues, fps) -> str`.

- [ ] **Step 1: Failing tests:** `test_script_spelling_wins` (transcript `"1,5"`/`"cop31"` vs script `"1,5°C"`/`"COP31'in"`), `test_unmatched_keeps_transcript`, `test_line_and_cue_limits` (no line > 32 chars, ≤ 2 lines), `test_break_on_pause`, `test_no_cue_in_teaser_or_end_card`, `test_teaser_words_relative`, `test_srt_format` (frames → `HH:MM:SS,mmm` at 25 fps).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `cutting-shorts: captions`.

### Task 8: Media prep: face crop, teaser cut-out, graphics

**Files:**
- Create: `scripts/crop.py`, `scripts/faces.py`, `scripts/matte.py`, `scripts/graphics.py`, `scripts/shorts_media.py` (`faces`, `matte`), `prepare` in `shorts.py`, `requirements.txt`, `tests/fakes.py`, `tests/test_crop.py`, `tests/test_media.py`, `tests/test_graphics.py`
- Modify: `.claude/skills/placing-b-roll/scripts/stills.py`: `placeholder(..., size=(1920, 1080))`; existing callers unchanged.

**Interfaces:**
- `crop.transform(face, src_w, src_h, tl_w=1080, tl_h=1920) -> dict` (`ZoomX, ZoomY, Pan, Tilt`) using the Task 2 formula: zoom = fill height × `EXTRA = 1.15`; face centre horizontally centred, vertically at 1/3 of the frame height, both clamped so no edge shows. `face` = `{"cx","cy","h"}` in source pixels, or `None` → centre crop.
- `faces.piece_faces(video, ranges, detect, runner) -> list[dict|None]`: samples 9 evenly spaced frames per range (FFmpeg), median of detections; `detect(png_path) -> {"cx","cy","h"} | None` (mediapipe face detection in production, fake in tests). Writes `shorts/<id>/crop.json`.
- `matte.cutout(video, src_range, transform, out, segment, runner)`: extracts the teaser frames at the short's crop, segments the speaker (`segment(png) -> mask png`, mediapipe selfie segmentation in production), writes `shorts/<id>/teaser-cutout.mov` (ProRes 4444 with alpha, 1080×1920).
- `graphics.requests(ep, cand, short_layout, templates, archive) -> (batch_rows, placeholders, needed)`:
  - B-roll graphics: render record from `broll/grafik/results.json` (`template`, `values`, `variant`, `background`) → same with `"vertical": true` when the template has `vertical: true`, else none (fit + flag in Task 9);
  - `teaser-caption` (`fields: {"words": captions.teaser_words(...)}`, frames = teaser length), `end-card` (`fields: {"title": ep.m["title"]}`), `short-header` when `header`, `watermark` (`state: static`) — each a placeholder (vertical size) + a "Gereken şablonlar" line when the template is missing.
- `shorts.py prepare EP [id ...]`: for accepted, not frozen candidates: runs `shorts_media.py faces/matte` through `.venv/bin/python` (subprocess, injectable), the graphics batch (`make_graphic.py --batch --out shorts/<id>/grafik`), placeholders, `captions.srt`, and writes `shorts/<id>/assets.json`. Stops with `"episode.json'da 'title' yok (bitiş kartı için gerekli)"` when the title is missing.

- [ ] **Step 1: Failing tests:** `test_crop_centres_face`, `test_crop_clamps_at_edge`, `test_crop_no_face_centre`, `test_face_median_of_samples`, `test_matte_commands` (fake runner sees FFmpeg extract, segment calls per frame, ProRes 4444 encode with `yuva444p10le`), `test_graphic_vertical_rerender_request`, `test_non_vertical_template_not_rerendered`, `test_missing_template_placeholder_and_needed`, `test_teaser_caption_words_field`, `test_missing_title_stops`, `test_prepare_skips_frozen_and_unaccepted`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Live: `.venv/bin/pip install -r .claude/skills/cutting-shorts/requirements.txt`; run `prepare` for one accepted COP31 candidate; look at a sampled crop still and `teaser-cutout.mov` over black. Commit `cutting-shorts: media prep (face crop, teaser cut-out, graphics)`.

### Task 9: Short plan and read-back

**Files:**
- Create: `scripts/splan.py`, `tests/test_splan.py`

**Interfaces:**
- Consumes: `mapping.short_layout`, `assets.json`, `crop.json`; `placing-b-roll/scripts/plan.py` `readback`, `actions`.
- Produces:
  - Tracks: V1 A-roll, V2 B-roll full-screen + end card, V3 overlays, V4 teaser caption, V5 teaser cut-out, V6 watermark (passage only), V7 header (when on).
  - `splan.desired(short_layout, assets, crops) -> list[item]`: plan items in the B-roll skill's item shape (`id, track, start, end, file, src_in, src_out, kind, props, marker`) plus `anchor`; V1 items carry the crop transform in `props`; stock gets the centre-crop fill transform; KAYNAK screenshots (`kind: screenshot`) are fitted to the width and flagged; non-vertical full-screen graphics get fit-to-width over black and a `flag`; non-vertical overlays fit-to-width with no background and a `flag`; editor-transformed long-form items (non-default `props` in the broll file) get the centre crop and a `flag`.
  - `splan.flags(items) -> list[marker dict]`: Fuchsia ranged markers for teaser, every join between pieces, every flagged item; one marker at frame 0 with the reason (customData `short:<id>:…`).
  - `splan.stale_anchors(editor_items, new_layout) -> list[item]`: editor items whose anchor no longer maps to the same short frames (each gets a Fuchsia marker + summary line; never moved).
  - `shorts/plan.json` = `{"units","shorts":{id:{"timeline","timeline_name","items","subtitles"}}}`; `subtitles` = cues as placed (+ uid when the API gives one).
  - `splan.subtitle_readback(last, seen) -> (keep_editor, ours)` same rules as items: an edited, moved or deleted cue becomes `editor: true` and is never rewritten.

- [ ] **Step 1: Failing tests:** `test_tracks_by_kind`, `test_v1_carries_crop`, `test_screenshot_fit_width_flagged`, `test_non_vertical_fullscreen_fit_and_flag`, `test_overlay_fit_without_background`, `test_editor_transformed_item_flagged`, `test_markers_teaser_joins_reason`, `test_editor_item_kept_by_readback` (via plan.readback), `test_stale_anchor_flagged_not_moved`, `test_edited_cue_kept`, `test_deleted_cue_not_refilled`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `cutting-shorts: short plan and read-back`.

### Task 10: Build in Resolve

**Files:**
- Add `build` to `scripts/shorts_resolve.py`; `tests/test_build_glue.py` for the pure glue (append spec with `mediaType: 1`, transform application order, rename decision)

**Interfaces:**
- Consumes: Task 2 facts, `splan`, `sync.Media`, `sync.place`-style uid diffing, `sync.track_items(..., tracks=None)`.
- `build EP [id ...]`: per accepted, not frozen candidate: find its timeline by the uid/name in `shorts/plan.json` (rename with `SetName` when rank/title changed; never create a second one); create it 1080×1920 at episode fps in bin `<prefix> Shorts/<id>` if missing; read back items and subtitles; remove/place our untouched items (`SetProperty` for transforms right after placing); place subtitles (or write `captions.srt` and print the import line, per Task 2); add flag markers; save plan after removes and after every placement (the B-roll skill's rule). Never touches long-form timelines (assert by name prefix before any setter).
- Summary per short (Turkish): `eklendi / kaldırıldı / korundu (düzenleyici öğesi)`, flags, `Kopyalanmayan yer tutucular`, `Kayan düzenleyici öğeleri`, `Gereken şablonlar`, and frozen/skipped shorts.

- [ ] **Step 1: Failing tests** for the glue: `test_append_spec_video_only`, `test_rename_when_title_changed`, `test_frozen_short_skipped`, `test_refuses_long_form_name`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Live on the COP31 copy: build two accepted shorts; rebuild → `0 eklendi, 0 kaldırıldı`; long-form timelines unchanged (uids + markers before/after). Commit `cutting-shorts: build shorts in Resolve`.

### Task 11: SKILL.md, reference.md and acceptance

**Files:**
- Create: `.claude/skills/cutting-shorts/SKILL.md` (frontmatter `name: cutting-shorts`, description starting "Use when an editor wants vertical shorts cut from a finished long-form episode…"; steps read → candidates (subagent prompt: pick and rank 5–8, 30–45 s, stitched pieces from `sentences.json`, teaser 1.5–3.5 s inside the passage, reason, teaser rating; write `shorts/candidates.json`, never overwrite an existing entry) → check → review → accept → prepare → build → freeze; what the editor may do; common mistakes)
- Modify: `reference.md` (file formats, track layout, acceptance run), project memory line

- [ ] **Step 1:** Write SKILL.md and reference.md.
- [ ] **Step 2: Acceptance** on `episodes/cop31-broll` (prefix COP31B, ch3/ch4 B-roll frozen), every spec bullet:
  - candidates via a real subagent run within 30–45 s; `check` leaves no boundary inside a word;
  - review timeline shows all candidates; accept two (one with a resized piece) → only those two built, with the resized range;
  - both shorts 1080×1920: teaser first with word-by-word caption behind the head (placeholder if no `teaser-caption` template; test once with the fixture template from Task 1 copied into a scratch design and removed after), face centred, R012's graph fitted and flagged, stock centre-cropped, subtitles on the passage only, watermark, end card with the title;
  - no long-form timeline changes after any number of builds;
  - editor fixes a caption, moves one B-roll item and deletes another → after rebuild all three as left; `freeze` a short → skipped by the next build.
- [ ] **Step 3:** Full offline suites (cutting-shorts, placing-b-roll, making-graphics) → PASS. Commit `cutting-shorts: SKILL.md and COP31 acceptance`.
