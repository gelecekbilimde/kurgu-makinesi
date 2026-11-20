# Placing B-roll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A project skill `placing-b-roll` that fills the non-KAMERA script rows of frozen A-roll chapters with stock, graphics, screenshots or placeholders, and builds per-chapter B-roll timelines in Resolve, updated in place without losing editor changes.

**Architecture:** Offline, deterministic steps in `broll.py` (`requests`, `align`, `fetch`) write JSON files under `episodes/<ep>/broll/`. Resolve steps in `broll_resolve.py` (`layout`, `build`, `freeze`, `master`) are thin glue around pure modules that decide what goes where (`plan.py`). Claude's only judgment is filling `broll/requests.json` for STOK and GRAFİK/YAZI rows.

**Tech Stack:** Python 3 standard library + `unittest`; DaVinci Resolve Studio 21.2 scripting API via the rough cutter's `rv.sh`; FFmpeg (`drawtext`) for stills; HyperFrames' Chrome (`npx hyperframes browser path`) for screenshots; the stock finder and making-graphics `--batch` CLIs as subprocesses.

**Spec:** `docs/superpowers/specs/2026-11-20-broll-design.md`

## Global Constraints

- All positions are **integer frames, half-open `[start, end)`**, never seconds. Every JSON file the skill writes carries `"units": "frames"`.
- The frozen A-roll chapter timelines are **never modified**: no item, marker, track or property change. The skill only reads them (`layout`) and nests their media-pool item.
- `build` never changes an `editor: true` plan entry, nor any timeline item, marker or track the skill did not create.
- Stock only through `find_stock.py --batch`; graphics only through `make_graphic.py --batch`. Neither tool's delivered files are replaced.
- Gaps are never silent: every non-KAMERA row in a frozen chapter ends up placed, placeholdered or listed in the summary.
- B-roll timeline name: `<frozen chapter timeline name> B-roll`; episode master: `<prefix> B-roll`; media-pool bin: `<prefix> B-roll` with one sub-bin per chapter and per row for unused candidates.
- Tracks: V1 nested frozen chapter; V2 full-screen (STOK, KAYNAK, ARŞİV placeholders, `output: fullscreen` graphics rendered with `background: true`); V3 overlays (transparent `.mov`, YAZI, `background: false` overrides).
- Placeholder markers are ranged, colour **Lavender**, with `customData` `broll:<item id>`. Yellow is never used.
- Stock goes in video-only (`mediaType: 1`). Clips start at source frame 0.
- STOK candidate count per row: `max(3, ceil(row_frames / (5 * fps)))`.
- Turkish user-facing output, matching the sibling skills' tone (`Hiç aday bulunamadı`-style lines).
- Tests: `cd .claude/skills/placing-b-roll/tests && python3 -m unittest -q`. Resolve steps are verified live, not in unit tests.

## Review Focus

1. **A row that spans an off-script ad-lib in the middle** (row words, 10 unmatched words, more row words): the row's range must still be one range from its first to last matched word; only gaps *between* rows end a row early. Test `test_offscript_inside_row_stays_one_range` in Task 5.
2. **The same sentence appears in two rows** (writer repeats a line): alignment must stay monotone and give each row its own occurrence. Test `test_repeated_sentence_two_rows_monotone` in Task 5.
3. **An editor edits `requests.json` after a fetch** (new keywords): that row is fetched again with the new request; unchanged rows are not re-fetched, and the old candidates are not deleted. Test `test_changed_request_refetches_only_that_row` in Task 6.
4. **An editor trims one of two stock items of a row** (candidate 1 + filler candidate 2): the whole row is left as it is on rebuild, so the untouched candidate 2 is not moved over the editor's trim. Test `test_row_with_editor_item_is_left_whole` in Task 7.
5. **The script changes and a row key disappears** while it has editor entries: the entries are kept, untouched on the timeline, and listed in the summary as `satırı kayboldu`. Test `test_editor_entry_of_vanished_row_kept_and_reported` in Task 7.

---

### Task 1: Drop the YZ tag from the script template

