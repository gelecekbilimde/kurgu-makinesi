# Shorts from long-form: design

**Date:** 2026-11-21
**Status:** approved
**Builds on:** the A-roll rough cutter (`.claude/skills/rough-cutting-a-roll`), the B-roll skill (`2026-11-20-broll-design.md`), making-graphics (`.claude/skills/making-graphics`).

## Why
Phase 2 of the channel plan is a daily vertical short. Cutting them by hand from each long-form episode costs an editor as much as a long-form chapter. Most of the work is mechanical once someone has decided which passage is worth a short: cut the passage, reframe the speaker, carry the B-roll over, add captions, the hook and the end card. This project automates that and leaves the editor a ready vertical timeline to review in Resolve, the same way the rough cutter and the B-roll skill do.

## Goals
- From the **signed-off** chapters of an episode (A-roll frozen and B-roll frozen), propose 5-8 short candidates and build each as a vertical Resolve timeline.
- Each short: a ~3 s teaser lifted from the middle of the passage plays first, then the passage (30-45 s, stitched from any parts of the signed-off chapters), then one end card.
- Reuse the long-form B-roll automatically, exactly as the editor signed it off.
- Rebuild as often as needed without losing the editor's changes.

## Non-goals
- **Standalone shorts** (shot or written for the short format). Later project.
- Rendering, uploading, titles/descriptions for the platforms, thumbnails.
- Chapters whose B-roll isn't signed off (`broll_frozen` in `episode.json`), and anything about changing the long-form.
- New graphic designs. The teaser caption, end card (and optional header) are templates editors make with making-graphics; until they exist, the short gets placeholders and the summary lists the templates needed, as in the B-roll skill.
- Music, sound design, transitions, zooms or punch-ins beyond the one fixed face crop.

