# Graphics Builder (making-graphics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A framework skill that lets editors design graphics with Claude Code and render them from HyperFrames templates by tool call, shipped with the brainstorm design as an editable starter example.

**Architecture:**
- A Python CLI (`make_graphic.py`) reads a template's `template.json`, validates fields, then stages a temporary HyperFrames project. The project holds the template's HTML, the chosen design's tokens and variant, and a small JS kit.
- The CLI renders the project with the pinned local HyperFrames and delivers the result like the stock finder: numbered files, `results.json`, `kaynaklar.txt` and a content-hashed archive.
- Every visual value lives in editor-owned files under `graphics/`, and the framework code holds none.

**Tech Stack:**
- Python 3 standard library and `unittest`.
- HyperFrames (npm, pinned exact) with Node 22.
- Host FFmpeg/FFprobe.
- Plain JS for the kit: animations are driven by HyperFrames' `hf-seek` event, with no GSAP.

**Spec:** `docs/superpowers/specs/2026-11-13-graphics-builder-design.md`

## Global Constraints

- **Paths:**
  - Skill folder `S = .claude/skills/making-graphics/`.
  - Editor files: `graphics/designs/<design>/`, `graphics/templates/<design>/<template>/`, `graphics/config.json`.
  - Archive: `assets/graphics/`.
- **HyperFrames:** pinned to an exact version (0.9.41 or later at build time) in `S/package.json` and `S/package-lock.json`. Install with `npm ci`; `S/node_modules/` is gitignored.
- **Telemetry:** every HyperFrames call runs with `HYPERFRAMES_NO_TELEMETRY=1` and `DO_NOT_TRACK=1`. No HeyGen sign-in, no cloud, no Docker renders.
- **Host:** FFmpeg and FFprobe on PATH, installed by the user with RPM Fusion then `dnf install ffmpeg`. The setup step prints that hint in Turkish and never runs sudo.
- **Frames:** lengths are integer frames everywhere; the default fps is 25. Default resolution is 3840×2160; `--resolution 1080p` gives 1920×1080; vertical is 2160×3840. Fixed-canvas templates ignore resolution and vertical.
- **Formats:** overlay is ProRes 4444 `.mov` with alpha, fullscreen is H.264 `.mp4`, still is a transparent `.png`.
- **No visual values in framework code:** no colour, font, size or easing name may be hardcoded in `S/scripts/`, `S/kit/` or SKILL.md. Every visual value comes from the design's `tokens.css` and variant CSS.
- **No HTML at render time:** a render request never writes or edits HTML. When no template fits, say so and offer the design workflow.
- **Messages:** every message to the editor is in Turkish, and errors fail clearly instead of rendering something broken. Exit codes: 0 ok, 1 failure, 2 validation error.
- **Delivery:**
  - Never overwrite; numbering continues.
  - `--out` defaults to `~/Downloads/grafik/<template>-<slug>/`.
  - `kaynaklar.txt` holds the raw `source` field text, deduplicated, in order.
- **Starter labelling:** it is labelled "starter example" in `design.md`, in its README line and on every sample. It is never presented as the channel's design.
- **Text rules:**
  - No double em dashes in any text the skill writes.
  - Fonts are OFL, with their licence files beside them and Turkish coverage (ğ ş ı İ ç ö ü).
- **Git:**
  - Never send the user's identity, project or email externally.
  - Never stage `*.rpm` or `wiki/.obsidian/workspace.json`.
  - Commit per task on the feature branch; merge or push only when the user asks.
- **USER REVIEW GATE steps are mandatory stops** (user decision): render, show, and wait for the user's verdict before the next task.
- **Test command:** `cd .claude/skills/making-graphics/tests && python3 -m unittest -q`. Live tests run only with `GRAPHICS_LIVE=1` and need `npm ci` done plus FFmpeg on PATH.

## Review Focus

1. **Turkish and overhanging text:** a Turkish field with ğ/İ or a long word, at the manifest's maximum length, renders inside the frame with no clipped last glyph. Covered by the `samples.json` longest-text rows of each starter template plus `test_live_*` poster checks.
2. **Editing a design after a render:** a token change, then the same request again, must re-render, not reuse the stale archive. Covered by `test_design_change_invalidates_archive` in Task 4.
3. **A broken render or missing toolchain:** Chrome or FFmpeg missing, or HyperFrames exits non-zero. The editor gets one Turkish line saying what to run, the archive gets no half-written entry and the output folder gets no 0-byte file. Covered by `test_render_failure_leaves_no_entry` in Task 4 and `test_setup_reports_missing_ffmpeg` in Task 1.
4. **Odd fps:** `--fps 30` or `--fps 50` with a template whose limits are written at 25 fps must scale the limits, not reject valid lengths. Covered by `test_frame_limits_scale_with_fps` in Task 2.
5. **A batch row with an unknown template or a bad field:** the other rows still render, and the bad row is reported in `results.json` notes and on stderr. Covered by `test_batch_bad_row_does_not_stop_others` in Task 4.

---

## File map