**Files:**
- Modify: `templates/script/rules.py:15,28,87`
- Modify: `templates/script/build_template.py:15`, `templates/script/kilavuz.md:33,46`
- Regenerate: `templates/script/script-template.docx` (via `python3 templates/script/build_template.py`, as the README describes)
- Test: `templates/script/tests/test_rules.py`

- [ ] **Step 1: Update the tests:** `TAGS == ("KAMERA", "STOK", "ARŞİV", "GRAFİK", "YAZI", "KAYNAK")`; drop the `("yz", "YZ")` and `("AI", "YZ")` alias cases; add `test_yz_is_unknown`: `rules.parse_visual("[YZ] bir galaksi")` returns `([], ["YZ"], "bir galaksi")` (use the function name the module actually exposes at line 46) so the row warns "bilinmeyen TÜR".
- [ ] **Step 2:** Run `cd templates/script/tests && python3 -m unittest -q`. Expected: the changed tests FAIL.
- [ ] **Step 3:** Remove `"YZ"` from `TAGS`, the `"AI": "YZ"` alias, and `"YZ"` from the multi-shot set at line 87. Remove `[YZ]` from the guide line in `build_template.py` and from `kilavuz.md` (table row and the 7 s warning line). Regenerate the template docx.
- [ ] **Step 4:** Run the template tests, including `test_acceptance_cop31.py`. Expected: all PASS (COP31 has no YZ rows).
- [ ] **Step 5: Commit** `templates/script/`: `script template: drop the YZ tag`. Tell the user to paste the new `kilavuz.md` into the master doc's Kılavuz tab.

### Task 2: Shared chapter timeline name and the skill skeleton

**Files:**
- Modify: `.claude/skills/rough-cutting-a-roll/scripts/episode.py` (add a function), `.claude/skills/rough-cutting-a-roll/scripts/chapters.py:52-57` (use it)
- Create: `.claude/skills/placing-b-roll/scripts/` (empty package dir), `.claude/skills/placing-b-roll/tests/helpers.py`, `.claude/skills/placing-b-roll/tests/test_names.py`

