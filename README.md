# Kurgu Makinesi

Video editing automation for [Gelecek Bilimde](https://www.youtube.com/@GelecekBilimde), supporting **DaVinci Resolve Studio**, **Adobe Premiere Pro**, **Kdenlive**, **Shotcut**, and **CapCut**:

- **DaVinci Resolve Studio (Claude Code skills):** end-to-end automated editing directly inside Resolve — rough-cutting A-roll from camera + recorder WAVs with AI transcription, finding stock footage, rendering graphics, placing B-roll, and cutting vertical shorts. Every result is an ordinary Resolve timeline that the editor reviews, changes, and signs off.
- **Kdenlive, Shotcut, Adobe Premiere Pro & CapCut (`kurgu_makinesi.py` CLI):** editor-neutral multi-track project builder turning a cut plan into native project files with A-roll, synced external WAV audio, B-roll (`V2`), overlays (`V3`), color-coded point & range markers, marker feedback readback (`read-markers`), per-chapter freeze/unfreeze, and 9:16 vertical shorts with face crop and captions. See [Multi-editor CLI](#multi-editor-cli-kdenlive-shotcut-premiere-pro-capcut).

**Watch the demo (in Turkish):** [Claude Kurgu DEMO on YouTube](https://youtu.be/4Zj-HLRg2E4)

[![Claude Kurgu DEMO](https://i.ytimg.com/vi/4Zj-HLRg2E4/hqdefault.jpg)](https://youtu.be/4Zj-HLRg2E4)

## Supported editors

| Capability | DaVinci Resolve Studio | Kdenlive (`.kdenlive`) | Shotcut (`.mlt`) | Adobe Premiere Pro (FCP7 `.xml`) | CapCut Desktop (Draft Folder) |
|---|---|---|---|---|---|
| **Workflow** | Claude Code skills (live API) | `kurgu_makinesi.py` CLI | `kurgu_makinesi.py` CLI | `kurgu_makinesi.py` CLI | `kurgu_makinesi.py` CLI |
| **AI transcription & auto cut planning** | Yes (Resolve Studio AI) | Cut plan JSON | Cut plan JSON | Cut plan JSON | Cut plan JSON |
| **A-Roll (`V1`) + Camera Audio** | Yes | Yes + **A/V grouped** (`kdenlive:docproperties.groups`) | Yes (`playlist0`) | Yes + `<link>` A1/A2 | Yes (Video Track 0) |
| **Synced External WAV Audio** | Yes (waveform sync) | `A2` track + grouped with `V1` (`audio_offset_f`) | `A1` (`playlist3`) + `mix` | `A3`/`A4` stereo tracks | Audio Track 0 |
| **Multi-Track B-Roll (`V2`) & Overlays (`V3`)** | Yes (`placing-b-roll`) | `V2` + `V3` with `qtblend` | `playlist1`/`playlist2` with `frei0r.cairoblend` & `qimage` stills | `V2` + `V3` tracks | Video Track 1 + Video Track 2 |
| **Color-Coded Point & Range Markers** | Yes (native Resolve markers) | `guidesCategories` + `guides` JSON | `shotcut:markers:{n}` with hex color & start/end | Sequence `<marker>` with `<pproColor>` & `<in>`/`<out>` | `chapters.txt` + `markers.json` |
| **Yellow Marker Feedback Readback** | Yes (skills read Resolve markers) | `read-markers` → `edits.json` | `read-markers` → `edits.json` | `read-markers` → `edits.json` | `read-markers` → `edits.json` |
| **Per-Chapter Projects & Freeze/Unfreeze** | Yes (`episode.json`) | `--chapters`, `freeze`/`unfreeze` | `--chapters`, `freeze`/`unfreeze` | `--chapters`, `freeze`/`unfreeze` | `--chapters`, `freeze`/`unfreeze` |
| **Vertical Shorts (`1080×1920`, Crop, Captions)** | Yes (`cutting-shorts`) | 9:16 profile + `qtblend` crop + `.srt` | 9:16 profile + `affine` crop + `.srt` | 9:16 sequence + Basic Motion crop + `.srt` | 9:16 canvas + `clip` transform + native text track + `.srt` |
| **Stock Footage & HyperFrames Graphics** | Yes (standalone skills) | Yes (standalone skills) | Yes (standalone skills) | Yes (standalone skills) | Yes (standalone skills) |

## The skills

| Skill | What it does | Needs Resolve |
|---|---|---|
| [`rough-cutting-a-roll`](.claude/skills/rough-cutting-a-roll/SKILL.md) | Syncs camera clips with recorder WAVs, transcribes them, removes retakes, false starts and pauses, and builds one timeline per script chapter | yes |
| [`finding-stock-footage`](.claude/skills/finding-stock-footage/SKILL.md) | Searches Pixabay and NASA, downloads a few candidates and collects the credits | no (works for all editors) |
| [`making-graphics`](.claude/skills/making-graphics/SKILL.md) | Renders title cards, numbers, charts, name lines and other overlays from HyperFrames templates | no (works for all editors) |
| [`placing-b-roll`](.claude/skills/placing-b-roll/SKILL.md) | Fills the script's B-roll rows with stock, graphics and source screenshots, over signed-off A-roll chapters | yes |
| [`cutting-shorts`](.claude/skills/cutting-shorts/SKILL.md) | Cuts 30-45 s vertical shorts from signed-off chapters, with face crop, captions, teaser and end card | yes |

The skills are built for Turkish teleprompter shoots at 25 fps, with scripts written in the [script template](templates/script/README.md).

## Requirements

### DaVinci Resolve (for the automated Resolve skills)
- **DaVinci Resolve Studio 21.2 or newer.** The free edition is not enough: the Resolve skills use external scripting and Resolve's AI transcription, which are Studio features.
- Resolve runs on the same machine as Claude Code, with the episode's project open.
- About 1-2 GB for the *Extended AI Transcription Language Support 2* Extras package, which Turkish needs. The rough cutter installs it the first time (step 3 of [the A-roll](#2-rough-cut-the-a-roll)).

### Other editors (Kdenlive, Shotcut, Adobe Premiere Pro, CapCut)
- **Python 3.11 or newer** — `kurgu_makinesi.py` uses only the Python standard library (zero external Python dependencies).
- **FFprobe** (optional) — reads clip duration, frame rate, resolution, and audio streams; falls back cleanly to 25 fps / 1920×1080 if unavailable.
- Any of **Kdenlive**, **Shotcut**, **Adobe Premiere Pro**, or **CapCut Desktop** to open the generated projects.

### Other software

| Software | Used by |
|---|---|
| [Claude Code](https://claude.com/claude-code) | skills |
| Python 3 (developed and tested with 3.12) with `venv` | everything (`kurgu_makinesi.py` needs only stdlib) |
| Node.js 22 or newer, with npm | graphics, B-roll, shorts |
| FFmpeg and FFprobe | graphics, B-roll, shorts (optional for `kurgu_makinesi.py`) |
| fontconfig (`fc-match`) | B-roll and shorts placeholders |
| A free [Pixabay API key](https://pixabay.com/api/docs/) | stock, B-roll (NASA needs no key) |
| DaVinci Resolve Studio, Kdenlive, Shotcut, Adobe Premiere Pro, or CapCut | opening and editing timelines/projects |

### Operating system
Developed and tested on Linux. `rv.sh` also knows Resolve's default paths on macOS, but macOS and Windows are untested.

## Setup

Run everything from the repo root.

**1. Clone the repo.**
```bash
git clone https://github.com/gelecekbilimde/kurgu-makinesi.git
cd kurgu-makinesi
```

**2. Let scripts talk to Resolve.** In Resolve Studio, open *Preferences › System › General* and set *External scripting using* to **Local**. Open a project, then check the connection:
```bash
bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh -c \
  "import DaVinciResolveScript as d; r = d.scriptapp('Resolve'); print(r.GetProductName(), r.GetVersionString()) if r else print('Resolve not reachable')"
```
It should print the product name and version. If Resolve is installed somewhere unusual, set `RESOLVE_SCRIPT_API` and `RESOLVE_SCRIPT_LIB` (the defaults are in [`rv.sh`](.claude/skills/rough-cutting-a-roll/scripts/rv.sh)). `RESOLVE_PYTHON` picks another Python.

**3. Install the Python packages** for the audio analysis and the shorts' face crop:
```bash
python3 -m venv .venv
.venv/bin/pip install -r .claude/skills/rough-cutting-a-roll/requirements.txt \
                      -r .claude/skills/cutting-shorts/requirements.txt
```
The first short also downloads two small mediapipe models.

**4. Install FFmpeg, then set up the graphics renderer.** On Fedora/RHEL-like systems FFmpeg comes from [RPM Fusion](https://rpmfusion.org/Configuration) (`sudo dnf install ffmpeg`).
```bash
python3 .claude/skills/making-graphics/scripts/setup.py
```
It checks Node and FFmpeg, installs the pinned HyperFrames and its Chrome, and lists anything missing (messages are in Turkish). `Hazır: …` means you're done.

**5. Set the Pixabay key** in your shell profile, then open a new terminal:
```bash
export PIXABAY_API_KEY="your-key"
```
Pexels is supported but turned off; see the [stock skill](.claude/skills/finding-stock-footage/SKILL.md#sources-and-cache).

**6. Start Claude Code** in the repo root. It finds the skills in `.claude/skills/` by itself.
```bash
claude
```

The channel's brand pack isn't in git and isn't needed to run the skills. Team members can download it with `./scripts/fetch-assets.sh fetch`, which asks for the archive link.

## Using the skills

Tell Claude what you want, in Turkish or English; it picks the skill and runs the scripts. You can also name a skill yourself, for example `/rough-cutting-a-roll`. The sections below follow one episode from script to shorts. Stock footage and graphics also work on their own, without an episode.

Only signed-off ("frozen") work moves on: **A-roll → B-roll → shorts**.

### 1. Prepare the episode

1. Write the script in a copy of the [script template](templates/script/README.md), then download it as `.docx`.
2. Make a folder `episodes/<slug>/` and put the file there as `script.docx`. Git ignores `episodes/`.
3. Unzip the raw footage outside the repo or under `demo/`, which git also ignores.
4. Create a project in Resolve and leave it open. **Don't create a timeline yet:** the frame rate can't be changed afterwards.
5. Ask Claude to write `episodes/<slug>/episode.json`, or write it yourself:

```json
{
  "prefix": "COP31",
  "title": "The episode title, shown on the shorts' end card",
  "fps": 25,
  "language": "tr",
  "script": "script.txt",
  "speaker": "Name of the person on camera",
  "frozen": [],
  "clips": [
    {"clip": "P1011087.MOV", "bin": "cop31",
     "camera": "/path/to/P1011087.MOV",
     "recorder": "/path/to/372/Track2-Combo 2.wav"}
  ]
}
```
List the clips in script order. `recorder` is the host's microphone track. All fields are described in [`episode.py`](.claude/skills/rough-cutting-a-roll/scripts/episode.py).

### 2. Rough-cut the A-roll

> Rough-cut the A-roll of episodes/cop31. The footage is in demo/cop.

Claude then:
1. pairs the camera clips with the recorder files and asks you when a pairing is unclear;
2. reads the script;
3. sets the project's frame rate and Turkish transcription;
4. imports, syncs and transcribes the clips, and checks the sync independently;
5. plans the cuts and builds one timeline per chapter, plus a master.

**Review in Resolve.** The engine removes only what it is sure of and marks the rest:

| Marker | Meaning |
|---|---|
| Fuchsia range | suggested cut, not removed |
| Pink range | retake longer than 30 s, not removed |
| Red, Rose, Purple | where something was removed |
| **Yellow range** | **yours: remove this range** |

Add Yellow ranges, or recolour a Fuchsia one to Yellow. The end of the range is where the good take starts. Then:

> Apply my markers on chapter 2 and rebuild it.

> Chapter 2 is done, freeze it.

A frozen chapter is never rebuilt.

### 3. Place the B-roll

> Place the B-roll for the frozen chapters of episodes/cop31.

Each chapter gets a new `… B-roll` timeline with the frozen chapter nested on V1, full-screen B-roll on V2 and overlays on V3. The script's tags decide what goes in: `[STOK]` stock, `[GRAFİK]` and `[YAZI]` graphics, `[KAYNAK]` source screenshots, `[ARŞİV]` a placeholder for past footage. Anything that can't be filled stays visible as a placeholder with a Lavender marker.

Move, trim, swap or delete anything you like; rebuilding keeps your changes. Unused stock candidates are in the bin `<prefix> B-roll/ch<N>/<row id>`. When you're happy:

> Freeze the B-roll of chapter 2 and build the B-roll master.

The credits for the video description are in `episodes/<slug>/broll/kaynaklar.txt`.

### 4. Cut the shorts

Shorts come only from chapters with both A-roll and B-roll frozen, and `episode.json` needs a `"title"`.

> Find short candidates in episodes/cop31.

Claude builds a review timeline, `<prefix> short adayları`, with Fuchsia ranges. Turn a candidate's marker **Green** to accept it, and move or resize its ranges to change the passage. Then:

> I accepted the shorts I want, build them.

Each short is a 1080x1920 timeline with a teaser, captions, the episode's B-roll and an end card. Edit it freely. Two things are done by hand for now: the subtitle style, and the watermark's size and animation.

> Freeze short c1.

### Stock footage and graphics on their own

> Find rocket launch footage for a vertical short.

> Make a number graphic: 10^67 yıl, "Kara deliklerin buharlaşma süresi", source NASA.

Files go to `~/Downloads/stok/` and `~/Downloads/grafik/`, each with a `kaynaklar.txt` for the credits. Graphics are transparent ProRes 4444 overlays unless you ask for a background. To design a new template or look, ask Claude for one; it follows the [design workflow](.claude/skills/making-graphics/references/design-workflow.md) and leaves the design decisions to you. The `starter` design is an example, not the channel's approved look.

## Multi-editor CLI (Kdenlive, Shotcut, Premiere Pro, CapCut)

`kurgu_makinesi.py` turns a **cut plan JSON** (and optional script) into multi-track projects for **Kdenlive**, **Shotcut**, **Adobe Premiere Pro**, and **CapCut Desktop** — no DaVinci Resolve required. It uses only the Python standard library (Python 3.11+); FFprobe is optional and gracefully falls back to 25 fps / 1920×1080 when unavailable.

It supports sequential A-roll on `V1`, synced external recorder WAVs, multi-track B-roll (`V2`) and graphics/text overlays (`V3`), color-coded point & range markers using the same palette as the Resolve skills, per-chapter splitting with `freeze`/`unfreeze` state, 9:16 vertical Shorts with face crop & `.srt`/native captions, and round-trip Yellow marker readback into `edits.json`.

### Quick usage

Try it right away with the bundled [`examples/sample_cutplan.json`](examples/sample_cutplan.json) and [`examples/sample_script.md`](examples/sample_script.md):

```bash
# 1. Build projects for all 4 editors (plus per-chapter files)
python3 kurgu_makinesi.py import examples/sample_cutplan.json \
  --script examples/sample_script.md --format all --chapters --out build/

# Shorthand `make` alias for a single editor:
python3 kurgu_makinesi.py make shotcut examples/sample_cutplan.json \
  --script examples/sample_script.md --out build/

# 2. Freeze signed-off chapters before rebuilding (stored in build/.kurgu_frozen.json)
python3 kurgu_makinesi.py freeze 1 2 --out build/
python3 kurgu_makinesi.py unfreeze 2 --out build/

# 3. Build 9:16 Vertical Shorts (1080x1920, face crop & captions)
python3 kurgu_makinesi.py shorts short_plan.json --format all --out build/shorts/

# 4. Read Yellow edit-range markers back from an edited project into edits.json
python3 kurgu_makinesi.py read-markers build/shotcut/gb_ep01_ornek.mlt \
  --color Yellow --out edits/ep01-edits.json

# 5. List script files (.txt, .md, .rst, .html) and their chapters / B-roll tags
python3 kurgu_makinesi.py list examples/
```

### CLI options

| Command / Option | Meaning |
|---|---|
| `import <cutplan.json>` | Build project file(s) from a cut plan (`--format`, `--script`, `--out`, `--name`, `--chapters`, `--freeze`, `--vertical`) |
| `make <editor> <cutplan.json>` | Alias for `import <cutplan.json> --format <editor>` (`kdenlive`, `shotcut`, `premiere`, `capcut`, `all`) |
| `shorts <plan.json>` | Build 1080×1920 vertical Shorts with per-clip face crop and `.srt` (plus native CapCut) captions |
| `read-markers <project>` | Read Yellow (or `--color all`) point/range markers back from `.kdenlive`, `.mlt`, `.xml`, or a CapCut draft folder into `edits.json` |
| `freeze` / `unfreeze <chapters...>` | Mark 1-based chapter numbers as frozen/unfrozen in `<out>/.kurgu_frozen.json` so `--chapters` rebuilds skip signed-off chapters |
| `list [DIR]` | List script files (`.txt`, `.md`, `.rst`, `.html`) and their `## ` chapters and `[STOK]`/`[GRAFİK]`/`[YAZI]`/`[KAYNAK]`/`[ARŞİV]` tags |

### The cut plan

See [`examples/sample_cutplan.json`](examples/sample_cutplan.json) for a full multi-track example:

```json
{
  "name": "gb_ep01_ornek",
  "fps": 25, "width": 1920, "height": 1080,
  "clips": [
    {
      "file": "media/cam_A001.mp4",
      "in": 4.0, "out": 14.0,
      "chapter": 1, "subsection": "Problem Tanımı",
      "external_audio": "media/rec_001.wav",
      "audio_offset_f": 12
    }
  ],
  "broll": [
    {"file": "stock/earth_orbit.mp4", "timeline_in": 3.0, "in": 1.0, "duration": 5.0, "kind": "STOK", "label": "Uzaydan Dünya"}
  ],
  "overlays": [
    {"file": "graphics/title_card.png", "timeline_in": 1.0, "duration": 3.5, "kind": "GRAFIK", "label": "Başlık Kartı"}
  ],
  "markers": [
    {"time": 8.0, "duration": 2.0, "name": "Tekrar cümle önerisi", "color": "Fuchsia", "note": "Kısaltılabilir"},
    {"time": 24.0, "duration": 3.0, "name": "Editör kesim aralığı", "color": "Yellow", "note": "Bu aralığı çıkar"}
  ],
  "captions": [
    {"start": 0.5, "end": 3.5, "text": "Gelecek Bilimde'ye hoş geldiniz."}
  ]
}
```

- `clips`: sequential A-roll clips on `V1`. Supports seconds (`in`/`out`) or integer frames (`in_f`/`out_f`), optional `chapter` (1-based index into script `## ` headings, or title string), `subsection`, `external_audio` (with frame-accurate `audio_offset_f`), and `crop` (`x`, `y`, `scale`, `center_x`, `center_y` for 9:16 shorts).
- `broll` (`V2`) and `overlays` (`V3`): placed at `timeline_in` (seconds) with `duration` or `in`/`out`, optional `kind` (`STOK`, `GRAFIK`, `YAZI`, `KAYNAK`, `ARŞİV`), `opacity`, and `crop`. Still images (`.png`, `.jpg`, `.webp`, etc.) are handled automatically.
- `markers`: point (`duration: 0`) or range markers using the shared Kurgu Makinesi color palette (`Green`, `Sky`, `Blue`, `Red`, `Rose`, `Purple`, `Cyan`, `Fuchsia`, `Pink`, `Yellow`, `Lavender`).
- `captions`: timed caption items exported as sidecar `<name>.srt` across all editors (and as a native text track in CapCut).
- `frozen_chapters`: optional list of chapter numbers to skip when exporting with `--chapters`.

### Notes & caveats per editor

- **Kdenlive (`.kdenlive`):** A/V pairs and synced external WAV tracks are grouped via `kdenlive:docproperties.groups`; uses `qtblend` for `V2`/`V3` overlays and vertical crop, and `guidesCategories` + `guides` JSON for color-coded markers.
- **Shotcut (`.mlt`):** Uses `playlist0`–`playlist3` with `mix` for synced external audio, `frei0r.cairoblend` & `qimage` stills for B-roll/overlays, `affine` for 9:16 face crop, and `shotcut:markers:{n}` with hex colors and start/end ranges.
- **Adobe Premiere Pro (`.xml`):** Uses Final Cut Pro 7 XML (`<xmeml version="4">`) imported via **File › Import** (native `.prproj` is proprietary). Links A1/A2 with `<link>`, places synced WAVs on A3/A4, overlays on V2/V3, Basic Motion for 9:16 crop, and `<marker>` with `<pproColor>`.
- **CapCut Desktop (`<name>/` draft folder):** Writes `draft_content.json`, `draft_meta_info.json`, `chapters.txt`, `markers.json`, and `<name>.srt` (plus a native text track for captions). `draft_content.json` targets unencrypted CapCut Desktop 5.x drafts; CapCut Desktop ≥ 6.0 encrypts newly saved drafts, while `chapters.txt`, `markers.json`, and `.srt` remain usable across versions.

Automated tests verify XML/JSON schemas, A/V grouping, external WAV sync, multi-track overlays, vertical shorts, freeze logic, and marker readback across all 4 editors. Still open generated projects in your target editor and report any version-specific quirks.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Resolve not reachable` or `No module named DaVinciResolveScript` | Resolve Studio must be running with *External scripting* set to Local. Run Resolve scripts through `rv.sh`, not plain `python3`. |
| The transcript is English nonsense | `resolve_setup.py` hasn't run on this project, so the language isn't set to Turkish |
| The timeline is 24 fps | A timeline existed before `resolve_setup.py`. Start from a new project. |
| `PIXABAY_API_KEY yok` | Open a new terminal, or run `source ~/.bashrc` |
| `HyperFrames kurulu değil` | Run the graphics `setup.py` again |
| "render path inaccessible" when rendering in Resolve | Choose a folder under `~/Videos` (seen on Linux) |

Each skill's `SKILL.md` lists its common mistakes. The rough cutter, B-roll and shorts skills also have a `reference.md` with file formats and Resolve API notes.

## Repository layout

| Path | Contents |
|---|---|
| `.claude/skills/` | the DaVinci Resolve & standalone Claude Code skills, their scripts and tests |
| `kurgu_makinesi.py`, `shared/`, `test_kurgu_multi_editor.py` | the Kdenlive / Shotcut / Premiere Pro / CapCut multi-editor builder, marker readback, and tests |
| `examples/` | sample multi-track cut plan (`sample_cutplan.json`) and script (`sample_script.md`) |
| `templates/script/` | the script template for writers and its reader |
| `graphics/` | designs and graphic templates |
| `docs/` | specs, plans and the development log |
| `episodes/`, `demo/`, `assets/` | local working data, not in git |

Run the tests (Resolve, FFmpeg, and network not needed):
```bash
for d in .claude/skills/*/tests templates/script/tests; do python3 -m unittest discover -s "$d"; done
python3 -m unittest test_kurgu_multi_editor.py -v
```

## License

Copyright (c) 2026 Gelecek Bilimde. The code and documentation are under the [GNU General Public License](LICENSE), version 3 or any later version (GPL-3.0-or-later): if you distribute this project or a modified version, you must share its source under the same license.

Two additional permissions apply (full wording in [NOTICE](NOTICE)):

- **DaVinci Resolve:** you may combine the project with Resolve and its scripting library, and share the result.
- **Your output is yours:** videos, graphics, subtitles and timelines you make with the project are not under the GPL, even when they use its templates.

The GPL and these permissions don't cover:

- **The Gelecek Bilimde name and logo** are the intellectual property of Gelecek Bilimde, all rights reserved. If you use this project for your own channel, replace them with your own.
- **The fonts** in `graphics/designs/starter/fonts/` are under the SIL Open Font License (`OFL.txt` next to each font).
- **The reference photo** `graphics/designs/starter/reference/rocket.jpg` (credit: NASA / Rocket Lab) is a still from NASA's [Rocket Lab PREFIRE-1 Launch](https://images.nasa.gov/details/KSC-20240525-MH-RKL01-0001-Rocket_Lab_PREFIRE_1_Launch_1080p-M6988) video, used only as a sample background in the design reference pages. It isn't ours to license, so check the rights before reusing it.

Stock clips you download stay under their source's license.