| File | Responsibility |
|---|---|
| `S/package.json`, `S/package-lock.json` | pin HyperFrames |
| `S/scripts/hf.py` | HyperFrames/FFmpeg command builder, env, runner injection |
| `S/scripts/setup.py` | toolchain check + `npm ci` + `browser ensure` + `doctor` |
| `S/kit/hf-kit.js` | template mechanics (vars, time, progress, reveal, draw, fit, tokens) |
| `S/scripts/manifest.py` | `template.json` loading and field validation |
| `S/scripts/designs.py` | config, design lookup, variants, design hash |
| `S/scripts/stage.py` | build a temporary HyperFrames project for one render |
| `S/scripts/render.py` | render a staged project to mov/mp4/png, poster frame |
| `S/scripts/archive.py` | render id, archive store/lookup, derived index |
| `S/scripts/deliver.py` | numbered files, `results.json`, `kaynaklar.txt` |
| `S/scripts/review.py` | samples, contact sheet, showcase page |
| `S/scripts/scaffold.py` | `--new-design`, `--new-template` |
| `S/scripts/preview.py` | stage + HyperFrames preview |
| `S/scripts/make_graphic.py` | CLI entry |
| `S/scaffold/` | blank design skeleton and blank template skeleton |
| `S/references/design-workflow.md`, `S/references/template-contract.md` | docs Claude reads |
| `S/SKILL.md` | skill entry |
| `S/tests/…` | unit tests (+ `test_live.py`) |
| `graphics/config.json` | active design |
| `graphics/designs/starter/…` | starter tokens, variants, fonts, assets, `design.md`, `reference/` |
| `graphics/templates/starter/{chapter-title,number,bar-chart,name-line,watermark}/` | starter templates |
| `scripts/fetch-assets.sh` | also ignore `./graphics/*` under assets |
| `.gitignore` | `S/node_modules/` |

---

### Task 1: Toolchain, runner and kit

**Files:**
- Create: `S/package.json`, `S/package-lock.json`, `S/scripts/hf.py`, `S/scripts/setup.py`, `S/kit/hf-kit.js`
- Create: `S/tests/helpers.py`, `S/tests/test_hf.py`, `S/tests/test_setup.py`, `S/tests/test_live.py`, `S/tests/fixtures/smoke/index.html`
- Modify: `.gitignore` (add `/.claude/skills/making-graphics/node_modules/`)

**Interfaces:**
- Produces:
  - `hf.SKILL_DIR: Path`, `hf.REPO_ROOT: Path`
  - `hf.hf_env(base: dict) -> dict`: a copy plus both telemetry vars
  - `hf.hf_cmd(*args: str) -> list[str]`: `[S/node_modules/.bin/hyperframes, *args]`
  - `hf.run(cmd: list[str], cwd: Path, runner=subprocess.run) -> subprocess.CompletedProcess`: always passes `hf_env(os.environ)`, `capture_output=True`, `text=True`
  - `class hf.ToolError(Exception)`: its message is Turkish
- Kit API (`window.kit`), for later templates:
  - `vars()`, `duration()` (seconds), `fps()`, `onFrame(fn)` (fn(t) on every `hf-seek` and once at t=0)
  - `progress(t, start, dur, easeName) -> 0..1`
  - `token(name) -> string`, `tokenNum(name) -> number`
  - `reveal(el, p)`: left-to-right clip with overhang so the last glyph never clips
  - `draw(pathEl, p)`: stroke draw-on
  - `fit(el, maxWidthPx)`: uses `window.__hyperframes.fitTextFontSize`
  - Easing names are provided (`linear`, `in-out-cubic`, `out-cubic`, `out-quint`); templates pick one via a token such as `--motion-ease`.

- [ ] **Step 1: Pin HyperFrames.** In `S/`, create `package.json` (`"private": true`, `"dependencies": {"hyperframes": "<exact version>"}`, no caret), then run `npm install --ignore-scripts=false` once to produce the lock. Run: `cd S && npm ci && HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 npx hyperframes --version`. Expected: the pinned version.
- [ ] **Step 2: Write failing tests** in `test_hf.py`:
  - `test_env_sets_telemetry_off`: `hf_env({})` contains `HYPERFRAMES_NO_TELEMETRY="1"` and `DO_NOT_TRACK="1"`.
  - `test_cmd_uses_local_binary`: `hf_cmd("render")[0].endswith("node_modules/.bin/hyperframes")`.
  - `test_run_passes_env`: a fake runner records `env`, which carries both vars.

  And in `test_setup.py`, using `setup.check(which=fake_which, run=fake_run) -> list[str]`, which returns Turkish problem lines:
  - `test_setup_reports_missing_ffmpeg`: with `ffmpeg` missing, one line contains `dnf install ffmpeg` and `RPM Fusion`, and no line mentions sudo being run.
  - `test_setup_reports_missing_node`: the message names Node 22.
  - `test_setup_ok`: everything present returns `[]`.