**Interfaces:**
- Produces: `episode.chapter_timeline_name(prefix: str, chapter_title: str, ch: int) -> str` (ch 0-based; same output as today's `chapters.chapter_name`). `helpers.py` puts the skill's `scripts/` and the rough cutter's `scripts/` on `sys.path` and exposes `FIXTURES`, `make_episode(tmp, **manifest) -> Path`.

- [ ] **Step 1: Test** `test_chapter_timeline_name`: `("COP31", "1. Açılış: Zirve neden bu kadar önemli? (Begüm Dursun)", 0) -> "COP31 ch1 Açılış"`; `("COP31", "6. COP31 dünyayı değiştirebilir mi?", 5) -> "COP31 ch6 COP31 dünyayı değiştirebilir mi"`; a 100-character title is cut to 80 characters.
- [ ] **Step 2:** Run; expected FAIL (no such function).
- [ ] **Step 3:** Move the body of `chapters.chapter_name` into `episode.chapter_timeline_name`; `chapters.chapter_name(ch)` calls it with `PRE` and `sec["chapters"][ch]`.
- [ ] **Step 4:** Tests PASS; `python3 -c "import ast,sys; ast.parse(open('.claude/skills/rough-cutting-a-roll/scripts/chapters.py').read())"` succeeds.
- [ ] **Step 5: Commit**: `rough cutter: chapter timeline name shared via episode.py; placing-b-roll skeleton`.

### Task 3: Resolve API spike (live, throwaway script; findings kept)

Before building on them, confirm the Resolve 21.2 calls the build relies on. Work in a scratch Resolve project, never on COP31's timelines.

**Files:**
- Create: `.claude/skills/placing-b-roll/reference.md` (findings section "Resolve API, verified on 21.2")
- Scratch: `<scratchpad>/spike_resolve.py` (not committed)

- [ ] **Step 1:** Verify each of these and record the outcome (works / doesn't / workaround) in `reference.md`:
  1. `mp.AppendToTimeline([{mediaPoolItem, startFrame, endFrame, trackIndex: 2, recordFrame, mediaType: 1}])` places a clip on V2 at a given frame. Is `recordFrame` absolute (includes `tl.GetStartFrame()`)? Is `endFrame` exclusive, as for V1?
  2. A PNG still placed the same way gets exactly `endFrame - startFrame` frames.
  3. Nesting a timeline's media-pool item on V1 (as `chapters.py master` does) leaves the source timeline's items and markers unchanged.
  4. `TimelineItem.GetUniqueId()` survives saving, closing and reopening the project, and survives the editor moving and trimming the item.
  5. Which keys `TimelineItem.GetProperty()` returns (zoom, pan, tilt, crop, opacity, …), and whether speed and clip colour are readable.
  6. `tl.DeleteClips([item])` removes only that item; `AddMarker(..., customData)` + `DeleteMarkerByCustomData` round-trip; markers without our customData are untouched.
  7. **Take Selector:** `item.AddTake(mpi, start, end)`, `GetTakesCount()`, `SelectTakeByIndex()`. Do takes survive save/reopen, and does `GetUniqueId` stay the same after a take switch?
  8. Reading a timeline without making it current: `GetItemListInTrack("video", 1)` on a non-current timeline object, with `GetLeftOffset()`/`GetStart()`/`GetDuration()`/`GetMediaPoolItem().GetName()`.
- [ ] **Step 2:** Write the decision in `reference.md`: candidates as **takes** if 7 works, otherwise **per-row bins**; and any workaround for 1-8 that the later tasks must use. Tasks 7-8 follow whatever this records.
- [ ] **Step 3: Commit** `reference.md`: `placing-b-roll: Resolve API findings`.

### Task 4: Rows and requests

**Files:**
- Create: `.claude/skills/placing-b-roll/scripts/rows.py`, `scripts/reqs.py`, `scripts/broll.py` (subcommand `requests`)
- Test: `tests/test_rows.py`, `tests/test_reqs.py`; fixture `tests/fixtures/script.json` (6-8 rows in 2 chapters: KAMERA, STOK, GRAFİK, `[STOK, YAZI]`, KAYNAK with link, KAYNAK without link, ARŞİV) and `tests/fixtures/sections.json`

**Interfaces:**
- Produces:
  - `rows.load(ep: Episode) -> list[Row]`; `Row` is a dataclass `{id, key, chapter: int (0-based, index in sections.json chapters), tags: list[str], visual, links, refs, ses, est_s}`. The chapter comes from the nearest level-2 heading at or above the row's `heading` in `script.json`, matched **by title** to `sections.json["chapters"]`; a row whose chapter isn't found raises with the row id.
  - `rows.broll_rows(rows, frozen: set[int]) -> list[Row]`: non-KAMERA rows of frozen chapters (`episode.json "frozen"` is 1-based; convert).
  - `requests.json` format: `{"units": "frames", "rows": {"<key>": [Request, ...]}}`; `Request` is one of
    `{"tag": "STOK", "kind": "stock", "query": str}`,
    `{"tag": "GRAFİK"|"YAZI", "kind": "graphic", "template": str, "fields": dict, "variant"?: str, "background"?: bool}`,
    `{"tag": "KAYNAK", "kind": "kaynak", "url": str}`,
    `{"tag": str, "kind": "placeholder", "reason": "no template"|"arşiv"|"link yok"|"geçersiz istek", "need"?: str}`.
  - `reqs.load(path) -> dict`, `reqs.save(path, data)`, `reqs.autofill(row) -> list[Request]` (deterministic parts: ARŞİV → placeholder `arşiv`; KAYNAK → `kaynak` with `links[0]`, or placeholder `link yok`), `reqs.pending(rows, data) -> list[Row]` (a row is pending if any of its tags has no request), `reqs.validate(req, templates: dict) -> list[str]` (problems; templates from `make_graphic.py --list --json`).
  - `broll.py requests EP`: adds autofill requests, saves, then prints the pending rows as JSON (`id, key, tags, visual, links, refs, est_s`) plus the templates list path hint, for Claude to fill. Never overwrites an existing request.

- [ ] **Step 1: Tests:** chapter assignment by title (fixture where `script.json` has a front-matter heading that `sections.json` lacks); `broll_rows` with `frozen=[2]` returns only chapter-2 non-KAMERA rows; `autofill` cases above; `pending` treats `[STOK, YAZI]` with only a STOK request as pending; `validate` reports an unknown template, a missing required field, and an empty `query`; `requests` run twice leaves a hand-edited request unchanged.
- [ ] **Step 2:** Run; FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run; PASS.
- [ ] **Step 5: Commit**: `placing-b-roll: rows and requests`.

### Task 5: Layout and alignment

**Files:**
- Create: `scripts/align.py`, `scripts/broll_resolve.py` (subcommand `layout` only, plus the shared Resolve connection helper), `broll.py` subcommand `align`
- Test: `tests/test_align.py`; fixtures `tests/fixtures/layout-ch2.json`, `tests/fixtures/transcripts/*.json` (small, in Resolve's `segments[].words[]` timecode format)

**Interfaces:**
- Consumes: `rows.Row`, `rows.broll_rows`; `episode.Episode` (`wav_tr`, `offset_f`, `fps`).
- Produces:
  - `broll/layout/ch<N>.json` (N 1-based): `{"units": "frames", "timeline": str, "frames": int, "pieces": [[rec, clip, src_start, src_end], ...]}`, written by `rv.sh broll_resolve.py layout EP` from the live frozen chapter timeline's V1 items (read-only; uses the reading method Task 3 verified). `rec` is relative to the timeline start.
  - `align.chapter_words(ep, layout) -> list[Word]`; `Word = (start_f, end_f, norm_text)` on the chapter timeline. A transcript word belongs to a piece when its camera-frame midpoint (`tc2f(mid) + offset_f`, the convention of `sections.py:63`) lies in `[src_start, src_end)`; its frames map by `rec + (f - src_start)`. Normalise text with the same `norm` as `sections.py`.
  - `align.align_rows(rows_in_chapter: list[Row], words: list[Word]) -> dict[key, Span|None]`; `Span = {"start": int, "end": int, "first_word": int, "last_word": int}`. **All** rows of the chapter are aligned (KAMERA too, for boundaries).
  - `broll/rows.json`: `{"units": "frames", "fps": int, "chapters": {"<N>": {"timeline": str, "rows": {"<key>": {"id", "start", "end"} | null}}}}` from `broll.py align EP`, with each B-roll row's **coverage range** applied.
- Algorithm (pinned):
  - SES text minus parentheses, normalised, as tokens. Walk the chapter's rows in script order with a cursor into `words`. For each row, find its 3-gram hits at or after the cursor, in order. The row is found when hits cover at least `max(3, 30% of its tokens)` tokens. First hit word → `first_word`, last hit word → `last_word`. The cursor moves past `last_word`. A row that is not found gets `None` and doesn't move the cursor.
  - Coverage: `start = words[first_word].start_f`. `end = next_row.start` when the next found row in the chapter is non-KAMERA **and** at most 3 words lie between `last_word` and its `first_word`. Otherwise `end = words[last_word].end_f`.

- [ ] **Step 1: Tests:** `test_word_mapping_through_pieces` (a word inside a cut-out part is dropped; offsets applied); `test_row_found_and_range`; `test_offscript_inside_row_stays_one_range`; `test_repeated_sentence_two_rows_monotone`; `test_row_not_spoken_is_none`; `test_coverage_runs_to_next_broll_row`; `test_coverage_stops_before_kamera_row`; `test_coverage_stops_at_offscript_gap` (5 unmatched words between rows); `test_last_row_ends_at_last_word`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement `align.py`, `broll.py align` and the `layout` glue. **Step 4:** PASS.
- [ ] **Step 5 (live):** On the acceptance copy (Task 9 Step 1 creates it, so do that step first if it doesn't exist), run `layout`, then `align`. Check that `layout/ch3.json`'s piece list matches `timelines/<ch3>.json` `flat`, and that the frozen chapter's item count and markers are unchanged.
- [ ] **Step 6: Commit**: `placing-b-roll: layout and row alignment`.

### Task 6: Fetch

**Files:**
- Create: `scripts/fetch.py`, `scripts/stills.py`, `broll.py` subcommand `fetch`
- Test: `tests/test_fetch.py`, `tests/test_stills.py` (fake runner for the subprocesses, like the sibling skills' `fakes.py`)

**Interfaces:**
- Consumes: `requests.json`, `rows.json`, `make_graphic.py --list --json` (template `output` and `frames.min/max`).
- Produces:
  - `broll/fetched.json`: `{"units": "frames", "rows": {"<key>": [Asset, ...]}}`, one list entry per request, in request order. `Asset = {"tag", "kind": "stock"|"graphic"|"kaynak"|"placeholder", "request_hash": str, "track": 2|3, "files": [{"file": abs path, "code", "frames": int|null (null = still), "credit": str|null}], "hold": abs path|null, "note": str|null}`.
  - `fetch.run(ep, runner=subprocess.run) -> Summary`. It only fetches requests whose `request_hash` (sha1 of the canonical request JSON + the row's coverage frames for graphics) differs from the one stored. Groups:
    - stock → one `find_stock.py --batch requests.json --out broll/stok/` call; code = row id (`R012`), `orientation: horizontal`, count per Global Constraints. `files` in the finder's ranking order, `frames` from `duration_s * fps` floored, `credit` from the candidate. Exit 2 / no candidates → placeholder asset with note `aday bulunamadı`.
    - graphic → one `make_graphic.py --batch rows.json --out broll/grafik/` call; code `G` + row number (`G012`); `frames = clamp(coverage, min, max)`; `background = request.get("background", template.output == "fullscreen")`; track 2 if background else 3. If coverage > max: `hold` = last frame extracted to PNG (`stills.last_frame(video, png)`). A render reported in `notes` as failed → placeholder asset with that note.
    - kaynak → `stills.screenshot(url, png)`; failure → placeholder asset, note `sayfa açılmadı` / `sayfa engelli olabilir`.
    - placeholder → `stills.placeholder(png, row_id, tag, text, overlay: bool)`; track 3 placeholders are `overlay=True`.
  - `stills.placeholder(out, row_id, tag, text, overlay)`: FFmpeg `color` + `drawtext` 1920×1080 PNG, font from `fc-match -f '%{file}' sans`; full frame dark grey when `overlay=False`; transparent with a lower-third band when `True`; text `"<row_id> · <tag>"` plus the description wrapped at ~60 characters (via `textfile=`).
  - `stills.screenshot(url, out, timeout_s=30)`: Chrome path from `npx --no-install hyperframes browser path` run in the making-graphics skill dir; `--headless --hide-scrollbars --window-size=1920,1080 --screenshot=<out> <url>`. Non-zero exit, timeout or missing file → `sayfa açılmadı`; a PNG under 20 KB → `sayfa engelli olabilir`.
  - `stills.last_frame(video, out)`: `ffmpeg -sseof -0.1 -i video -frames:v 1 out`.
- Prints the summary: rows fetched, from cache/archive, placeholders by reason.

- [ ] **Step 1: Tests:** batch inputs built correctly (codes, counts for a 7 s and a 17 s row, background/track for `bar-chart` vs an overlay template vs a `background: false` override); frames clamped to min/max and `hold` set only above max; `test_changed_request_refetches_only_that_row`; finder exit 2 → placeholder asset; a failed graphic in `notes` → placeholder asset; an invalid request (Task 4 `validate`) → placeholder `geçersiz istek` with the problems as note; screenshot failure modes; `placeholder()` command line contains the text file and the right size (fake runner).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5 (live):** `STILLS_LIVE=1` tests render one placeholder of each kind and screenshot `https://example.com`; open the PNGs and check that Turkish letters (ğ, İ, ş) render.
- [ ] **Step 6: Commit**: `placing-b-roll: fetch stock, graphics, screenshots and placeholders`.

### Task 7: Plan, read-back merge and build actions (pure)

**Files:**
- Create: `scripts/plan.py`, `scripts/credits.py`
- Test: `tests/test_plan.py`, `tests/test_credits.py`

**Interfaces:**
- Consumes: `rows.json`, `fetched.json`, the Task 3 decision (takes vs bins).
- Produces:
  - `Item = {"id": "<row id>#<n>" | "E<n>", "row": key|null, "track": 2|3, "start", "end", "file"|null, "src_in", "src_out", "kind", "code"|null, "editor": bool, "deleted": bool, "uid": str|null, "props": dict, "marker": str|null}`.
  - `plan.desired(chapter_rows: dict, fetched: dict) -> list[Item]` (no uid yet), per row and asset:
    - stock: candidate 1 from `start`, then next candidates until the coverage is full; the last one trimmed (`src_out = src_in + remaining`); if all candidates together are shorter, the rest of the range stays empty and the summary says `stok yetmedi`.
    - graphic: one item `[start, start + frames)`, plus the hold still `[start + frames, end)` when `hold` is set; a graphic longer than coverage is trimmed.
    - kaynak and placeholder: one still over the full coverage; placeholders also get `marker` = `"<row_id> <tag>: <visual>"` (+ `need`).
  - `plan.readback(last: list[Item], seen: list[dict]) -> list[Item]`; `seen` items are `{uid, track, start, end, file, src_in, src_out, props}` read from V2/V3. Rules exactly as the spec's read-back section: changed → `editor: true` with the seen values; our uid missing → `editor: true, deleted: true`; unknown uid → new `E<n>` entry, `row: null, editor: true`.
  - `plan.actions(current: list[Item], desired: list[Item]) -> (keep, remove, add)`. A row with **any** editor entry is left whole (none of its items is in `remove` or `add`). For other rows, an item equal in `(track, start, end, file, src_in, src_out)` is kept; otherwise the old one is removed and the new one added. Items of rows no longer in `rows.json` with `editor: false` are removed; with `editor: true` they stay and are reported `satırı kayboldu`.
  - `plan.json`: `{"units": "frames", "chapters": {"<N>": {"timeline": str, "items": [Item, ...]}}}`.
  - `credits.collect(items, fetched) -> list[str]`: one line per distinct credit of non-deleted items on the timeline, timeline order, graphics' `sources` and KAYNAK URLs included, duplicates dropped; written to `broll/kaynaklar.txt`.

- [ ] **Step 1: Tests:** desired: stock fill with 3 candidates for a 17 s row, trim of the last, `stok yetmedi`; graphic + hold; placeholder marker text. Readback: moved, trimmed, property-changed, deleted, added. Actions: unchanged row kept; changed fetch → remove + add; `test_row_with_editor_item_is_left_whole`; `test_editor_entry_of_vanished_row_kept_and_reported`; a deleted editor entry is never re-added. Credits: unused candidates excluded, editor-added item with a known file included, duplicates once.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5: Commit**: `placing-b-roll: plan, read-back and build actions`.

### Task 8: Build, freeze and master in Resolve

**Files:**
- Modify: `scripts/broll_resolve.py` (subcommands `build EP [N...]`, `master EP`), `scripts/broll.py` (subcommand `freeze EP N` / `unfreeze EP N`, offline, edits `"broll_frozen"`, 1-based)

**Interfaces:**
- Consumes: everything above; the Task 3 findings for every API call.
- Behaviour of `build` per frozen chapter not in `broll_frozen` (all such chapters, or only the given N):
  1. Find the B-roll timeline by name. If it doesn't exist: create it in the `<prefix> B-roll` bin, append the frozen chapter's media-pool item on V1, add V2 and V3. Never make the frozen chapter timeline current and never call any setter on it.
  2. If it exists: read V2/V3 items into `seen` and run `plan.readback`.
  3. Import new files into `<prefix> B-roll/ch<N>` (reuse already imported media-pool items by path).
  4. `plan.actions` → delete `remove` items (`DeleteClips`) and our markers (`DeleteMarkerByCustomData("broll:<id>")`), append `add` items (track, record frame, source range, video only), add Lavender markers for placeholders, store the new uids and `props` (read back right after placing) in `plan.json`.
  5. Unused candidates: as takes on the placed item, or into `<prefix> B-roll/ch<N>/<row id>`, per Task 3.
  6. Write `kaynaklar.txt` and print the summary: rows placed; placeholders by reason; `stok yetmedi`; rows not found in the chapter; `satırı kayboldu`; then **"Gereken şablonlar"**: the distinct `need` lines.
- `master`: `<prefix> B-roll`, rebuilt each time (it holds no editor work: chapters are nested), chapters in order: the B-roll timeline if it exists, otherwise the frozen A-roll chapter, otherwise nothing and a note. Chapter-start markers Green, as in the A-roll master.

- [ ] **Step 1 (live):** On the acceptance copy, run `build` twice in a row. The second run reports 0 added / 0 removed, and the frozen chapter timelines are unchanged (item count, each item's `GetLeftOffset`/`GetDuration`, marker dict compared before/after).
- [ ] **Step 2 (live):** Change one request in `requests.json`, `fetch`, `build`: only that row's items change.
- [ ] **Step 3 (live):** `freeze EP 3` → `build` skips chapter 3; `unfreeze` → it's rebuilt. `master` nests the chapters in order.
- [ ] **Step 4: Commit**: `placing-b-roll: build, freeze and master in Resolve`.

### Task 9: SKILL.md and acceptance on the COP31 copy

**Files:**
- Create: `.claude/skills/placing-b-roll/SKILL.md`; update `reference.md` (file formats, the summary lines, Resolve findings)
- Modify: `.claude/skills/finding-stock-footage/SKILL.md` and `.claude/skills/making-graphics/SKILL.md` "For the B-roll skill" sections only if an interface detail differs from what they say

- [ ] **Step 1: Acceptance copy:** `episodes/cop31-broll/` with a copy of COP31's `episode.json` (prefix `COP31B`), `plans/`, `transcripts/`, `sections.json`, `edits/`; `script.json` from `python3 templates/script/script_doc.py episodes/cop31/script-av.docx episodes/cop31-broll`. Build its chapter timelines with `chapters.py chapters`, then `chapters.py freeze` the chapters holding R012, R015 and R023 (check `rows.load`; expected 3-5). The real `episodes/cop31` and its `COP31 …` timelines are not touched.
- [ ] **Step 2: SKILL.md** (frontmatter `name: placing-b-roll`; description starting "Use when an editor wants B-roll placed over frozen A-roll chapters …", mentioning STOK/GRAFİK/YAZI/KAYNAK/ARŞİV rows, Resolve, rebuilding without losing edits). Body: overview (scripts do the work, Claude only fills requests), requirements, the pipeline `requests` → (Claude fills STOK and GRAFİK/YAZI: English keywords; a template only when it fits and the cell has the data, else `placeholder` with `need`) → `layout` → `align` → `fetch` → `build` → review in Resolve → repeat `build` → `freeze` → `master`; what the editor may change in Resolve and what survives; the marker legend (Lavender = placeholder); common mistakes (running on an unfrozen chapter; editing the frozen chapter; deleting `plan.json`).
- [ ] **Step 3: Acceptance (live), per the spec:**
  - R012 renders through `bar-chart` with background, sits on V2 over R012's words and holds its last frame to the row's end;
  - R015 and R023 get stock on V2 and a YAZI placeholder on V3;
  - the other GRAFİK rows of the frozen chapters get placeholders, and "Gereken şablonlar" lists them;
  - the frozen chapter timelines are unchanged after three builds;
  - the editor (you, in Resolve) moves one clip, trims another, zooms a third, deletes a fourth, adds a clip on V2 and a marker; after `build` all of it is still there, and untouched rows are updated after a request change;
  - `broll/kaynaklar.txt` lists exactly the sources on the timeline.
  Record the run in `reference.md` (commands and the summary output).
- [ ] **Step 4:** Full offline test run: `cd .claude/skills/placing-b-roll/tests && python3 -m unittest -q`, plus the template and rough-cutter checks touched in Tasks 1-2. All PASS.
- [ ] **Step 5: Commit**: `placing-b-roll: SKILL.md and COP31 acceptance`. Update the project memory with the skill's status.