## Anti-goals (a failure even if it works)
- **Any long-form timeline changes:** frozen A-roll chapters, chapter B-roll timelines, the masters.
- **A short shows B-roll that differs from the signed-off chapter** under the same words (other than the vertical crop/re-render).
- **An editor's change to a short is lost** on a rebuild, including caption text fixes.
- **A cut clips a word** or leaves a breath/pause at a join (the rough cutter's rules hold at every piece boundary).
- **The skill decides beyond ranking:** Claude's judgment is limited to choosing and ranking passages and teaser lines; everything else is deterministic.

## Constraints
- Integer frames, half-open `[start, end)`, `"units": "frames"` in every file. Episode fps (25 for COP31).
- Resolve Studio 21.2+ on Linux through `rv.sh`; episode files in `episodes/<slug>/` (gitignored); vertical timeline 1080×1920.
- Graphics only through `make_graphic.py`; nothing invented outside templates.
- The rough cutter's reviewer preferences: no breaths/empty space, word endings never clipped, flag rather than risk an automatic cut; ranged Yellow markers are the editor's, the engine's suggestions are Fuchsia.

## Approaches considered
1. **Render the whole short outside Resolve** (ffmpeg/HyperFrames). Rejected: the user chose a vertical Resolve timeline as the output, so the editor can review and fix it where they work.
2. **Claude assembles the short through the Resolve MCP.** Rejected for the same reason as in the B-roll skill: not reproducible.
3. **Same shape as the B-roll skill (chosen):** one judgment step writes `shorts/candidates.json` (a subagent ranks passages and teaser lines), deterministic `shorts.py` steps do the rest.

**Captions (user):** regular captions go on Resolve's own **subtitle track**, so an editor fixes a mistranscribed word directly in Resolve. Plain styling is accepted. Only the teaser's captions are rendered (they must sit behind the speaker's head).

## Decisions

### Source: signed-off chapters only (user)
- A chapter is eligible when it is in `"frozen"` and `"broll_frozen"`. Shorts never wait on or change anything else.
- *(Our call)* The chapter B-roll timeline is read **live and read-only** from Resolve (V2, V3 and any editor tracks above V1), not from `broll/plan.json`: the editor may have touched it after the last build. The A-roll layout is read live from the frozen chapter timeline, as the B-roll skill does.

### Candidates (user: subagent ranks; the judgment step)
- `shorts.py candidates EP` prints the eligible chapters' text as sentences with their frame ranges (transcript words + `offset_f`, mapped through the live layout), plus the script rows for context.
- A subagent picks and ranks **5-8 candidates** (proposal accepted) and writes `shorts/candidates.json`: per candidate a stable id, a rank, a working title, one or more **pieces** `{chapter, start, end}` (stitched in the order given, from anywhere in the eligible chapters), a **teaser** span inside the passage (~3 s), a one-line reason and a teaser rating.
- **Length:** the passage is 30-45 s; the teaser and end card don't count (proposal accepted).
- *(Our call)* `shorts.py check EP` snaps every boundary to the nearest gap between words (never inside a word, no breath/pause kept at a join, using the rough cutter's rules), checks lengths and eligibility, and reports what it changed. The file is plain JSON; an editor may edit it, and the step never overwrites an existing candidate.

### Accepting candidates (user: accept first, then build)
- Only candidates the editor accepts are built.
- *(Our call)* The long-form timelines can't carry the review markers (the chapter B-roll timelines are signed off, the master is regenerated). So `shorts.py` keeps its own 16:9 review timeline, `<prefix> short adayları`: the signed-off chapter B-roll timelines nested in order, like the master, with one Fuchsia ranged marker per piece and one per teaser. Each marker carries the candidate's rank, title, reason and teaser rating in its note, and the candidate id in its custom data.
- *(Our call)* The editor **accepts** a candidate by turning any of its markers Green, **rejects** it by deleting its markers or leaving them Fuchsia, and **adjusts** a piece or the teaser by moving or resizing its marker. `shorts.py accept EP` reads the markers back, writes the accepted flags and the adjusted ranges into `candidates.json`, and runs `check` on them again.
- The review timeline is regenerated from `candidates.json` after each `accept`, so it always shows the current state.

### The short's timeline
- One timeline per candidate, `<prefix> short <rank> <title>`, 1080×1920 at the episode fps. Only accepted candidates are built. *(Our call)* The timeline is tied to the candidate's stable id (recorded in `shorts/plan.json`); changing rank or title renames the existing timeline, never makes a second one.
- **Order:** teaser → passage (from its start, so the teaser's words are heard again in place) → end card.
- **V1 A-roll:** the camera clips themselves (not the nested chapter), with the chapter's audio. Shorts are built ungraded and without audio fixes (user: grading and audio fixes happen in the last pass, after B-roll); nothing is copied from the chapter items beyond the cut ranges. **One fixed face crop per piece** (proposal accepted): the speaker's face is found on sampled frames of the piece and the 9:16 window is centred on it, with the face in the upper third. *(Our call)* Face finding runs offline on the host (OpenCV class of tools; the reference `face_track.py` can be adapted).
- **B-roll (user: reused automatically):** every long-form B-roll item that overlaps a piece is copied over the same words, trimmed to the overlap with the matching source offset. Stock is **centre-cropped** to fill the frame (proposal accepted). KAYNAK screenshots are **fitted to the width** and flagged, since a centre crop would cut the article's text (user, approved in the earlier shorts session). Graphics are **re-rendered vertical** from their archived `vars.json` when their template supports vertical (proposal accepted); *(our call)* a template without a vertical version (`bar-chart`, `watermark` today) is fitted to the width over black and flagged in the summary. A placeholder left in a signed-off chapter is not copied (the speaker shows) and is listed.
- *(Our call)* "As signed off" means the same file and source range under the same words, including the editor's swaps, trims and added clips. The framing is redone for 9:16: an editor's zoom/pan/crop made for 16:9 can't carry over, so those items are centre-cropped and flagged for a look. A graphic without an archived `vars.json` (one the editor added by hand) is fitted to the width and flagged. A non-vertical **overlay** (V3) is fitted to the width with nothing behind it, so the speaker stays visible.
- **No B-roll during the teaser** (proposal accepted).
- **B-roll is muted (user):** B-roll is copied video-only, as the B-roll skill already places it; only the speaker's audio is heard.
- **Teaser captions (user: word by word):** the teaser's words appear **word by word, timed to the speech**, rendered **behind the speaker's head**. This needs a new word-timing field type in the making-graphics template contract and `make_graphic.py` (words with their frame ranges relative to the graphic's start), done as part of this project. The rest of the teaser caption: the caption from a making-graphics template, the speaker cut out over it with a matte made only for the teaser frames. *(Our call)* The cut-out speaker is pre-rendered as a clip with alpha, so the stacking is plain tracks in Resolve (no Fusion).
- **Regular captions (user):** subtitles on the subtitle track, spelled as in the script (matched words take the script's spelling, unmatched words keep the transcript's), from the words of the passage, timed to the short's frames, not over the teaser or end card. *(Our call)* At most two lines and ~32 characters a line, split at word gaps.
- **Watermark:** everywhere except the teaser and end card (proposal accepted).
- **End card** (user: one consistent graphic): logo, "YENİ VİDEO", the **episode's title** (proposal accepted) and "Videonun tamamı YouTube kanalımızda". *(Our call)* The title comes from a new `"title"` in `episode.json`; the end card is a making-graphics template, placeholder until it exists.
- **Title header:** off by default (proposal accepted); `"header": true` on a candidate adds it from a template, placeholder until one exists.

### Review and rebuilds (user: markers like the rough cut)
- Fuchsia ranged markers mark the teaser, every join between pieces and any flagged item (non-vertical graphic, uncopied placeholder); the candidate's reason sits on a marker at frame 0. Yellow stays the editor's.
- *(Our call)* Rebuilds keep editor changes the B-roll skill's way: `shorts/plan.json` records what the skill placed, each build reads the short back first, and anything the editor changed, deleted or added is never touched again. Subtitles included: an edited caption stays as the editor left it.
- **Freezing a short** (user, earlier session): `shorts.py freeze EP <id>` signs a short off; later builds skip it (`unfreeze` undoes it).
- *(Our call)* Changing a candidate's pieces or teaser in `candidates.json` rebuilds that short's untouched parts; removing a candidate never deletes its timeline (the editor deletes it). Editor items and edited captions stay at their frames, as in the B-roll skill; each is anchored to the source words it sat on, and when those words moved or left the passage it gets a Fuchsia marker and a summary line instead of being moved or guessed.

### Packaging *(our call)*
- Project skill `.claude/skills/cutting-shorts/` with `SKILL.md`, scripts in `scripts/`, reusing `episode.py` and the B-roll skill's Resolve helpers by import. Resolve steps through `rv.sh`.
- Offline tests for boundary snapping, length checks, B-roll overlap/trim mapping, crop maths and caption splitting, on COP31 data; Resolve steps verified live.

## Acceptance
On the copy `episodes/cop31-broll` (prefix COP31B) with chapters 3 and 4 B-roll signed off:
- `candidates` + the subagent give ranked candidates within 30-45 s; `check` leaves no boundary inside a word.
- The review timeline shows every candidate as markers; after the editor accepts two (one with a resized piece) and `accept`, only those two are built, with the resized range.
- At least two shorts build as 1080×1920 timelines: teaser first with behind-the-head captions (or the placeholder if the template is missing), the passage with the face centred, the long-form B-roll over the same words (R012's graph fitted and flagged, stock centre-cropped), subtitles on the passage, watermark, end card with the episode title.
- No long-form timeline changes after any number of builds.
- An editor fixes a caption, moves a B-roll item and deletes another; after a rebuild all three are as the editor left them. A frozen short is skipped by later builds.

## Left to the builder
- How Resolve's subtitle track is created and read back through the API (SRT import or other), and how the matte is made.
- Face detection method and sampling, crop maths for the camera's 4K frame.
- Exact JSON field names, summary wording, CLI flags, timeline naming details.
