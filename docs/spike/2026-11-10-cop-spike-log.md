# Spike log — COP raw footage, A-roll cleanup in Resolve

**Date:** 2026-11-10
**Status:** throwaway spike (nothing here is production code)
**Goal:** find out whether DaVinci Resolve Studio 21.2's built-in tools (audio sync, Turkish transcription, silence removal), driven by script, are good enough for the A-roll cleanup. The main open question is whether Turkish filler sounds ("ııı", "eee") show up in the transcript.

Scripts used are in `docs/spike/scripts/`. Run them with `./rv.sh <script>.py`, which sets the Resolve scripting environment variables for Linux.

---

## Environment

| Item | Value |
|---|---|
| OS | Linux (RHEL-family, kernel 6.12), 16 cores, 29 GB RAM, no NVIDIA GPU |
| Resolve | Studio 21.2.0.6, `/opt/resolve`, external scripting enabled, running with GUI |
| Python | 3.12 (system), using Resolve's `DaVinciResolveScript` module |
| Resolve project | `demo`, empty at start, 1920×1080, **24 fps by default** |
| Not installed | ffmpeg (not needed so far; WAVs analysed with Python's `wave` module) |

Scripting env (Linux), from `/opt/resolve/Developer/Scripting/README.md`:

```bash
export RESOLVE_SCRIPT_API=/opt/resolve/Developer/Scripting
export RESOLVE_SCRIPT_LIB=/opt/resolve/libs/Fusion/fusionscript.so
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

Resolve also ships an **official Blackmagic MCP server**: `/opt/resolve/DaVinciResolve.mcpb` (a Node server with tools like `run_script`, `get_scripting_api`, `get_image` and `get_thumbnails`). It's packaged for the Claude desktop app. It isn't used in this spike yet.

---

## 1. Raw delivery: what's in the zip

`demo/cop/raw/COP.zip` is **52 GB**. It extracts to `demo/cop/raw/COP/` (plenty of free disk: 1.4 TB).

- **7 camera files**, `P1011087.MOV` … `P1011094.MOV` (no 092). Sizes run from 1.4 to 10.9 GB.
- **7 audio recorder folders**, `372 - 23 Oct 2026` … `378 - 23 Oct 2026`, each containing:
  - `Stereo Mix.wav`: 2 ch, 24-bit, 48 kHz
  - `Track1-Combo 1.wav`: 1 ch, 24-bit, 48 kHz
  - `Track2-Combo 2.wav`: 1 ch, 24-bit, 48 kHz
  - `Meta.xml`: recorder metadata (name, duration, creation time, show UUID). This looks like RØDECaster-style metadata (*guess*).
- **Pairing is by order** (*inferred, not yet confirmed by sync*): file sizes are proportional, so 087↔372, 088↔373, 089↔374, 090↔375, 091↔376, 093↔377, 094↔378.
- **No script file in the delivery.** Matching takes against the script needs the script from the academics.

Extraction: Python `zipfile` (no `unzip` on the machine). Audio was extracted first so analysis could start early.

## 2. Which mic is the host?

Loudness of recording 372 over a 60 s window starting at 30 s:

| File | RMS |
|---|---|
| Track1-Combo 1.wav | **-59.1 dBFS** (essentially silent / unused) |
| Track2-Combo 2.wav | **-23.3 dBFS** (host mic) |
| Stereo Mix.wav | -23.4 / -23.4 dBFS (mix ≈ Track2) |

→ **Use Track2 as the A-roll audio.** The pipeline should detect the active track automatically rather than hardcode it, since a different mic setup could swap the tracks.

## 3. Resolve project inspection (`01_info.py`)

Connected to the running Resolve. The project is `demo`, with 0 timelines and an empty media pool.

## 4. Import (`02_import.py`)

**API gotcha:** `MediaPool.ImportMedia([{"FilePath": path}])` (the dict form the 21.x docs recommend) **returned `None`**. The plain list form `ImportMedia([path, ...])` works. `MediaStorage.AddItemListToMediaPool` returned `[]` for a file that was already imported. → Use the list form.

The clips were imported into bin `spike-372`:

| Clip | Type | Duration | FPS | Resolution | Codec | Audio |
|---|---|---|---|---|---|---|
| P1011087.MOV | Video + Audio | 00:05:40:20 | **25** | 3840×2160 | H.264 High 4:2:2 L5.1, **10-bit** | 2 ch LPCM 48 kHz (camera scratch audio) |
| Track2-Combo 2.wav | Audio | 00:05:44:01 | (project) | – | LPCM | 1 ch 48 kHz |

The WAV runs about 3.4 s longer than the video, so the recorder started before the camera.

## 5. Frame-rate mismatch (`03_set_fps.py`)

The camera shoots **25 fps**, but the project default was **24 fps**. The timeline frame rate can only be changed while the project has no timelines, so it was set right away:

```
SetSetting("timelineFrameRate", "25") -> True   (playback rate followed automatically)
```

→ **The pipeline must read the camera FPS and set the project to match *before* creating any timeline.** 4K 10-bit H.264 4:2:2 is also heavy to edit on most machines. Expect to need proxies or optimized media for the editors (*guess*, to confirm with the hardware survey).

Transcription settings at this point: `transcriptionLanguage = 'auto'`, `transcriptionExtendedLanguageSupport = '0'`.

## 6. Audio sync (`04_sync.py`)

```python
mp.AutoSyncAudio([video, wav], {"syncMode": resolve.AUDIO_SYNC_WAVEFORM, "retainEmbeddedAudio": True})
```

→ `True`. The WAV is linked to the MOV as audio track 2 (mono), with the camera's scratch audio kept on track 1:

```
linked_audio: {"1": {"channels": "1", "offset": -18239, ...Track2-Combo 2.wav}}
Audio Offset: -9.50 frames  (= -18239 samples @ 48 kHz ≈ 0.38 s)
```

Sync took well under a minute. *Not independently verified yet* (no ffmpeg to cross-check), but it's Resolve's standard waveform sync. Later: check by eye/ear in the UI.

## 7. Transcription, first attempt (`05_transcribe.py`): wrong language

- `SetSetting("transcriptionLanguage", "tr")` → **False**, and the setting stayed `auto`.
- `TranscribeAudio()` ran **non-blocking**. The script polled `GetTranscription()` until segments appeared, which took **145 s for 5:44 of audio on CPU** (no NVIDIA GPU).
- Auto-detect chose **English** and produced nonsense ("When the union strikes the location A…"). Saved as `docs/spike/out/372-track2-resolve.json` for reference.

Language code probe: `en` and `de` are accepted, but `tr`, `tr-TR`, `tr_TR`, `tur`, `Turkish` and `TR` are all rejected. `transcriptionExtendedLanguageSupport = "1"` → False.

**Cause:** Turkish isn't in Resolve's *built-in* transcription model. It's in the **"Extended AI Transcription Language Support 2"** Extras package (1.89 GB download), which wasn't installed. Note that *subtitles* (`AUTO_CAPTION_TURKISH`) list Turkish as a constant, but transcription still needs the extended model.

→ **Lessons for the pipeline:**
- Never rely on language auto-detect. Set Turkish explicitly and fail loudly if `SetSetting` returns False.
- The setup step must install the extended language package (it can be done by script: `resolve.InstallExtrasPackage(name)`, then poll `GetExtrasPackages()`).

## 8. Installing the Turkish model (`06_install_turkish.py`)

The package was queued through `resolve.InstallExtrasPackage("Extended AI Transcription Language Support 2")`, with progress polled from `GetExtrasPackages()`. It can be removed with `UninstallExtrasPackage`.

Other Extras available on this system (not installed): AI Slate ID (5.6 GB), AI Voice Training (4.2 GB), AI IntelliSearch Better/Faster (4.4/1.1 GB), AI Speech Generator (1.8 GB).

---
Install result: queued → downloading → installing → **installed in ~30 s** (fast connection). After that, `transcriptionExtendedLanguageSupport = "1"` and `transcriptionLanguage = "tr"` were both accepted.

## 9. Transcription, second attempt: Turkish (`05_transcribe.py`, `05b_dump_transcript.py`)

- **160 s for 5:44 of audio on CPU**, about 2.1× real time. Result: `language=tr`, 42 segments, **577 words**, each with its own start/end timecode. Saved as `docs/spike/out/372-track2-resolve-tr.json`.
- Script bug: the JSON dump failed with `UnicodeEncodeError` (the system locale is ASCII). Fixed by opening files with `encoding="utf-8"`. Since the transcript is stored on the clip, `05b_dump_transcript.py` re-reads it without re-transcribing.
- **The text quality is good** for Turkish science content. There are a few recognition errors on proper nouns and terms: "Ansalya" (Antalya), "uygulama kopu" (COP), "geçişi" (geçici). → Captions should be corrected against the script, not used raw.

## 10. Cleanup signals (`07_analyze.py`, `08_gap_energy.py`)

Recording 372: 5:44 span, **4:26 actual speech**, so roughly 1:18 (23%) is removable pause or retake.

### Fillers ("ııı", "eee"): the model drops them, but there are very few
- **Zero** hesitation tokens in the transcript. The only filler-like words are discourse words (`yani` ×6, `işte` ×3, `şey` ×2), which are real words and probably intentional. *Don't auto-cut them.*
- Checking the audio *inside* word gaps (noise floor ≈ -61 dBFS, speech ≈ -18 dBFS, threshold -42 dBFS): **52 of 59 gaps ≥ 0.25 s are true silence**, and only **7 contain 0.2–0.35 s of sound**. These are likely breaths or short hesitations, mostly right after a "bir daha".
- → **For teleprompter reads, filler sounds are a minor problem.** Cutting by gaps (transcript word times + audio energy) covers them, so no verbatim/filler-aware ASR model is needed. *To confirm by listening to the 7 spots.*

### Retakes: the host announces them out loud with **"bir daha"** ("one more time")
19 "bir daha" markers were found in 5:44, for example:

```
0:28  ...ilk kez bu kadar [BİR DAHA] Dünya ortalaması sanayi öncesine göre ilk kez bir yıl boyunca 1,5 dereceyi aştı.
0:39  ...2025'te de hemen arkasından geldi. [BİR DAHA] 2025'te hemen arkasından geldi.
2:59  ...ekspo da yapılacak. [BİR DAHA] bir daha bir daha. COP31 9-20 Kasım 2026'da [BİR DAHA] ...
```

This is the strongest signal for bad takes, and it's a production convention we can **formalize**: the host always says "bir daha" and then restarts the sentence. Rough-cut rule (*proposed, not yet implemented*): on "bir daha", find the start of the abandoned attempt (the last sentence start whose opening words match what follows the marker), then cut from that point through the end of the marker.

Caveat: "bir daha" can also appear in normal speech. With the script available, a "bir daha" that isn't in the script is a marker. Without the script, use the repeated-phrase check (`07_analyze.py` found 10 repeated 4-word phrases within 90 s, all of them next to a marker).

### Pauses
31 gaps ≥ 0.7 s, totalling 59 s. The longest is 6.5 s, between takes. Resolve's `RippleDeleteSilence` (dB threshold, padding, minimum length) exists as an alternative, but gap-cutting from word timings gives more control and keeps the cut decisions inspectable as data.

## Status at end of this session

| Question | Answer |
|---|---|
| Can Resolve sync the separate WAV by script? | **Yes**: `AutoSyncAudio`, waveform mode, under a minute |
| Turkish transcription with word timings? | **Yes**, after installing the extended language Extras package, about 2× real time on CPU |
| Fillers "ııı/eee" detectable? | Not as words (the model drops them), but **rare in teleprompter reads**. Gaps plus audio energy cover them |
| Bad takes detectable? | **Yes, very well**: the host's spoken "bir daha" marker plus repeated phrases. Even better with the script |
| Not done yet | building the actual rough-cut timeline; verifying the sync offset direction; matching against the script (not in the delivery) |

Gotchas found: the `ImportMedia` dict form returns `None` (use the list form); the project defaults to 24 fps while the camera shoots 25; transcription language auto-detect picks English; Turkish needs the Extras package; the system locale is ASCII, so always use explicit `encoding="utf-8"`.

---

# Part 2: the PoC rough cut (same session)

The session is now a **proof of concept**: rough-cut the real COP31 footage in Resolve by script, logging every step so the log can become a rough-cut guide. Housekeeping: `/demo/` was added to `.gitignore`. `assets/` was already ignored except `assets/assets.sha256`, which stays tracked because `fetch-assets.sh` needs it to verify the pack.

## 11. The script arrives (`10_docx_to_text.py`)

`demo/cop/raw/COP31_YouTube_Senaryosu.docx` → `docs/spike/out/COP31-script.txt` (225 paragraphs, 3318 words; plain `zipfile` + XML, no dependencies). What's in it:

- A **corrections table** at the top (the fact-check notes; not read on camera).
- Sections as Word headings, with a speaker name per section (e.g. "1. Açılış … (Begüm Dursun)").
- **`[EKRAN: …]` lines**: the writers' visual/B-roll suggestions ("seslendirilmez", not read aloud). → **Direct input for B-roll/HyperFrames automation later.**
- Pronunciation hints in parentheses, e.g. "COP (kap)". These aren't read as written, so alignment must ignore them.
- Estimated length 11–13 min.

**The host doesn't read verbatim.** There are ad-libs ("Çayınızı kahvenizi alın. Arkaya yaslanın…"), paraphrases, and an improvised intro at 0:02 ("Gelecek Bilim'de hoşgeldiniz… Gelin öncelikle bundan başlayalım") *before* the scripted cold open, with the scripted welcome following at 0:58. → The script is a **review aid** (flag off-script passages and missing lines), not a strict cut driver. Whether to keep an ad-lib is an **editorial decision left to the human**.

## 12. Which transcript to trust: the WAV, not the camera clip

The synced camera clip was also transcribed (`05_transcribe.py spike-372 P1011087.MOV`, 100 s) to measure the offset between camera and WAV time:

- 106 rare words appear once in both → median offset **camera − WAV = +0.40 s = +10 frames**, with zero spread. Resolve reported the linked-audio offset as -9.5 frames, so this matches. The camera clip's transcription evidently ran on the synced WAV.
- **But the camera-clip transcript was worse:** it missed 2 "bir daha" markers (4:56, 5:12) and **hallucinated** text at the end ("Sec ceremoni olarak bir çevresel olacaktır. chopsticks Mysterio"). The camera stops about 3 s before the recorder, so that pass saw cut-off audio. The WAV transcript has silence there and then "İzlediğiniz için teşekkür ederim." (after the camera stopped).

→ **Rule: transcribe the clean recorder WAV and map it to camera frames with the measured offset.** Drop any word that falls outside the camera clip's range.

## 13. Cut planner (`09_cutplan.py`)

**v1** (camera transcript; marker rule only): 5:38 → 4:02. It missed the 4:48 retake that had no marker, left an orphan "Bir." between two retakes, and kept the hallucinated tail.

**v2** (WAV transcript plus rules R2 and R3): 5:40 → 3:48, with 15 marker retakes and 1 orphan. Rules:

- **R1 "bir daha" marker**: cut from the start of the abandoned attempt through the marker run ("bir daha bir daha bir daha" counts as one run). The attempt start is the latest earlier word matching the first word after the marker, within 30 s; otherwise it's the start of the sentence.
- **R2 repeated opening**: a retake *without* a marker, e.g. "4. kritik nokta ise…" said twice. If a sentence's first 3 words reopen a later sentence within 20 s, the last take wins. (Here the WAV transcript did contain the marker, so R1 caught it first.)
- **R3 orphan**: a kept island of ≤ 2 words and < 1.5 s between two cuts gets dropped ("Bir." at 1:52).
- **R4**: trim head and tail, and shorten gaps > 0.45 s.

**v2 → Resolve showed every piece one frame short.** I'd passed `endFrame = b - 1`, but **`AppendToTimeline`'s `endFrame` is exclusive** (duration = end − start), and the plan was rounding seconds into frames.

**v3: frame-native (user requirement: "cut from frames, not timestamps").**

- Transcript timecodes (`HH:MM:SS:FF`) are converted **directly to integer frames**, never through seconds.
- The offset is a whole number of frames (**+10**). The -9.5 frame half-frame from Resolve is rounded, and it agrees with the measured 0.40 s.
- All pads and thresholds are in frames: `PAD_IN=3`, `PAD_OUT=5`, `MAX_GAP=11` frames, windows `30*fps`/`20*fps`.
- Ranges are **half-open `[start, end)`**, same as Resolve. The plan JSON records `units: frames`, `range: half-open`, the fps, offset and clip length (`P1011087.MOV` = **8520 frames**, from `GetClipProperty("Frames")`).

Result: **8520 f (5:40:20) → 5702 f (3:48:02)**, 34 pieces, with 15 retake cuts, 1 orphan and 22 pause cuts. Plan: `docs/spike/out/087-cutplan-v3.json` (it includes every removed span with its rule and text, and the full kept text).

## 14. Timeline build (`12_build_timeline.py`)

```python
mp.CreateEmptyTimeline("COP 087 rough v3")
mp.AppendToTimeline([{"mediaPoolItem": mov, "startFrame": a, "endFrame": b} for a, b in keep_frames])
```

- Result: 34 pieces → **V1: 34 video items, A1: 34 stereo items (camera scratch), A2: 34 mono items (recorder WAV, linked via sync)**. The linked WAV comes along automatically because the MOV was synced in step 6.
- **Duration check: all 34 items match the plan frame for frame (5702 f).** The script asserts this after every build.
- `SetTrackEnable("audio", 1, False)` disables the camera scratch audio.
- **Review markers**: one marker per cut point where a take was removed. Red = "bir daha" retake, Yellow = repeated-opening retake, Purple = orphan. The note holds the rule and the removed text, so the editor can jump between markers and check each decision. 16 removed takes → 11 markers (several removals fall on the same cut point and are merged into one note). `AddMarker` returns False if a marker already exists on that frame, hence the merging.
- Earlier attempts `COP 087 rough v2` (off by one frame) is still in the project for comparison.

**Status:** `COP 087 rough v3` is in the `demo` project, ready for human review.

---

# Part 3: human review round 1 → planner v4 (audio-aware)

## 15. The user's review of `COP 087 rough v3`

Overall: *"I really liked the cuts, the timeline feels very natural."* Specific notes (timeline TC, timeline starts 01:00:00:00):

| # | Note | Diagnosis (source frames; `13_inspect.py` maps timeline TC → source frame and prints per-frame dB + transcript words) |
|---|---|---|
| 1 | Restart after "2025'te … Bir daha." loses the start of "2025" | Voice onset at **1047**, but the ASR word starts at **1055** (8 frames late). The piece started at 1052. |
| 2 | Clip at 01:00:42:14 not understandable; start and end too tight, expand symmetrically | The 19-frame piece "COP31." (1646–1665). Speech runs 1642–1665, but the ASR word is 1649–1660. Both edges were clipped. |
| 3 | 01:00:47:08–47:15 breathing not removed | 1933–1940 after "anlatayım.": -34…-48 dB with weak voicing (0.07–0.45) = exhale/inhale, kept inside the word's padded span. |
| 4 | 01:01:00:06–01:04:18 huge empty space while coughing | **ASR stretched one word, "1995'ten", over 144 frames (5.8 s)**, covering silence, a cough (2418–2440) and a breath. The real word is only 2494+. |
| 5 | Breathing at the "Sera … bir daha" cuts | An inhale *attached to the start of the next word* (3014–3017, -35…-46 dB, voicing ≤ 0.4). |
| 6 | 01:01:38:06–41:10 empty space | Same as #4: a stretched word over silence. |
| 7 | 01:01:51:03–55:09 retake still included | **The WAV transcript collapsed the retake into one "word"**: "Kasım" = 4697–4814 (4.7 s) swallowing "Kasım 2026'da bir daha. COP31 9-20 Kasım". The camera-clip transcript has it: "…2026'da **bir daha.** COP31 9-20…". |
| 8 | 01:03:22:23–25:14 empty space | Stretched word over silence. |

**Root cause: ASR word boundaries can't be trusted for cut points.** Starts come late, ends come early, some words get stretched over seconds of silence, and occasionally a whole retake is merged into one word. Word *ends* are more reliable than word *starts*.

## 16. Per-frame audio features (`audio_frames.py`, needs numpy)

`numpy` wasn't installed, so a project venv was created: `python3 -m venv .venv && .venv/bin/pip install numpy==2.3.4` (`.venv/` is already in `.gitignore`).

For each **camera frame** (40 ms of WAV at 25 fps, shifted by the +10 frame offset), it computes:

- `db`: RMS level (dBFS)
- `voice`: voicing strength = max normalized autocorrelation over 70–400 Hz pitch lags, averaged over two half-frame windows

All 8520 frames take **0.7 s**. Cached at `docs/spike/out/372-frames.npz`.

Measured on this recording (Track2 host mic):

| Sound | dB | voicing |
|---|---|---|
| Speech (vowels) | -14…-30 | 0.5–0.8 |
| Silence / room tone | -55…-65 | – |
| Breath (inhale/exhale) | -34…-50 | 0.07–0.45 |
| Cough | -26…-44 | 0.2–0.6 (**overlaps speech**: it's only separable because it stands alone, between silences) |
| Unvoiced word onset (e.g. "2025'te" at 1047) | -34 | 0.26 (**1 frame**; a consonant, *not* a breath) |

## 17. Planner v4 (`14_cutplan_v4.py`): the transcript decides *what*, the audio decides *where*

1. **Word-level decisions** as in v3 (R1 "bir daha", R2 repeated opening, R3 orphan), plus **R2b**: any repeated 3-word phrase within 20 s means the last take wins.
2. **Second opinion**: the same rules also run on the **camera-clip transcript** (already in camera frames, offset 0). Removed spans the primary missed are subtracted from the kept audio, with cut points snapped to the quietest frame within ±3. This added 4 cuts and fixed #7. Overlaps where the second transcript starts earlier were checked: they only cover silence or the abandoned attempt, and no kept word was lost.
3. **Audio islands**: runs of frames ≥ **-45 dB**, with gaps < 3 frames merged (121 islands in this clip).
4. **Ownership**: each word owns the chain of islands ending at the island that contains its **end** frame, chained backwards only across gaps ≤ 11 frames. A stretched word therefore can't claim a cough 2 s earlier (fixes #4/#6/#8). Islands owned by no word (breath, cough, noise; **18 here**) are dropped.
5. **Mixed islands** (removed and kept words with no silence between them) are split at the quietest frame between the last removed word and the first kept word.
6. **Breath trim**: a breath frame is < -33 dB with voicing < 0.5. A leading or trailing **run of ≥ 3 breath frames** is trimmed (tail max 8, head max 12). Runs of 1–2 frames are consonant onsets or word-end decays and are kept. This took two tries: first the tail trim had no minimum run and clipped the 1-frame decay of "COP31", leaving #2's end still tight.
7. **Pieces** = kept islands, padded 2 frames before / 3 after, but **padding only extends into silence**, never into a trimmed breath. Neighbours merge when the gap is ≤ 11 frames *and* contains no dropped island.
8. **Long words** (> 1.6 s) are listed for review. Here: "1995'ten" 144 f, "Yani" 94 f, "COP31" 127 f, "Kasım" 117 f, "4." 50 f, "Birleşmiş" 77 f, all at retake or pause spots.

Review points re-checked in v4 (source frames):

| # | v3 | v4 |
|---|---|---|
| 1 | piece starts 1052 | starts **1045** (onset 1047 − 2 frames pad) |
| 2 | 1646–1665 | **1640–1669** (+6 / +4) |
| 3 | kept until 1941 | ends **1933** |
| 4 | cough + 4.5 s silence kept | cough island dropped, piece starts **2492** |
| 5 | inhale 3014–3017 kept | dropped, next piece starts **3019** |
| 6, 8 | silence kept | dropped |
| 7 | retake kept | removed (from the camera transcript) |

**Result:** 8520 f (5:40:20) → **5252 f (3:30:02)**, 33 pieces (v3: 5702 f). Timeline **`COP 087 rough v4`** was built, and its durations match the plan frame for frame. Markers: red = "bir daha", purple = orphan, **cyan = cut added by the second transcript**.

---

# Part 4: review round 2 → v5 (endings)

## 18. Review of `COP 087 rough v4`

*"You've solved all the previous problems, but now the yellow-marked clip endings seem eagerly cut. Cyan markers have no problems."*

The reviewer put **their own yellow markers** on the timeline. `15_read_markers.py` reads markers from a timeline via the API (`Timeline.GetMarkers()`) and maps each one back to its piece and source frame. That's a good review loop: **the editor marks in Resolve, and the script reads the marks back.** Six markers, each just before a piece end (one sits exactly on a cut, i.e. the end of the previous piece): pieces ending at source frames 180, 354, 1933, 2145, 3003 and 3265.

**Diagnosis:** at all six endings the final syllable **fades out at -33…-40 dB with weak voicing (0.16–0.45) for 3–7 frames**. Turkish sentence-final syllables are often unvoiced ("-ecek", "-ş", "-t", devoiced vowels). v4's tail-breath rule (< -33 dB and voicing < 0.5, run ≥ 3) classified that fade as breath and trimmed it.

Looking back at round 1 note #3 ("breathing" after "anlatayım", 1933–1940): the real breath is **1940–1947 at -47…-49 dB, voicing 0.07–0.24**. The 1933–1937 part that v4 trimmed was actually the word's fade. → **Loudness separates a word-end fade from a breath better than voicing does:** fades stay above about -42 dB, breaths sit around -45…-50 dB.

## 19. v5 changes (`14_cutplan_v4.py`, plan `087-cutplan-v5.json`)

- **Tail trim** only removes trailing frames below **-42 dB** (`TAIL_BREATH_DB`), still requiring weak voicing and a run of ≥ 3. The head-breath rule is unchanged (round 1 inhales were approved).
- **Padding after a piece** only extends through true silence (< **-50 dB**, `PAD_SIL_DB`), so it stops before a following breath. Padding before a piece follows the same rule.
- **Minimum release**: every piece end gets at least **2 frames** after the last sound (`MIN_RELEASE_F`), so an ending that fades into a quiet -45…-48 dB tail doesn't stop dead (the 3265 case gained only 1 frame without it).

| Flagged ending (source frames) | v4 end | v5 end | v5 timeline TC |
|---|---|---|---|
| piece 73– | 180 | **188** | 01:00:04:15 |
| piece 271– | 354 | **361** | 01:00:10:24 |
| piece 1817– | 1933 | **1940** (stops right where the -48 dB breath starts) | 01:00:48:13 |
| piece 2016– | 2145 | **2152** | 01:00:56:04 |
| piece 2903– | 3003 | **3009** | 01:01:13:03 |
| piece 3113– | 3265 | **3268** | 01:01:22:19 |

All round-1 fixes still hold (2025'te onset, COP31, cough, Sera inhale, missed retake, empty spaces). **Result:** 8520 f → **5342 f (3:33:17)**, 31 pieces. Timeline **`COP 087 rough v5`** built, durations frame-exact.

**Open/ambiguous:** the "anlatayım" ending (01:00:48:13 in v5) was flagged as *breath* in round 1 and as *cut too eagerly* in round 2. v5 keeps the fade and stops at the true breath, but it's the spot to listen to.

---

# Part 5: review round 3 → v6 (end of video)

## 20. Review of `COP 087 rough v5`

*"Endings sound perfect, I think the other parts are already fine. Except the very ending of the timeline: the last word 'kavşak' is cut early without finishing."*

**Diagnosis:** the last piece ended at source frame 8457. "kavşak" is voiced 8440–8453, then the closure of the final "k" (silence, 8453–8461), then the **release burst at 8462–8464** (-39…-48 dB, 8 frames after the vowel). That burst became its own tiny audio island with no owning word, so it was dropped as noise. And the timeline ended only 3 frames after the last sound, which sounds abrupt at the *end* of a video even though it's right between sentences.

## 21. v6 change

- **End hold**: the last piece of a clip is held `END_HOLD_F` = 25 frames (1 s) past its last kept sound, capped at the camera clip's end. Last piece 7886–8457 → **7886–8479**. All other pieces are identical to v5.
- Result: 8520 f → **5364 f (3:34:14)**, 31 pieces. Timeline **`COP 087 rough v6`**, durations frame-exact.

Known gap (not fixed, didn't come up mid-clip): a word-final stop release that arrives later than the merge gap after the vowel would be dropped as noise anywhere. If it shows up mid-video, add a "release" rule: a small, quiet island (≤ 3 frames) within about 10 frames after a kept word's end belongs to that word.

**Reviewer verdict on clip 087 after 3 rounds:** retakes, pauses, breaths and endings are approved; the end of the video is fixed in v6 (awaiting confirmation).

---

# Part 6: full episode (all clips)

The reviewer approved clip 087 v6 (*"this is perfect now"*). Now: the same pipeline on every clip, then one episode timeline.

## 22. Host-mic check for all recordings

Track1 sits at -59…-60 dB in every recording (unused), Track2 is the host: 373 -22.6, 374 -22.8, 375 -23.5, 376 -23.3, 378 -22.4 dB. **Exception: 377 averages -45.7 dB** (1:53 long, mostly silence with sporadic sounds).

## 23. Ingest and sync (`16_ingest.py`, bin `cop-episode`)

- Every recorder file is called `Track2-Combo 2.wav`, so in the media pool they're renamed to `<rec>-Track2.wav` (`SetClipProperty("Clip Name", …)`).
- The script asserts each camera clip's FPS equals the project's (all 25).
- `AutoSyncAudio` waveform results (offset in samples → camera_frame = wav_frame − offset/1920):

| Camera | Recorder | Frames | Resolve offset | **Independent check** (`17_xcorr_sync.py`) | conf. | offset_f used |
|---|---|---|---|---|---|---|
| P1011087 | 372 | 8520 | -18239 smp = +9.50 f | +0.378 s = **+9.44 f** | 8.6 | 10 (approved v6; 0.56 f / 22 ms off, analysis only) |
| P1011088 | 373 | 14388 | 62399 smp = -32.50 f | -1.300 s = **-32.51 f** | 5.5 | -33 |
| P1011089 | 374 | 10992 | -13919 smp = +7.25 f | +0.291 s = **+7.27 f** | 5.0 | 7 |
| P1011090 | 375 | 14040 | 62399 smp = -32.50 f | -1.302 s = **-32.56 f** | 6.0 | -33 |
| P1011091 | 376 | 9912 | -11040 smp = +5.75 f | +0.226 s = **+5.64 f** | 6.6 | 6 |
| P1011093 | 377 | 1848 | **sync failed** | no match with *any* recording (conf. ≤ 1.8) | – | – |
| P1011094 | 378 | 6876 | -10079 smp = +5.25 f | +0.205 s = **+5.12 f** | 7.3 | 5 |

- **Why an independent check:** the camera clip's transcript is made *through* the synced WAV, so it can't verify the sync. `17_xcorr_sync.py` decodes the camera's own scratch audio with ffmpeg and cross-correlates it with the recorder WAV (GCC-PHAT at 8 kHz). The confidence is the main peak divided by the best peak more than 50 ms away. Resolve agrees with it to within 0.1 frame on every pair.
- The identical -32.5 f offsets for 088 and 090 looked like a false match but are real: both recorders started 1.3 s after their cameras.
- **ffmpeg:** not on the system. Installed a pinned static build into the venv: `.venv/bin/pip install imageio-ffmpeg==0.6.0` (ffmpeg 7.0.2-static).
- Offsets aren't whole frames. For analysis they're rounded to the nearest frame. Playback in Resolve uses Resolve's own sub-frame sync, so rounding only affects where the planner *thinks* audio events are, by at most half a frame.
- **P1011093 has no recorder audio:** its camera scratch audio has speech (-25…-38 dB in 15 s bursts), while recorder 377 is near silence (-60 dB with a few -32…-45 dB blips). Most likely the recorder wasn't capturing the host mic during that take. To be checked from transcripts.

## 24. Batch transcription (`18_transcribe_batch.py`)

All six WAVs and six camera clips are queued with `TranscribeAudio`, then the script polls `GetTranscription()` per clip and writes `docs/spike/out/episode/<clip>-tr.json`. (Run in the background; results below.)

## 25. New tools for the episode
- `19_script_order.py`: maps each plan's kept text to a position in the read-aloud script (3-gram index; corrections table, headings, `[EKRAN]` lines and pronunciation hints removed). Reports the script range per clip, **script passages covered by more than one clip (cross-clip retakes)**, and script passages nobody said. On 087 it found script words 11–292 of 2453 = section "1. Açılış … COP31 neden bir dönüm noktası?". Correct.
- `20_build_episode.py`: builds one timeline from several plans in order. It adds Blue clip-boundary markers plus the per-cut markers, verifies durations, and disables the stereo camera-scratch tracks.

## 26. End hold 1 s → 500 ms (reviewer request)

*"Let's make the hold 500 ms instead of a second."* 500 ms at 25 fps is 12.5 frames. The planner keeps its params in whole frames, so the hold is defined as **500 ms rounded up**: `END_HOLD_F = ceil(500 * fps / 1000)` = **13 frames (520 ms)** at 25 fps, never shorter than requested. It still covers the late "k" release of "kavşak" (+8 f).

Plan `087-cutplan-v7.json`: last piece 7886–8479 → **7886–8467**, all other pieces identical; 8520 f → **5352 f (3:34:02)**. Timeline rebuild deferred until the batch transcription finishes (to avoid scripting Resolve while it's transcribing).

My call for the episode: each clip's last piece gets this hold. Clip boundaries coincide with script sections here, so a 13-frame pause there reads as a section break.

## 27. Batch transcription: Resolve runs ONE job at a time

The first batch (`TranscribeAudio` called on all 12 clips at once) returned `True` for the first clip and **`None` for the other 11**. Resolve doesn't queue transcription jobs: while one runs, further calls are refused. The script would have polled forever. Rewritten (`18_transcribe_batch.py`) to run **sequentially**: start one, retry `TranscribeAudio` until it returns True, poll until done, write the JSON; already-written outputs are skipped (resumable).

Timings (CPU, no NVIDIA GPU): WAVs 373: 140 s, 374: 120 s, 375: 140 s, 376: 135 s, 377: 30 s, 378: 60 s; camera clips 093: 40 s, 088: 165 s, 089: 135 s, 090: 120 s, 091: 100 s, 094: 55 s. **About 18 minutes for 12 files (about 72 min of audio).**

## 28. ASR hallucination on silence

- **Recorder 377** "transcript": `İzlediğiniz için teşekkür ederim.` **×7**, over a track that's near silence (-60 dB). This is the classic Whisper-style failure: the model invents a stock phrase when given silence. The same phrase appeared at the end of 372 (after the camera stopped) and at the end of 093. Probably invented every time.
- **Rule 0 (planner):** a word is dropped if < 10% of the frames under it (±2) are active (≥ -45 dB). It dropped the 12 invented words in 093, 2 in 088 and 1 in 089. 087's plan is unchanged.

## 29. Planning all clips, and a second over-cut problem

- **P1011093 has no recorder audio** (recorder 377 didn't capture the host). Its camera audio was extracted with ffmpeg (`P1011093-camera-audio.wav`, mono 48 kHz 24-bit) and used as the WAV, with offset 0 and its camera transcript as primary.
- First planning pass: **094 came out at 4:35 → 1:30**. Some retake cuts were **31 s and 51 s** long. Cause: **094's camera-clip transcript has no punctuation** (536 words in 5 segments), so R1's "go back to the sentence start" fallback ran all the way back to the previous cut. Clip 088 had 27 s and 20 s removals from first-word matches 20+ s back.
- **R1 safeguards (approved 087 unchanged):**
  1. Matching the restart: **first word within 10 s** (`NEAR_F`); **first two words** further back (up to 30 s).
  2. Fallback boundary = the nearer of sentence start and the **last real pause in the audio** (≥ 12 silent frames, `PAUSE_F`). Word gaps are useless when a transcript has back-to-back word timings.
  3. **Attempts longer than 15 s (`MAX_RETAKE_F`) are not removed.** Only the "bir daha" itself is cut, and the passage is flagged `long-retake-review` (**pink marker**). Principle: *a wrongly removed passage is worse than an extra take the editor deletes in two clicks.*
  4. R2b repeated-phrase window 20 s → **10 s**.
- Result: 3 review flags left (090 "Taslak metinleri…" 15 s, 091 "Bir diğer teknoloji…" 22 s, 094 "Paris anlaşması imzalandığında…" 22 s).
- Implementation bug along the way: the new `flags` variable was overwritten by a later local `flags` list, causing a crash. Renamed to `review_flags`.

| Clip | Source | Rough cut | Pieces |
|---|---|---|---|
| P1011087 | 8520 f (5:40:20) | 5352 f (3:34:02) | 31 |
| P1011088 | 14388 f (9:35:13) | 9586 f (6:23:11) | 65 |
| P1011089 | 10992 f (7:19:17) | 7299 f (4:51:24) | 42 |
| P1011090 | 14040 f (9:21:15) | 9871 f (6:34:21) | 59 |
| P1011091 | 9912 f (6:36:12) | 6263 f (4:10:13) | 34 |
| P1011093 | 1848 f (1:13:23) | 835 f (0:33:10) | 6, **excluded** (see 30) |
| P1011094 | 6876 f (4:35:01) | 4414 f (2:56:14) | 24 |

## 30. Script order and coverage (`19_script_order.py`)

- **The clips are in script order:** 087 §1 → 088 §2–3.1 → 089 "Dönüm noktası olan zirveler"–3.4 → 090 3.4–SKDM → 091 SKDM–"Bizim hayatımızda…" → 093/094 "Bizim hayatımızda…"–Kapanış.
- **Cross-clip retake: 093 → 094.** Both cover EVs, waste/plastics and product labels (script words 1880–1939), and 094 is the later take with proper audio. **093 is excluded from the episode** (last take wins; its audio is camera-mic only anyway).
- 088/089 "overlap" at script words 490–499 is **not** a retake. In 089 the host *refers back* ("COP28'de fosil yakıtlardan uzaklaşma kabul edilmişti", "Kayıp ve hasar fonu ise…"). It's a 3-gram coincidence. → Overlap reports need a human glance.
- "Uncovered" script blocks were checked against the *raw* transcripts. 3.4 and SKDM blocks are in the plans (artifacts of the tool's 5% edge-outlier trim). The rest is the **Kaynakça (bibliography), which isn't read aloud** (the tool should stop at that heading; noted). The closing lines are in 094.
- **Length:** about 3,590 kept spoken words against 2,453 in the script; the host adds explanation and asides. At about 2.1 words/s that's about **28.5 min against the writers' 11–13 min estimate**. Editorial call, not a cutting problem.

## 31. Episode timeline (`20_build_episode.py`)

**`COP31 episode rough v1`**: 087 (approved plan, 500 ms end hold) + 088 + 089 + 090 + 091 + 094.

- **255 pieces, all durations match the plans frame for frame; 42785 f = 28:31:10** (source 64728 f = 43:09:03 → 34% removed).
- V1 video; A1 camera scratch (stereo, disabled); A2 recorder WAV (mono).
- **93 markers**: Blue = clip boundary (with source → cut frame counts), Red = "bir daha" retake, Yellow = repeated phrase, Purple = orphan, Cyan = cut found only by the second transcript, **Pink = long retake kept, needs a decision**.