- [ ] **Step 3: Run** the test command. Expected: FAIL (module not found).
- [ ] **Step 4: Implement `hf.py`, and `setup.py` with `check(which, run) -> list[str]` and `main() -> int`.** `main` runs `check`, then `npm ci` (only when `node_modules` is missing), `hyperframes browser ensure`, `hyperframes telemetry disable` and `hyperframes doctor`, printing doctor's failures in Turkish. It exits 1 if any problem remains.
- [ ] **Step 5: Run** the test command. Expected: PASS.
- [ ] **Step 6: Kit and live smoke test.**
  - Write `S/kit/hf-kit.js` with the API above.
  - Write `fixtures/smoke/index.html`, a 1920×1080 root with `data-duration="1"`. It loads `kit/hf-kit.js` (the test copies the kit beside it) and fades a box in with `kit.onFrame`, using `kit.progress`.
  - `test_live.py::test_live_smoke_render` (skipped unless `GRAPHICS_LIVE=1`) renders it with `--fps 25 --format mov` into a temp dir. ffprobe must report 25 frames, codec `prores`, `pix_fmt` containing `a` (alpha), and 1920×1080.
  - `test_live_smoke_frames_differ`: frames 0 and 24, extracted with ffmpeg, differ, which proves `hf-seek` drives the animation.
- [ ] **Step 7: Run** `python3 S/scripts/setup.py`, then `GRAPHICS_LIVE=1` plus the test command. Expected: setup exits 0, or lists exactly what the user must install. The live tests PASS once FFmpeg is installed. If FFmpeg is missing, stop and ask the user to run `! sudo dnf install ffmpeg` (after RPM Fusion).
- [ ] **Step 8: Commit.**
  ```bash
  git add .gitignore .claude/skills/making-graphics/{package.json,package-lock.json,scripts/hf.py,scripts/setup.py,kit,tests}
  git commit -m "making-graphics: pinned HyperFrames, setup check, runner and template kit"
  ```

### Task 2: Template manifest and field validation

**Files:**
- Create: `S/scripts/manifest.py`, `S/tests/test_manifest.py`, `S/tests/fixtures/templates/demo/template.json`

**Interfaces:**
- Consumes: none
- Produces:
  - `manifest.Template` dataclass with: `name`, `dir: Path`, `description`, `version: int`, `status`, `output: str`, `output_by: dict|None`, `canvas: str|dict`, `vertical: bool`, `frames: dict(default,min,max)`, `fields: list[Field]`.
  - `manifest.Field` with: `name`, `type`, `required`, `max_len`, `help`, `of` (highlight), `values` (enum), `item` (`"text"`|`"pair"`), `numeric`, `min_items`, `max_items`.
  - `manifest.load(dir: Path) -> Template`: raises `ManifestError` (Turkish) on a bad manifest.
  - `manifest.validate(t: Template, raw: dict[str, str|list[str]]) -> dict`: returns normalised values, or raises `FieldError(list[str])` holding every problem at once, in Turkish.
  - `manifest.output_for(t, values) -> str`
  - `manifest.frame_limits(t, fps: int) -> (default, min, max)`

`template.json` shape (pin this in `references/template-contract.md` in Task 11):

```json
{"name": "number", "description": "Tek sayı vurgusu: değer, birim, açıklama", "version": 1, "status": "draft",
 "output": "fullscreen", "output_by": {"field": "state", "map": {"static": "still"}},
 "canvas": "frame", "vertical": true, "frames": {"default": 150, "min": 75, "max": 375},
 "fields": [{"name": "value", "type": "number", "required": true},
            {"name": "explanation", "type": "text", "max_len": 120},
            {"name": "highlight", "type": "highlight", "of": "explanation"},
            {"name": "bars", "type": "list", "item": "pair", "numeric": true, "min_items": 2, "max_items": 8},
            {"name": "source", "type": "source"}]}
```

- `canvas` is `"frame"` or `{"width": W, "height": H}`.
- `frames` limits are written at 25 fps.

- [ ] **Step 1: Write failing tests:**
  - `test_load_reads_fields`: types and defaults (`required` false, `max_len` None).
  - `test_bad_manifest_names_the_key`: a missing `output` raises `ManifestError`, and the message contains `output`.
  - `test_required_missing`: the message contains the field name and `gerekli`.
  - `test_text_over_max_len`: the message contains the limit number.
  - `test_highlight_must_be_substring`: `"çok uzun"` in `"bu çok uzun bir süre"` passes; `"kısa"` fails with a message naming both fields.
  - `test_number_parses_exponent`: `"10^67"` gives `{"base":"10","exp":"67","text":"10^67"}`; `"3,7"` gives `{"base":"3,7","exp":None,...}`; `"abc"` fails.
  - `test_enum_rejects_unknown`: the message lists the allowed values.
  - `test_list_pairs_numeric`: `["Mars=3,7","Dünya=9.8"]` gives `[{"label":"Mars","value":3.7},…]`; `"Mars=x"` fails; 1 item fails when `min_items` is 2; 9 items fail when `max_items` is 8.
  - `test_unknown_field_rejected`: the message lists the template's field names.
  - `test_all_errors_reported_together`: two bad fields give `len(err.args[0]) == 2`.
  - `test_output_by_maps_enum`: `state=static` gives `still`, and any other state gives the template's `output`.
  - `test_frame_limits_scale_with_fps`: limits `150/75/375` at fps 50 give `300/150/750`; at fps 30 they give `180/90/450` (`round`).
