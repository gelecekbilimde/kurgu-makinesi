---
name: rough-cutting-a-roll
description: Use when rough-cutting talking-head A-roll in DaVinci Resolve Studio from camera clips plus separate recorder WAVs - removing retakes ("bir daha", "tekrar"), false starts, pauses and breaths, splitting the cut into script chapters, or applying an editor's review markers to a rough cut. Built for Turkish teleprompter shoots (Gelecek Bilimde).
---

# Rough-cutting A-roll

## Overview
Scripts drive Resolve Studio. The **transcript decides what to keep** and the **audio decides where to cut**. All cuts are integer camera frames in half-open `[start, end)` ranges, never seconds.

The engine removes only what it is sure of. It **suggests** the rest as ranged markers. The editor's **Yellow ranged markers** are final: they mean "remove this range; the good take starts at the marker end". Each script chapter gets its own timeline, which is regenerated from the plans until the editor signs it off (freezes it).

## Requirements
- **Resolve Studio 21.2+**, running with the project open. Set Preferences › System › General › External scripting to *Local*.
- **Resolve tools** run through `bash scripts/rv.sh <tool>`, which uses the system `python3`.
- **Analysis tools** run with `.venv/bin/python`, after `python3 -m venv .venv && .venv/bin/pip install -r .claude/skills/rough-cutting-a-roll/requirements.txt`.
- **The episode directory** is `episodes/<slug>/`, which git ignores. Its manifest `episode.json` has the clips in episode order, their bins, recorder WAVs and offsets, the script path, the timeline prefix and the frozen chapters. The full schema is in the docstring of `scripts/episode.py`.

All paths below are relative to `.claude/skills/rough-cutting-a-roll/`.

## Pipeline
1. **Raw footage.** Unzip it outside the repo or under `demo/`.
   - Find the host's mic track on the recorder. It's the loud, voiced one (`Track2` on the COP31 shoot).
   - Pair each camera file with its recorder take, using creation time and duration.
   - Put the clips in script order and write `episode.json`, including `"speaker"`: who is actually on camera. Scripts can name the wrong person.
   - Ask the user when a pairing is unclear.
2. `bash scripts/rv.sh scripts/resolve_setup.py EP` sets the fps and Turkish transcription. Run it before any timeline exists.
3. `bash scripts/rv.sh scripts/ingest.py EP` imports, waveform-syncs, and writes `frames` and `offset_f`.
4. `.venv/bin/python scripts/sync_check.py --fps 25 CAM:WAV …` is an independent sync check. It must agree with `offset_f_exact` within ~0.5 f.
5. `bash scripts/rv.sh scripts/transcribe.py EP` transcribes the recorder WAV and the camera clip for each clip (one Resolve job at a time).
6. From the repo root, `python3 templates/script/script_doc.py script.docx EP --prompter` writes `EP/script.txt`, with the `[Heading2]`/`[Heading3]` styles kept. For an A/V script (the template in `templates/script/`), it also writes `script.json`, prints the row warnings and the length as written at the speaker's pace, and writes `prompter.txt` for the teleprompter. Old-style scripts work too, without `--prompter`.
7. `.venv/bin/python scripts/plan_episode.py EP` writes `plans/*.json` and prints the suggestions and flags.
8. `python3 scripts/sections.py EP` maps every kept piece to a chapter. It prints the chapter starts; check that they are plausible.
9. `bash scripts/rv.sh scripts/chapters.py chapters EP`, then `… chapters.py master EP`, build the chapter timelines and the master.

A clip that a later clip re-records completely, with no unique content left, gets `"skip": "<reason>"` in the manifest. Confirm this against the script before skipping.

## Review loop (per chapter)
The editor marks failed bits as **Yellow ranges** in `<prefix> chN …`, or recolours a Fuchsia suggestion to Yellow. Then run:
`markers_to_edits.py "<timeline>" EP` → `plan_episode.py EP` → `sections.py EP` → `chapters.py chapters EP N` → `chapters.py master EP`.
When a chapter is signed off, `chapters.py freeze EP N` locks it. It is never rebuilt again, and the master nests its timeline.

## Marker legend
| Colour | Meaning |
|---|---|
| Blue / Green / Sky | clip boundary / chapter start / subsection start |
| Red / Rose / Purple | removed: cue retake / repeated phrase / other (orphan, abandoned "…", heading number, cross-clip) |
| Cyan | cut found only by the camera transcript |
| **Fuchsia (ranged)** | suggested failed bit, **not removed**, e.g. a silent restart the transcription folded into one word |
| **Pink (ranged)** | retake longer than 30 s, **not removed** |
| **Yellow (ranged)** | the editor's: remove this range. The engine never uses Yellow. |

## Common mistakes
- **The project fps is still 24** (Resolve's default): timelines resample the 25 fps camera. Run `resolve_setup.py` first.
- **Transcription language is left on auto:** Turkish comes out as English nonsense. Turkish needs the Extras package that `resolve_setup.py` installs.
- **Times are treated as seconds:** every plan, edit and map uses frames, and all four tools assert it.
- **A frozen chapter is rebuilt by hand:** that destroys the editor's work. Unfreeze it explicitly first.
- **A timeline name contains `§ : ?`:** Resolve refuses the name, and `AppendToTimeline` then writes into the *current* timeline. The tools assert against this.
- **The silent-restart suggestions are trusted as cuts:** they are guesses, so the editor must decide.

Planner rules and parameters, the plan JSON format, known limits and API gotchas are in `reference.md`. The development history is in `docs/spike/2026-11-10-cop-spike-log.md`.
