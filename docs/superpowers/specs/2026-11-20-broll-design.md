# B-roll skill: design

**Date:** 2026-11-20
**Status:** draft, awaiting approval
**Builds on:** the script template and reader (`2026-11-11-script-template-design.md`), the stock finder (`2026-11-13-stock-finder-design.md`), making-graphics (`.claude/skills/making-graphics`), the A-roll rough cutter (`.claude/skills/rough-cutting-a-roll`).

## Why
B-roll is the biggest time sink in editing. The writer already says, row by row, what should be on screen under which words (`script.json`). The stock finder and making-graphics can fetch or render a single visual. What's missing is the step that does this for a whole episode and places the results in Resolve under the right words, so the editor starts from a filled timeline instead of an empty one. Shorts will later reuse the B-roll this skill places, which is why it comes before the shorts project.

## Goals
- For every non-KAMERA row of a **frozen** A-roll chapter: find or create the B-roll and place it over the frames where the row's words are spoken.
- Put it on **new** B-roll timelines; the frozen A-roll is never modified.
- Allow **rebuilding** as often as needed without losing anything the editor changed in Resolve.
- Make every gap visible in place: rows the skill can't fill yet get a placeholder.
- Deterministic scripts do the work. Claude makes one judgment step (turning row descriptions into requests) and otherwise only calls the tools.

## Non-goals
- **Anything about the A-roll.** The deviation report (off-script spans, missed retakes, rows longer than estimated, measured speaker pace) is an A-roll project, to be designed separately. The B-roll skill never cuts, reports on or re-times A-roll.
- Unfrozen chapters.
- **YZ (Adobe Firefly).** The tag is dropped from the vocabulary (see Template change).
- **ARŞİV search.** The Dropbox archive isn't indexed; ARŞİV rows get placeholders.
- Designing graphics or templates. GRAFİK/YAZI rows with no fitting template get placeholders; the design path stays in making-graphics, run by an editor.
- Shorts, vertical output, music, sound design, transitions, zooms.

## Anti-goals (a failure even if it works)
- **A frozen chapter timeline changes** in any way: items, markers, track state.
- **An editor's change in Resolve is lost** on a rebuild.
- **The skill picks clips or invents graphics by judgment.** Candidates come from the finder's ranking; graphics come only from existing templates.
- **A gap is silent.** Every row that isn't filled must be visible on the timeline and in the printed summary.

## Constraints
- All positions in **integer frames, half-open `[start, end)`**, never seconds (the rough cutter's rule).
- Resolve Studio 21.2+ on Linux, driven through its scripting API via `rv.sh`, like `chapters.py`.
- Episode files live in `episodes/<slug>/` (gitignored); the frozen chapters are listed in `episode.json` `"frozen"`, their timelines are named by `chapters.py` and mapped in `timelines/<timeline>.json` (`flat: [rec_frame, clip, src_start, src_end]`).
- Stock goes only through `find_stock.py --batch`, graphics only through `make_graphic.py --batch`; both never replace delivered files.

## Approaches considered
1. **Fully deterministic scripts.** Rejected: turning "AB sınırında bir tır" into English stock keywords, or a bar-chart description into a template with fields, needs judgment. The stock finder already leaves keyword translation to Claude.
2. **Claude places clips through the Resolve MCP.** Rejected: not reproducible, and it breaks the principle that scripts do the work and the LLM only calls tools.
3. **Hybrid, one judgment step (chosen by the user).** A `broll.py` script with steps. Claude writes one reviewable file of requests; everything else is deterministic.

## Decisions

### Timelines (user)
- Each frozen chapter gets its own B-roll timeline, `<prefix> chN <title> B-roll`. V1 holds the frozen chapter timeline as **one nested item**, the way `chapters.py master` already nests frozen chapters. The skill never opens or edits the frozen chapter timeline itself.
- The first `build` creates the B-roll timeline; every later `build` **updates it in place** (user). It adds, moves and removes only its own items that the editor hasn't touched. Everything else on the timeline (items the editor changed or added, their transforms, crops, opacity, speed, colour, the editor's markers, extra video and audio tracks) is never touched.
- Tracks: **V2** full-screen B-roll: STOK, KAYNAK screenshots, ARŞİV placeholders and **full-screen graphics**. Templates whose `template.json` says `"output": "fullscreen"` (`bar-chart`, `number`, `chapter-title` today) are rendered with `--background` as `.mp4` on the design's page and placed like footage (user: graphs are shown like B-roll, with background). **V3** true overlays: transparent `.mov` graphics such as `name-line`, and YAZI. `requests.json` may override this per row (`"background": false`) to put a full-screen template on V3 as an overlay. A two-tag row such as `[STOK, YAZI]` fills both tracks over the same range. *(Our call)* B-roll audio is not placed; stock clips go in video-only.
- *(Our call)* `broll.py freeze EP N` signs off a chapter's B-roll timeline: it is never rebuilt again (`"broll_frozen"` in `episode.json`). `broll.py master EP` builds `<prefix> B-roll`, nesting each chapter's B-roll timeline in order (or the frozen A-roll chapter where none exists yet). This is the timeline shorts will draw from.

