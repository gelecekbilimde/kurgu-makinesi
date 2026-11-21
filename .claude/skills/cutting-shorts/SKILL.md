---
name: cutting-shorts
description: Use when an editor wants vertical shorts cut from a finished long-form episode in DaVinci Resolve - picking and ranking 30-45 s passages from the signed-off chapters, a review timeline to accept them, then 1080x1920 short timelines with the face crop, the long-form B-roll over the same words, subtitles, a word-by-word teaser caption, watermark and end card, rebuilt without losing the editor's changes. Also for freezing a finished short. Built for Gelecek Bilimde episodes.
---

# Cutting shorts

## Overview
A short is a passage (30-45 s, one or more stitched pieces) from the **signed-off** chapters of a long-form episode: chapters that are in both `"frozen"` (A-roll) and `"broll_frozen"` (B-roll) of `episode.json`. Each short becomes a vertical timeline `<prefix> short <rank> <title>`: a 1.5-3.5 s teaser lifted from inside the passage plays first, then the passage from its start, then a 3 s end card. V1 is the camera itself (one fixed face crop per piece and camera clip), the long-form B-roll is copied over the same words, captions go on Resolve's subtitle track, and the teaser's words appear word by word behind the speaker's head.

**Your only judgment step is writing the candidates** (step 2): which passages, in what order, which teaser line. Everything else is running scripts and relaying what they print. Never place clips through the Resolve MCP, change the crop, choose B-roll or invent graphics. Never change a long-form timeline (frozen chapters, `… B-roll`, `<prefix> B-roll`, `<prefix>`): the scripts only read them.

`shorts/plan.json` is the truth about what is on the short timelines. Each `build` reads the short back first: anything the editor changed, deleted or added is kept and never touched again.

## Requirements
- An episode from the rough cutter and the B-roll skill: `script.json`, transcripts, `sections.json`, chapters frozen (`chapters.py freeze`) and their B-roll frozen (`broll.py freeze`). Only those chapters are used.
- `"title"` in `episode.json`: the episode title on the end card. `prepare` stops without it.
- Resolve Studio 21.2+ running with the episode's project open. Resolve steps go through the rough cutter's `rv.sh`.
- Python packages for the face crop and the teaser cut-out, in the repo's venv: `.venv/bin/pip install -r .claude/skills/cutting-shorts/requirements.txt`. On first use `shorts_media.py` downloads two mediapipe models into `.claude/skills/cutting-shorts/.cache/models/` (gitignored; needs the network once). `shorts.py`, `shorts_resolve.py` and the tests need only the system `python3`.
- making-graphics set up (`setup.py` done). Templates the short uses when the active design has them: `teaser-caption` (a `words` field, overlay, vertical), `end-card` (a `title` field), `short-header` (a `title` field, only for `"header": true`), `watermark`. A missing one becomes a placeholder and a "Gereken şablonlar" line.

Shorthands below: `S=.claude/skills/cutting-shorts/scripts`, `RV="bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh"`, `EP=episodes/<ep>`.

