# Rough-cutting A-roll: reference

## Tools
| Tool | Runs with | Reads | Writes |
|---|---|---|---|
| `resolve_setup.py EP` | rv.sh | manifest fps, language | project settings; installs the Turkish transcription package |
| `ingest.py EP` | rv.sh | clips (camera, recorder, bin) | media pool, waveform sync; `frames`, `offset_f_exact`, `offset_f` in the manifest |
| `sync_check.py CAM:WAV …` | .venv | media files | prints the GCC-PHAT lag of camera scratch audio vs the WAV, and a confidence (> ~5 is solid) |
| `transcribe.py EP` | rv.sh | clips | `transcripts/<stem>-wav-tr.json`, `<stem>-cam-tr.json` |
| `docx_to_text.py in.docx out.txt` | python3 | the script .docx | text with `[StyleName]` prefixes |
| `cutplan.py …` | .venv | one clip | one plan (called by plan_episode) |
| `plan_episode.py EP` | .venv | manifest, transcripts, WAVs, edits | `plans/<stem>-plan.json` |
| `sections.py EP` | python3 | plans, WAV transcripts, script | `sections.json` |
| `chapters.py chapters\|master\|freeze\|unfreeze EP [N…]` | rv.sh | plans, sections, manifest | timelines, `timelines/<name>.json` maps |
| `markers_to_edits.py "<timeline>" EP [colour] [--dry]` | rv.sh | the timeline's markers and map | `edits/<stem>-edits.json` |

Offset convention: `camera_frame = recorder_frame + offset_f`. Set `"offset_locked": true` to keep a hand-verified offset when ingest is re-run.

## What the planner does (`cutplan.py`; details are in its docstring)
1. **Audio:** per-frame RMS dB and voicing from the recorder WAV. Islands are runs of frames ≥ -45 dB. A word owns the island that contains its **end**, because ASR word starts are often late or stretched over silence.
2. **Hallucinations:** words with no sound under them are dropped, and so are Whisper stock phrases ("İzlediğiniz için teşekkür ederim", "Altyazı M.K.", "abone ol"), even over a cough.
3. **Units:** words are split at sentence punctuation and at audio pauses (≥ 12 f, or ≥ 6 f for an unpunctuated transcript). A "bir daha" splits its unit.
4. **Cue clusters:**
   - **Strong** (always cut): "bir daha", or the discard words "neyse / boşver / uzatmayalım / uzadı".
   - **Weak** ("Tekrar.", "Dur/Durun.", "pardon", "olmadı", "baştan", a short "…yapalım" meta sentence): cut only when the speech before them overlaps the restart; otherwise they become a suggestion.
   - Clusters are processed **right to left**, so each one is compared with the *final* take.
5. **Attempt start:**
   - The unit before the cue is always part of the attempt. Earlier units join while their content overlaps the restart: IDF-weighted 5-letter stems, numbers compared by their digits, score ≥ 0.5 (or ≥ 0.35 with 2 or more shared stems). The walk goes at most 30 s back and never past the previous cue.
   - The start then moves to the earliest unit that overlaps the restart's first 6 stems (≥ 0.4) or opens with the restart's first word. A two-word opening match also counts, but only when it contains a content word ("Bir diğer…" is too weak).
   - Inside a unit, the restart's first content word marks the start, unless the words before it are stop words, a heading number, or are themselves re-said.
   - A discard cluster removes everything back to the previous cue.
   - An attempt longer than 30 s is not removed: only the unit before the cue goes, and the rest is flagged (Pink).
6. **Other rules:**
   - An abandoned "…" unit whose content the next words repeat.
   - A heading number read on its own ("3.3").
   - A cross-clip retake: the clip's tail re-said at the head of the next clip.
   - A repeated 3-word phrase means the last take wins. It may span removed cue words and up to 20 s only when both occurrences start a unit.
   - An orphan: ≤ 3 words and < 2.5 s, with cuts on both sides.
   - A dangling phrase start: 1–2 words running into an editor's or camera-transcript cut, or into a restart that opens with the same word.