### The editor's changes survive rebuilds (user: read-back)
- `episodes/<ep>/broll/plan.json` is the truth. One entry per placed item: row key, chapter, track, `[start, end)` on the B-roll timeline, the file, its source `[in, out)`, the candidate code, and `editor: true|false`.
- `readback` runs before every `build`. It reads V2/V3 of the existing B-roll timeline and compares with the last build:
  - an item that was moved, trimmed, swapped for another file, or changed in any other way the API can see (transform, crop, opacity, speed, colour) is written into the plan with `editor: true`, and `build` leaves that timeline item alone;
  - an item that was deleted becomes an `editor: true` entry with no file: "nothing here", never rebuilt;
  - an item the editor added that the skill didn't place is kept as an `editor: true` entry with no row.
- `build` never changes an `editor: true` entry. Everything else is recomputed.
- If the script changes later, rows are matched by their key (`script.json` row `key`, based on SES text). An editor entry whose row no longer exists is kept and flagged in the summary; it is never deleted or guessed.

### Rows → requests (the judgment step)
- `broll.py requests EP` lists the non-KAMERA rows of frozen chapters that have no request yet. Claude writes one entry per row into `broll/requests.json`:
  - **STOK:** 2-4 English keywords, as the stock finder asks.
  - **GRAFİK / YAZI:** a template from `make_graphic.py --list --json` and its fields, **only** when one fits and the cell carries the data; otherwise `{"placeholder": "no template", "need": "<one line: what kind of template would fit>"}`. Never invented data.
  - **KAYNAK:** the link from the row (`links[]`).
  - **ARŞİV:** placeholder.
- The file is plain JSON. An editor may correct it; existing entries are never overwritten by the step. Deleting an entry makes it pending again.

### Alignment: row → frames
- `align` turns each row into `[start, end)` on the frozen chapter: the row's SES words are matched, in order, to the transcript words that survive in the chapter. *(Our call, from the builder check)* The chapter's layout (clip, source in/out, record position of every piece) is read **live and read-only** from the frozen chapter timeline in Resolve, not from `timelines/<chapter>.json`, which can be stale if the chapter was hand-edited before freezing. Words come from `transcripts/*-wav-tr.json` + `offset_f`.
- *(Our call)* A row covers from its first matched word to the start of the next row's first word, so B-roll doesn't flash back to the presenter between rows. It ends at its own last word when the next words belong to no row (off-script) or to a KAMERA row. Off-script words are therefore never covered.
- A row that can't be found in the chapter (cut, or not spoken) is listed in the summary and not placed.
- The A-roll is not judged: alignment only answers "where are these words".