- [ ] **Step 2: Run** the test command. Expected: FAIL.
- [ ] **Step 3: Implement** `manifest.py`. Decimal comma: `"3,7"` parses as 3.7. Text is checked for length after `strip()`.
- [ ] **Step 4: Run** the test command. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "making-graphics: template manifest and field validation"`

### Task 3: Designs and staging

**Files:**
- Create: `S/scripts/designs.py`, `S/scripts/stage.py`, `S/tests/test_designs.py`, `S/tests/test_stage.py`, `S/tests/fixtures/designs/demo/{design.json,tokens.css,variants/a.css,fonts/x.woff2,design.md,reference/r.html}`, `S/tests/fixtures/templates/demo/index.html`

**Interfaces:**
- Consumes: `manifest.Template`, `manifest.validate`
- Produces:
  - `designs.Config(root: Path)` with `.design`, read from `graphics/config.json` (`{"design": "starter"}`).
  - `designs.design_dir(root, name) -> Path`: raises Turkish `DesignError` listing the existing designs.
  - `designs.variants(dir) -> list[str]`: stems of `variants/*.css`.
  - `designs.default_variant(dir) -> str|None`: from `design.json` `{"default_variant": "ev"}`.
  - `designs.design_hash(dir) -> str`: sha256 over sorted relative paths and bytes, excluding `design.md` and `reference/`.
  - `designs.template_dir(root, design, name) -> Path` and `designs.templates(root, design) -> list[Template]`.
  - `stage.stage(t: Template, design: Path, variant: str|None, values: dict, vertical: bool, frames: int, fps: int, dest: Path) -> Path`

  The staged layout:
  - `dest/` holds the template files.
  - `dest/design/` holds the design minus `design.md` and `reference/`, plus `design/variant.css` (the chosen variant, or empty).
  - `dest/kit/hf-kit.js`.
  - `dest/vars.json` holds `{name: value}`. Lists and numbers are JSON-encoded strings, and the kit decodes them using the types in `<script id="kit-types" type="application/json">`, which `stage` injects.

  `stage` also rewrites the root element (`[data-composition-id]`, first match) in `dest/index.html`:
  - `data-duration` becomes `frames/fps` (as a decimal string);
  - `data-fps` becomes fps;
  - `data-width`/`data-height` become 1920×1080, or 1080×1920 when vertical, or the fixed canvas;
  - it sets `<html data-composition-variables=…>` generated from the manifest (all `string`, default `""`).

  Templates link only `design/tokens.css`, `design/variant.css` and `kit/hf-kit.js`.

- [ ] **Step 1: Write failing tests:**
  - `test_unknown_design_lists_known`
  - `test_variants_and_default`
  - `test_design_hash_ignores_docs`: editing `design.md` or `reference/r.html` keeps the hash, while editing `tokens.css` changes it.
  - `test_stage_rewrites_root`: frames 125 at fps 25 give `data-duration="5"`; vertical gives width 1080, height 1920.
  - `test_stage_fixed_canvas_ignores_vertical`
  - `test_stage_copies_variant_as_variant_css`, and the case with no variant gives an empty file.
  - `test_stage_declares_variables_from_manifest`: the ids equal the manifest field names.
  - `test_stage_excludes_reference_and_design_md`
  - `test_vars_json_encodes_lists`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `designs.py` and `stage.py`. Edit the root with a regex on the first tag that carries `data-composition-id`, replacing or adding each attribute. Don't use an HTML parser that would reformat the file.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "making-graphics: designs, variants, design hash and render staging"`

### Task 4: Render, archive, delivery and the CLI

**Files:**
- Create: `S/scripts/render.py`, `S/scripts/archive.py`, `S/scripts/deliver.py`, `S/scripts/make_graphic.py`
- Create: `S/tests/test_render.py`, `S/tests/test_archive.py`, `S/tests/test_deliver.py`, `S/tests/test_cli.py`, `S/tests/test_fetch_assets.py`, `S/tests/fakes.py`
- Modify: `scripts/fetch-assets.sh` (the `list_files` exclusion gains `! -path './graphics/*'`, and the comment names it)

**Interfaces:**
- Consumes: everything from Tasks 1 to 3.
- Produces:
  - `render.render(staged: Path, output: str, resolution: str, fixed: bool, vertical: bool, out_file: Path, run=hf.run)`:
    - overlay: `--format mov`;
    - fullscreen: `--format mp4`;
    - still: `--format png-sequence` with the root forced to 1 frame, keeping the single PNG;
    - `--resolution`: `landscape-4k`/`portrait-4k`, or none for 1080p and fixed;
    - plus `--fps`, `--variables-file vars.json`, `--strict-variables` and `-o`.

    It renders into a temp file in the same folder, then `os.replace`. On a non-zero exit it raises `hf.ToolError` carrying the last stderr line, and leaves no file behind.
  - `render.poster(file: Path, frame: int, dest: Path, run)`: ffmpeg grabs one frame as RGBA PNG. The poster frame is `round(frames*0.7)`; a still's poster is the PNG itself.
  - `archive.render_id(**parts) -> str`: the first 16 hex of the sha256 of canonical JSON over template, template_version, design, design_hash, variant, vertical, frames, fps, resolution, output and values.
  - `archive.Archive(root)` with:
    - `.lookup(id) -> Path|None`;
    - `.store(id, vars: dict, file: Path, poster: Path)`, which writes into `<template>/<id>.tmp/` then renames to `<template>/<id>/` (holding `vars.json`, `render.<ext>`, `poster.png`);
    - `.write_index() -> list`, which builds `index.json` from every `vars.json`.
  - `deliver`:
    - `slugify(text) -> str`, the finder's Turkish fold, with fallback `"grafik"`;
    - `load_results(out)`;
    - `add(out, results, code, entry: dict, file: Path) -> dict`: names the file `<code>-<n>.<ext>`, hard-linking or else copying, continues numbering, never overwrites;
    - `save(out, results, notes, now)`: writes `results.json` atomically and rewrites `kaynaklar.txt` from every entry's `sources`, deduplicated.
  - CLI `make_graphic.py`:
    - render: `<template> [--set k=v]... [--fields-file F] [--variant V] [--vertical] [--frames N] [--fps 25] [--resolution 4k|1080p] [--out DIR] [--code C] [--design D] [--fresh]`;
    - other modes: `--batch FILE --out DIR`, `--list [--json]`, `--reindex`;
    - `main(argv, env=os.environ, run=hf.run, now=None) -> int`.
    - Repeating `--set` for a list field appends.
    - A batch row is `{"template", "code"?, "fields": {}, "variant"?, "vertical"?, "frames"?}`.
    - `--list --json` prints `[{"name","description","output","vertical","frames","fields":[{name,type,required,help}]}]` for the active design.
    - `results.json` is `{"created","notes","renders":[{"code","file","template","version","design","variant","vertical","frames","fps","resolution","values","sources","from_archive","archive_id"}]}`.

- [ ] **Step 1: Write failing tests** with `fakes.FakeRun`, which records calls and, for render commands, writes a dummy output file at `-o`:
  - `test_render_args_overlay_4k`: contains `--format mov`, `--resolution landscape-4k`, `--fps 25`, `--strict-variables`.
  - `test_render_vertical_uses_portrait_4k`
  - `test_render_fixed_canvas_has_no_resolution`
  - `test_render_failure_leaves_no_entry`: FakeRun exits 1. `main` returns 1, stderr has one `Hata:` line, and both the archive root and `--out` have no files.
  - `test_render_id_changes_with_each_part`: one assertion per part.
  - `test_archive_reuse`: the second identical call does no render, and `from_archive` is true.
  - `test_fresh_forces_render`
  - `test_design_change_invalidates_archive`: editing the fixture's `tokens.css` between calls makes a second render happen.
  - `test_deliver_numbering_continues`: two runs with code `G1` give `G1-1.mp4` and `G1-2.mp4`, and the first file is unchanged.
  - `test_kaynaklar_dedup`
  - `test_validation_error_exit_2`: Turkish lines on stderr, no render.
  - `test_default_out_dir`: `HOME/Downloads/grafik/<template>-<slug of first text field>/`.
  - `test_list_json_shape`
  - `test_batch_bad_row_does_not_stop_others`: row 1 is an unknown template and row 2 is fine. Exit 0, one render, a note naming row 1.
  - `test_reindex_rebuilds_from_vars`
  - `test_fetch_assets_ignores_graphics`: copy the finder's `test_fetch_assets.py` pattern with `graphics/x/y/render.mov`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the four modules and the `fetch-assets.sh` change.
  - Staging happens in a `tempfile.TemporaryDirectory`.
  - The archive root defaults to `REPO_ROOT/assets/graphics` (`--archive` overrides it for tests).
  - The graphics root defaults to `REPO_ROOT/graphics` (`--root` overrides it for tests).
- [ ] **Step 4: Run** the whole test command. Expected: PASS, including the finder's own suite: `cd .claude/skills/finding-stock-footage/tests && python3 -m unittest -q`.
- [ ] **Step 5: Commit.** `git commit -m "making-graphics: render, archive, delivery and make_graphic.py CLI"`

### Task 5: Starter design, chapter-title, samples and contact sheet

**Files:**
- Create:
  - `graphics/config.json` (`{"design": "starter"}`)
  - `graphics/designs/starter/{design.json,tokens.css,design.md}`
  - `graphics/designs/starter/variants/{ev,uzay,diyalog,kurgu,muhendislik,notlar}.css`
  - `graphics/designs/starter/fonts/` (Fraunces variable roman + italic, JetBrains Mono, Caveat, each with `OFL.txt`)
  - `graphics/designs/starter/assets/{logo.svg,motifs/*.svg}`
- Create: `graphics/templates/starter/chapter-title/{index.html,template.json,samples.json}`
- Create: `S/scripts/review.py`, `S/tests/test_review.py`
- Modify:
  - `graphics/designs/starter/reference/*.html`: make them standalone documents, using the companion frame's CSS inlined, so they open by double-click.
  - `S/scripts/make_graphic.py`: add `--samples <template> [--out DIR]`.

**Interfaces:**
- Consumes: the CLI and the kit.
- Produces:
  - `make_graphic.render_row(row: dict, out: Path, fresh: bool, ...) -> dict`: the one-row render path that Task 4's CLI uses, returning the `results.json` entry. It is factored out so the review code can call it.
  - `review.samples(t, rows, out, render_fn) -> list[Path]`, where `render_fn` is `render_row` with options bound: renders every `samples.json` row (rows are batch rows without `template`), always `--fresh`.
  - `review.contact_sheet(posters: list[Path], dest: Path, run)`: an ffmpeg `tile` of 320 px-wide posters, scaling with `force_original_aspect_ratio=decrease` before the pad, on a dark grey background so alpha posters stay visible.

**Starter content:** the values in the spec's "The starter example" section.
- `tokens.css` defines `@font-face` with relative `fonts/` paths.
- Colours: `--ink #ECE6DA`, `--hl #FFB46A`, `--hl-fill rgba(255,154,60,.45)`, body `#B9B3A8`, label `#8F8A80`, source `#6E6A62`, page `#000`, dots `#3a3a3a` at 2.5cqw with a radial fade.
- Motion: `--motion-rise 1.2cqw`, `--motion-stagger .15s`, `--motion-in .8s`, `--motion-ease out-cubic`, `--motion-out .3s`.
- Each variant sets `--series`, `--tick` and `--motif` (an url to `assets/motifs/<x>.svg` or `none`), and `muhendislik` also sets `--page: graph`.
- `design.md` opens with: "Bu bir başlangıç örneğidir (starter example), kanalın onaylı tasarımı değildir." It then records each decision from the 2026-11-13 brainstorm and the rejected ideas.

chapter-title manifest:
- `output fullscreen`, `canvas frame`, `vertical true`, frames `100/50/250`;
- fields `label` (text 40), `line1` (text 60, required), `line2` (text 60).

`samples.json` covers every variant, vertical, and the longest Turkish text (`"Güneş Sistemi'nin İlk Işığı Ğüşçö"`-style, at the full max_len).

- [ ] **Step 1: Write failing tests:** `test_samples_renders_every_row_fresh`, and `test_contact_sheet_command` (the arguments contain `tile=` and `force_original_aspect_ratio=decrease`).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `review.py` and `--samples`. Then build the starter design and the chapter-title template, matching `reference/showcase.html`'s chapter card and using tokens only. Grep check: `grep -nE '#[0-9a-fA-F]{3,6}|rgba?\(' graphics/templates/starter/chapter-title/index.html` prints nothing.
- [ ] **Step 4: Run** the test command, then `GRAPHICS_LIVE=1`. Add `test_live_chapter_title`: one 1080p render, where ffprobe shows 100 frames, h264 and 1920×1080. Expected: PASS.
- [ ] **Step 5: Render the samples:** `python3 S/scripts/make_graphic.py --samples chapter-title --out ~/Downloads/grafik/_samples/chapter-title`. Expected: one file per row plus `contact.png`. Read `contact.png` and check for clipped glyphs before showing it.
- [ ] **Step 6: USER REVIEW GATE.** Show the user the folder and the contact sheet, and confirm the reference pages open standalone. Apply the requested changes (bump `version` when `status` is `final`). Mark `final` only when the user says so.
- [ ] **Step 7: Commit.** `git commit -m "making-graphics: starter design, chapter-title template, samples and contact sheet"`. Stage the fonts and licences, and the `reference/` pages.

### Task 6: Starter template `number`

**Files:** `graphics/templates/starter/number/{index.html,template.json,samples.json}`, `S/tests/test_live.py`

Manifest:
- `output fullscreen`, `vertical true`, frames `150/75/375`;
- fields:
  - `value` (number, required)
  - `unit` (text 20)
  - `explanation` (text 140)
  - `highlight` (highlight of explanation)
  - `hand` (text 40)
  - `source` (source)

The look follows showcase.html's number card:
- an exponent set as a superscript;
- the highlight sweeps on after the text;
- the hand note is revealed with `kit.reveal`.

- [ ] **Step 1: Write the failing live test** `test_live_number_sources`: a render with `source "NASA, 2024"` produces `kaynaklar.txt == "NASA, 2024\n"` and 150 frames. Run it. Expected: FAIL (the template is missing).
- [ ] **Step 2: Build the template.** It uses tokens only (same grep check as Task 5).
- [ ] **Step 3: Run** with `GRAPHICS_LIVE=1`. Expected: PASS.
- [ ] **Step 4: Render the samples** and the contact sheet. Check the last glyph of the hand note in the poster.
- [ ] **Step 5: USER REVIEW GATE.** As in Task 5.
- [ ] **Step 6: Commit.** `git commit -m "making-graphics: starter number template"`

### Task 7: Starter template `bar-chart`

**Files:** `graphics/templates/starter/bar-chart/{index.html,template.json,samples.json}`, `S/tests/test_live.py`

Manifest:
- `output fullscreen`, `vertical false`, frames `175/100/375`;
- fields:
  - `label` (text 40)
  - `line1` (text 60, required)
  - `line2` (text 60)
  - `bars` (list pair numeric, 2 to 8, label max 24)
  - `unit` (text 12)
  - `source` (source)
  - `hand` (text 40)
  - `hand_bar` (text, must equal one bar label; validated by an extra `"one_of_labels": "bars"` key; add the test `test_one_of_labels` to `test_manifest.py` and support it in `manifest.py`)

Bars scale to the maximum value. Values are printed with a decimal comma.

- [ ] **Step 1: Write the failing test** `test_one_of_labels` (unit). Run it. Expected: FAIL.
- [ ] **Step 2: Implement** it in `manifest.py`. Run it. Expected: PASS.
- [ ] **Step 3: Write `test_live_bar_chart_8_bars`**, which renders the 8-bar sample successfully. Run it. Expected: FAIL.
- [ ] **Step 4: Build the template** (tokens only). Run it. Expected: PASS.
- [ ] **Step 5: Render the samples**, including the 2-bar and 8-bar rows, plus the contact sheet.
- [ ] **Step 6: USER REVIEW GATE.**
- [ ] **Step 7: Commit.** `git commit -m "making-graphics: starter bar-chart template"`

### Task 8: Starter template `name-line`

**Files:** `graphics/templates/starter/name-line/{index.html,template.json,samples.json}`, `S/tests/test_live.py`

Manifest:
- `output overlay`, `vertical true`, frames `125/75/250`;
- fields `name` (text 40, required) and `role` (text 60).

The background is transparent, with no page dots.

- [ ] **Step 1: Write the failing live test** `test_live_name_line_alpha`: ProRes with an alpha `pix_fmt`, and the alpha of the top-left pixel of the poster is 0 (PNG read via ffmpeg `-vf alphaextract`). Run it. Expected: FAIL.
- [ ] **Step 2: Build the template** (tokens only). Run it. Expected: PASS.
- [ ] **Step 3: Render the samples** and the contact sheet.
- [ ] **Step 4: USER REVIEW GATE.**
- [ ] **Step 5: Commit.** `git commit -m "making-graphics: starter name-line overlay template"`

### Task 9: Starter template `watermark` (the living logo)

**Files:** `graphics/templates/starter/watermark/{index.html,template.json,samples.json}`, `graphics/designs/starter/design.md` (watermark section), `S/tests/test_live.py`

**Source of truth:** `graphics/designs/starter/reference/watermark-v9.html`. Port its logic faithfully into a frame-driven `kit.onFrame` function:
- per-letter spans positioned via canvas `measureText`;
- each frame applies curvature `c` from 0 to 1 with `reff = r/c` and `translateZ(r - reff) rotateY(m/reff) translateZ(reff)` (flat `translateX(m) translateZ(r)` at c=0);
- the ring rotates by `rotateY(phi)`;
- the grow scale goes up to 1.16;
- the globe SVG sits inside the preserve-3d world at `translateZ(0)`, so letters behind it are hidden;
- back-side opacity is 0.6 in colour and 0.3 in wireframe;
- the revolve timeline as fractions of its length: 0 to .06 static, .06 to .20 grow and bend, .20 to .84 revolve (in-out), .84 to .96 unbend and shrink;
- the star: a straight path from far outside, fading in, crossing, and fading out far outside, with the trail gradient and the head glow from v9.

All colours come from tokens: the logo green, petrol, ink and star colours are starter tokens. The wireframe stroke widths are tokens too.

Manifest:
- `output overlay`, `output_by {"field":"state","map":{"static":"still"}}`;
- canvas fixed, wide enough for the star path with the globe about 1600 px across, the same for every state (builder sets the exact W×H, recorded in `design.md`);
- `vertical false`;
- fields: `state` (enum `static, wireframe, revolve, revolve-wireframe, star, star-noname`, required);
- frames per state through samples. Defaults: revolve 150, star 100, wireframe 100 (min 25, max 500). The user confirms the lengths in review.

- [ ] **Step 1: Write the failing live tests:**
  - `test_live_watermark_static_png`: a PNG of the canvas size, with an alpha channel.
  - `test_live_watermark_states_same_canvas`: every animated state gives the same W×H.
  - `test_live_watermark_chains`: the first and last frames of `revolve` and of `star` match the static PNG, with a mean absolute difference under 2/255 via ffmpeg `blend=difference` + `signalstats`.

  Run them. Expected: FAIL.
- [ ] **Step 2: Build the template** from v9. Run the tests. Expected: PASS.
- [ ] **Step 3: Render the samples** (all six states) and the contact sheet. Also render `revolve` at 1080p-equivalent speed to check for stutter: the frames must step evenly.
- [ ] **Step 4: Update** the watermark section of `design.md`: how each state behaves, the canvas size, the lengths, and what was rejected (extruded letters, the elliptical star path).
- [ ] **Step 5: USER REVIEW GATE.** Compare it side by side with `reference/watermark-v9.html`: it must match the prototype the user approved.
- [ ] **Step 6: Commit.** `git commit -m "making-graphics: starter watermark template, living logo states"`

### Task 10: Design-workflow tooling

**Files:**
- Create: `S/scripts/scaffold.py`, `S/scripts/preview.py`, `S/scaffold/design/{design.json,tokens.css,design.md,variants/.keep}`, `S/scaffold/template/{index.html,template.json,samples.json}`
- Create: `S/tests/test_scaffold.py`, `S/tests/test_preview.py`, `S/tests/test_showcase.py`
- Modify: `S/scripts/make_graphic.py` (`--new-design NAME [--from D]`, `--new-template NAME [--from T]`, `--preview T [--variant V] [--vertical]`, `--showcase [--design D] [--out DIR]`), `S/scripts/review.py` (`showcase`)

**Interfaces:**
- Produces:
  - `scaffold.new_design(root, name, from_=None) -> Path`. The blank skeleton `tokens.css` lists every token name the starter uses, with empty values and a comment per group. It refuses to overwrite an existing design.
  - `scaffold.new_template(root, design, name, from_=None) -> Path`. The blank skeleton is a minimal composition wired to `design/tokens.css`, `design/variant.css` and the kit, with one `text` field and `status draft`, `version 1`.
  - `preview.preview(t, design, variant, vertical, port=None, run=hf.run) -> str`: stages into `assets/graphics/_preview/<template>/` (persistent while previewing), runs `hyperframes preview --background --port P`, checks the URL answers HTTP 200, and returns the URL with its `#project/` hash. `--preview --stop` stops it.
  - `review.showcase(root, design, out, render_fn) -> Path`: renders the first `samples.json` row of each template in 1080p, archive reuse allowed, and writes `out/index.html`. That page plays each clip with a caption of template name, description and fields. Its heading says the design name, plus "başlangıç örneği" when the design is `starter`. Visual values come from the design's `tokens.css` (linked).

- [ ] **Step 1: Write failing tests:**
  - `test_new_design_blank_lists_all_starter_tokens`: every `--x:` name in the starter `tokens.css` appears in the blank skeleton.
  - `test_new_design_refuses_existing`
  - `test_new_design_from_copies`
  - `test_new_template_is_renderable`: it loads through `manifest.load` and stages without error.
  - `test_preview_command`: FakeRun sees `preview --background --port`.
  - `test_showcase_lists_every_template`
  - `test_showcase_marks_starter`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** them. Check the HyperFrames preview against the pinned version: if it can't serve a staged project, fall back to `hyperframes play` and record the ruling.
- [ ] **Step 4: Run** the suite, and with `GRAPHICS_LIVE=1` run `test_live_new_template_renders` (a scaffolded template renders 1 s). Expected: PASS.
- [ ] **Step 5: Build the starter showcase** into `~/Downloads/grafik/_showcase/`, open it, and show the user.
- [ ] **Step 6: Commit.** `git commit -m "making-graphics: new design/template scaffolds, preview and showcase"`

### Task 11: SKILL.md, references and a live editor session

**Files:**
- Create: `S/SKILL.md`, `S/references/design-workflow.md`, `S/references/template-contract.md`
- Modify: memory note (the project file), only to record the final state.

**SKILL.md:**
- Frontmatter: `name: making-graphics`. The description says when to use it and summarises no workflow: "Use when an editor wants a graphic, title card, number callout, chart, name line, logo/watermark or other motion graphic for a video or short ("bölüm başlığı grafiği", "isim altyazısı", "10^67 yıl vurgusu"), when the B-roll skill needs GRAFİK rows rendered, or when an editor wants to create or change the channel's graphic design or templates with HyperFrames."
- Body, in the finder's style:
  1. **Render path:** run `--list --json`, pick a template, then render with `--set`, and report the folder, file, `kaynaklar.txt` and warnings. If no template fits, say so and offer the design workflow; never write HTML for a render.
  2. **Design path:** read `references/design-workflow.md` and follow it. The editor makes every design decision.
  3. **For the B-roll skill:** the `--batch` row shape and the `results.json` shape.
  4. **Setup:** `python3 S/scripts/setup.py`.
  5. The starter is an example, not the channel design.

**`design-workflow.md`:**
- Explore in the brainstorm visual companion, in the editor's words.
- Record the rulings in the design's `design.md`.
- Scaffold, fill tokens, scaffold templates, then preview, samples and showcase.
- Mark `final` only on the editor's word.
- Rules: no visual values outside tokens; Turkish glyph check; reveal overhang.

**`template-contract.md`:** the manifest schema and field types (from Task 2, plus `one_of_labels`), the staged layout, the kit API, the `hf-seek` timing rules, and how `output_by` and fixed canvases work.

- [ ] **Step 1: Baseline (RED).** Dispatch a fresh subagent *without* the skill, giving it: "Bir sayı vurgusu grafiği yap: 10^67 yıl, kara deliklerin buharlaşma süresi, kaynak NASA". Record what it does; it will likely write ad-hoc HTML or give up.
- [ ] **Step 2: Write** SKILL.md and the two references.
- [ ] **Step 3: GREEN.** Run the same prompt with the skill. It must call `make_graphic.py number --set …` and report `kaynaklar.txt`, with no HTML written. A second prompt, "Uzay Gündemi için yeni bir 'alıntı' şablonu tasarlayalım", must start the design workflow and ask the editor rather than decide the design itself. Fix any loophole and rerun.
- [ ] **Step 4: Run** the full suite and `GRAPHICS_LIVE=1`. Expected: PASS. Also run the finder's suite. Expected: PASS.
- [ ] **Step 5: USER REVIEW GATE.** The live editor session: the user (or Claude acting on the user's prompts) creates a new template from scratch with the workflow and renders it.
- [ ] **Step 6: Commit.** `git commit -m "making-graphics: SKILL.md and design workflow references"`

---

## Deviations from the spec's order of work (rulings)

- `--samples` and the contact sheet move into Task 5, because every template's review gate needs them. `--new-design`, `--new-template`, `--preview` and `--showcase` stay in Task 10.
- The animation timing uses HyperFrames' `hf-seek` event through the kit instead of GSAP. That way nothing has to be vendored, and the per-frame watermark port maps one-to-one. Task 1's live test proves it.
- Variables can't change the root's `data-duration` in HyperFrames, so `stage` rewrites the root attributes in a temporary copy per render. Templates never hold a length.