7. **Camera transcript (second opinion):** it adds only cuts the primary transcript did not make. It never widens a primary retake cut.
8. **Editor ranges (`--edits`):** cut exactly as given. They mark only words that are ≥ 90% inside the range, because a swallowed word can hold the good take.
9. **Cut placement:**
   - Breath trim: the tail below -42 dB, the head below -33 dB and weakly voiced, in runs of 3 frames or more.
   - Padding goes only through silence below -50 dB, with at least 2 f of release.
   - Pieces are merged across gaps ≤ 11 f that contain no removed sound.
   - A mixed island is split at its quietest frame, biased toward the kept word, and never more than 3 f past a kept word's end.
   - The clip end holds 500 ms.
10. **Suggestions (Fuchsia):** a "swallowed retake" is a kept word longer than 1.6 s with more than 8 active frames per letter (p99 across all words is 8.2). The ASR merged a silent restart into it. The range runs from the unit start to the first silence inside the word. Suggestions that overlap an editor range are dropped.

All thresholds are in the `P = dict(...)` block at the top of `cutplan.py` and are copied into every plan's `params`.

## Plan JSON (per clip)
`units: "frames"`, `range: "half-open [start,end)"`, `fps`, `clip`, `offset_f`, `clip_end_f`, `keep_frames` [[a,b]…], `removed` [{kind, start_f, end_f, how, source, text}], `suggestions`, `review_flags`, `long_words`, `hallucinated`, `kept_text`, `params`. `sections.json` labels every `keep_frames` piece with `[clip, a, b, chapter, heading]`.

## Script conventions (`sections.py`)
- **Chapters:** `[Heading2]` lines, starting at the one that begins with "1.".
- **Subsections:** `[Heading3]` lines.
- **Stop:** at "Kaynakça".
- **Ignored:** `[EKRAN …]` lines, which are the writers' B-roll notes, and (pronunciation hints).
- **Overrides** in the manifest: `script_levels`, `script_stop`, `transition_words`.
- **Boundary placement:** a chapter boundary lands on a transition word ("Gelelim", "Peki", "Gelin", "Şimdi") or on a word from the heading's title.

## Known limits (COP31 review: 36 reviewer markers)
- **Engine alone:** 68% of the marked frames were removed and 8% suggested.
- **By marker:** 20 fully removed, 5 partly, 8 suggested, 3 missed.
- **Partial cuts:** a second failed attempt with no cue word after it.
- **Misses:** an "addition" restart the reviewer preferred to drop; a meta remark ("Bunu anlamadım ya"); an off-script ad-lib, which is the editor's call.
- **Known wrong cut:** a spoken label right before a re-read sentence, where there is no pause to split on.
- **Silent restarts** can only be suggested, because the repeat isn't in the transcript.

## Resolve API gotchas (21.2)
- `ImportMedia([path])` works; the dict form returns None.
- `AutoSyncAudio([video, wav], {"syncMode": resolve.AUDIO_SYNC_WAVEFORM, "retainEmbeddedAudio": True})`. The offset is in `GetAudioMapping()` › linked_audio › offset, given in samples, and the sign is inverted.
- Only **one transcription job at a time**: `TranscribeAudio` returns None while another one runs. Poll `GetTranscription()`.
- `AppendToTimeline([{mediaPoolItem, startFrame, endFrame}])`: `endFrame` is **exclusive**.
- Timelines are media pool items (`GetClipProperty("Type") == "Timeline"`). Appending one to another timeline nests it.
- A nested timeline's audio lands on A1. So the camera scratch audio is muted per item (`SetClipEnabled(False)`), not per track, in the master.
- `AddMarker(frame, colour, name, note, duration)`. Ranged markers come back from `GetMarkers()` with a `duration`. There is no "Orange" marker colour.
- Resolve rejects some characters in timeline names (`§ : ?`). `CreateEmptyTimeline` then returns None.
- The system locale may be ASCII: rv.sh sets `PYTHONIOENCODING=utf-8`, and files are written as UTF-8.