### Fetch
- `fetch` runs after `align` (graphics need the row's length) and only for requests without a delivered result:
  - STOK → `find_stock.py --batch … --out broll/stok/`. *(Our call)* A row longer than 7 s asks for more candidates (about one per 5 s, min 3).
  - GRAFİK/YAZI → `make_graphic.py --batch … --out broll/grafik/` with `frames` = the row's length, clamped to the template's allowed range. When the row is **longer than the template's maximum** (R012: ~17 s, `bar-chart` max 15 s), the graphic renders at the maximum and `build` **holds its last frame** for the rest of the row (user). A row shorter than the minimum renders at the minimum and is trimmed.
  - KAYNAK → a screenshot of the link at 1920×1080 with the Chrome that HyperFrames installs, `broll/kaynak/<code>.png`. A failed load or an obviously blocked page (paywall, cookie wall) is reported; the row gets a placeholder carrying the link.
- Codes follow the existing scheme (R12-1, G12 …) with the row number.

### Build
- Candidate 1 of each STOK row is placed. If it is shorter than the row, the next candidate follows it until the row is full; the last one is trimmed. *(Our call)* Clips start at their source frame 0.
- Unused candidates go into a media-pool bin per row (`B-roll/<chapter>/<row>`). **Take Selector** is tested first in the build; if it works in 21.2, candidates become takes of the placed item instead.
- **Placeholders** *(our call)*: a still on the row's track with the row id, the tag and the writer's description, plus a ranged **Lavender** marker over the row with the same text. Placeholders are rebuilt like everything else, and an editor may delete or replace them (read-back keeps that).
- `broll/kaynaklar.txt` *(our call)*: the credits of the clips and graphics actually on the timeline after the build, merged from the tools' own `kaynaklar.txt`, ready for the video description.
- The printed summary: rows placed, rows with placeholders by reason (no template + the `need` line, ARŞİV, KAYNAK failed), rows not found in the chapter, editor entries whose row disappeared. It also prints the "templates needed" list collected from the `need` lines, so an editor can take it to the design path; a later `requests`/`fetch`/`build` then fills those rows.

### Tags in the first version (user)
| Tag | Handling |
|---|---|
| STOK | stock finder |
| GRAFİK | making-graphics when a template fits; placeholder + "templates needed" otherwise |
| YAZI | making-graphics once a text template exists; placeholder until then |
| KAYNAK | headless screenshot of the link |
| ARŞİV | placeholder |
| YZ | dropped |

### Template change: drop YZ (user)
- `templates/script/` (reader rules, Kılavuz text, template build): YZ is no longer a tag. A `[YZ]` cell then gets "bilinmeyen TÜR".
- The user pastes the updated Kılavuz into the master Google Doc.

### Packaging *(our call)*
- Project skill `.claude/skills/placing-b-roll/` with `SKILL.md`; scripts in its `scripts/`. Resolve steps (`readback`, `build`, `freeze`, `master`) run through the rough cutter's `rv.sh`; the others with plain `python3`.
- It reuses `episode.py` from the rough cutter (imported, not copied).
- Offline tests for requests bookkeeping, alignment, fill/trim, read-back diffing and plan merging, using COP31 data; Resolve steps verified live.

## Acceptance
On a **copy** of COP31 (`episodes/cop31-broll`, own timeline prefix, so the real episode's frozen state is never touched) with at least chapters 3 and 4 frozen:
- R012 (two bars) renders through `bar-chart` with background, sits on V2 over R012's words, and holds its last frame to the row's end; R015/R023 get stock on V2 and a YAZI placeholder on V3; the other GRAFİK rows get placeholders, and the summary lists the templates they need.
- The frozen chapter timelines are unchanged after any number of builds (same items and markers; `timelines/<chapter>.json` untouched).
- The editor moves one clip, trims another, zooms a third, deletes a fourth, adds a clip of their own on V2 and a marker; after `readback` + `build` all of it is still there, and every untouched row is updated.
- `broll/kaynaklar.txt` lists exactly the sources on the timeline.

## Left to the builder
- How read-back identifies the skill's own items (Resolve unique ids vs. name + position), how it detects a swap or a property change, and how the last frame is held (freeze frame, still export, or speed change).
- The alignment algorithm, within "in order, row words to surviving transcript words".
- How the placeholder still is made, and its look.
- Exact JSON field names, summary wording, CLI flags.