## Steps
1. **Read:** `$RV $S/shorts_resolve.py read $EP` reads each signed-off chapter's frozen A-roll V1 and its `… B-roll` timeline, read-only, into `shorts/layout/ch<N>.json` and `shorts/broll/ch<N>.json`. Run it again whenever a long-form chapter changed.
2. **Candidates:** `python3 $S/shorts.py candidates $EP > $EP/shorts/candidates-in.json` writes `shorts/sentences.json` and prints the sentences (chapter frames) with the chapters' script rows. Then dispatch **one subagent** with the prompt below (or do it yourself when no subagent tool is available, following the same prompt).
3. **Check:** `python3 $S/shorts.py check $EP` gives new candidates their ids (`c3`, `c4`, …), snaps every piece and teaser to the gaps between words (the rough cutter's padding: 2 frames before a word, 3 after, never past the middle of a gap) and checks lengths and chapters. It prints what it moved and every error (`c4: pasaj 47,2 s (30–45 s olmalı)`); fix the file and run it again until `0 hatalı`.
4. **Review:** `$RV $S/shorts_resolve.py review $EP` builds `<prefix> short adayları` (bin `<prefix> Shorts`): the signed-off chapter B-roll timelines nested in order, one Fuchsia ranged marker per piece and per teaser (placed at the chapters' offsets as the nested timelines landed on V1; `accept` reads them back with the same offsets). Marker name `<rank>. <title>`, note = reason + teaser rating, customData `short:<id>:p<i>` / `short:<id>:t`.
5. **The editor accepts** in Resolve (see below), then `$RV $S/shorts_resolve.py accept $EP` reads the markers back into `candidates.json` (`accepted`, moved/resized ranges), re-checks them and rebuilds the review timeline. It prints `Kabul edilen adaylar: c1, c4`.
6. **Prepare:** `python3 $S/shorts.py prepare $EP [ID ...]` for the accepted, not frozen candidates: face crop (`crop.json`), the teaser cut-out (ProRes 4444 with alpha), vertical re-renders of the copied B-roll graphics, the teaser caption, end card and watermark through `make_graphic.py`, placeholders for missing templates, `captions.srt`, and `shorts/<id>/assets.json`. About a minute per short. Run it again after any change to a candidate's ranges or a template. Re-running it re-renders the graphics under new names, so the next build replaces those items once (`N eklendi, N kaldırıldı`); the teaser cut-out and placeholder stills are named by a hash of what they show, so they change only when their content does.
7. **Build:** `$RV $S/shorts_resolve.py build $EP [ID ...]` creates or updates each accepted, not frozen short's timeline (bin `<prefix> Shorts/<id>`) and writes `shorts/plan.json`. Rebuilding is always safe.
8. **Report** the summary as printed (see reference.md "Summary lines"): per short `eklendi / kaldırıldı / korundu (düzenleyici öğesi)` and every `Uyarı`, then `Kontrol edilecekler` (fitted graphics, editor-framed items, B-roll copied at 100 % from another speed or without its opacity/composite mode, the watermark, a subtitles re-import), `Kopyalanmayan öğeler` (long-form placeholders and file-less items: Text+, generators, compound clips), `Kayan düzenleyici öğeleri`, and **`Gereken şablonlar`** (offer the making-graphics design path for them).
9. **Sign off:** `python3 $S/shorts.py freeze $EP <id>`: later `prepare`/`build` runs skip it (`c1: dondurulmuş, atlandı`). `unfreeze` undoes it.

### Candidate prompt (the subagent's whole brief)
> You choose short-video candidates from a Turkish science episode. Input: `<the JSON printed by shorts.py candidates>` (sentences per chapter with `start`/`end` frames on the chapter timeline at `<fps>` fps; the script rows for context) and the current `episodes/<ep>/shorts/candidates.json`.
> Pick and rank **5-8 candidates in total** (existing entries count). Each is a passage that works on its own for someone who never saw the episode: one clear idea, a hook in its first seconds, an ending that lands. A passage is **30-45 s** (`30*fps..45*fps` frames, summed over its pieces; the teaser and end card don't count). It may stitch several pieces, in the order given, from anywhere in the listed chapters, when the joined text reads naturally; start and end pieces on sentence boundaries (use the sentences' `start`/`end`).
> For each candidate pick a **teaser**: 1.5-3.5 s of the most striking words, inside one of its pieces, also on word boundaries.
> Append to `candidates` **without an `id`** (check assigns it) and **never change or remove an existing entry**:
> `{"rank": <1 = best, unique over all entries>, "title": "<short Turkish working title, no ':'>", "pieces": [{"chapter": N, "start": F, "end": F}], "teaser": {"chapter": N, "start": F, "end": F}, "reason": "<one Turkish line: why it works>", "teaser_rating": <1-5, how strong the teaser line is>, "accepted": false, "frozen": false, "header": false}`.
> Integer frames, half-open `[start, end)`. Choose and rank only: no B-roll, crop or caption decisions. Reply with the ids-less list you added (rank, title, length in seconds).

## What the editor may do in Resolve
- **Review timeline:** turn any marker of a candidate **Green** to accept it; delete its markers or leave them Fuchsia to reject; move or resize a piece's or the teaser's marker to change the range (accept snaps it to word gaps again). Don't edit the nested chapters there.
- **Short timelines:** everything. Move, trim, zoom/reframe, delete, add clips, tracks and Yellow markers, re-enable the scratch audio, fix a subtitle cue's text or timing. A changed item becomes the editor's and build never touches it again; a deleted one stays deleted; an added one is kept. The camera crop is an exact fill with the face centred horizontally and Tilt 0 (the camera's own vertical framing): for a tighter shot, zoom in Resolve.
- **Subtitles** are appended only to a **fresh** timeline (the API can place cues only on an empty one). When a short's passage or teaser changes later, build rewrites `shorts/<id>/captions.srt`, leaves the cues as they are, and puts a Fuchsia marker at frame 0 asking the editor to re-import it (delete the old cues, File › Import › Subtitle, drag to the subtitle track at 0).
- To rebuild a short from scratch, delete its timeline and its entry in `shorts/plan.json` together; then build makes it fresh, with subtitles.

**Markers** (customData `short:<id>:…`): **Fuchsia** = the engine's: the teaser and the candidate's reason at frame 0, every join between pieces, every flagged item (a graphic fitted to the width, an item the editor framed for 16:9, a retimed item copied at 100 %, an opacity or composite mode not copied, a graphic without `vars.json`), a placeholder or file-less item (Text+, generator, compound clip) of the chapter that was not copied (the speaker shows), an editor item whose words moved (`Kayan`), the subtitles re-import note. Marker texts on one frame are merged. **Green** = an accepted candidate on the review timeline. **Yellow** is the editor's: never written, never touched. Our markers are deleted and re-added on every build, so recolour or resize an engine marker and it comes back; add a Yellow one instead. Review markers that land on an occupied frame are bumped ≤ 4 frames and carry their intended start in customData (`short:c1:p0@803`), so an untouched marker reads back exactly.

## Common mistakes
- **Using an unsigned chapter.** Only chapters in both `"frozen"` and `"broll_frozen"` are listed, checked and built. Freeze the chapter's B-roll first.
- **Editing a long-form timeline to fix a short.** Fix it on the short. To change the passage, edit the candidate (review markers or `candidates.json`), then `check`, `prepare`, `build`.
- **Overwriting `candidates.json` when adding candidates.** Append only; ids, `accepted` and `frozen` live there.
- **Building after a range change without `prepare`.** Build reads `assets.json` and `crop.json`; they must match the candidate.
- **Deleting or hand-editing `shorts/plan.json`** (except together with the timeline, above). Without it build takes the whole short for the editor's and places everything again on top.
- **Expecting changed captions on an existing short.** Re-import `captions.srt` when the Fuchsia note asks for it.
- **Running Resolve steps with plain `python3`, or media steps with the system python.** Resolve steps need `rv.sh`; `prepare` calls `.venv/bin/python` itself.

See `reference.md` for the Resolve API facts, file formats, track layout, summary lines and the acceptance run.
