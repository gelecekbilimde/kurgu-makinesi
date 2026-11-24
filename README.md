# Kurgu Makinesi

Claude Code skills that edit [Gelecek Bilimde](https://www.youtube.com/@GelecekBilimde) videos in DaVinci Resolve Studio: rough-cutting the A-roll, finding stock footage, rendering graphics, placing B-roll and cutting vertical shorts. Every result is an ordinary Resolve timeline that the editor reviews, changes and signs off.

The skills need DaVinci Resolve. Separately, a small command-line tool writes a rough-cut project for **Kdenlive, Shotcut, Adobe Premiere Pro and CapCut** from a cut plan: see [Other editors](#other-editors-kdenlive-shotcut-premiere-capcut).

**Watch the demo (in Turkish):** [Claude Kurgu DEMO on YouTube](https://youtu.be/4Zj-HLRg2E4)

[![Claude Kurgu DEMO](https://i.ytimg.com/vi/4Zj-HLRg2E4/hqdefault.jpg)](https://youtu.be/4Zj-HLRg2E4)

## The skills

| Skill | What it does | Needs Resolve |
|---|---|---|
| [`rough-cutting-a-roll`](.claude/skills/rough-cutting-a-roll/SKILL.md) | Syncs camera clips with recorder WAVs, transcribes them, removes retakes, false starts and pauses, and builds one timeline per script chapter | yes |
| [`finding-stock-footage`](.claude/skills/finding-stock-footage/SKILL.md) | Searches Pixabay and NASA, downloads a few candidates and collects the credits | no |
| [`making-graphics`](.claude/skills/making-graphics/SKILL.md) | Renders title cards, numbers, charts, name lines and other overlays from HyperFrames templates | no |
| [`placing-b-roll`](.claude/skills/placing-b-roll/SKILL.md) | Fills the script's B-roll rows with stock, graphics and source screenshots, over signed-off A-roll chapters | yes |
| [`cutting-shorts`](.claude/skills/cutting-shorts/SKILL.md) | Cuts 30-45 s vertical shorts from signed-off chapters, with face crop, captions, teaser and end card | yes |

The skills are built for Turkish teleprompter shoots at 25 fps, with scripts written in the [script template](templates/script/README.md).

## Requirements

### DaVinci Resolve
- **DaVinci Resolve Studio 21.2 or newer.** The free edition is not enough: the skills use external scripting and Resolve's AI transcription, which are Studio features.
- Resolve runs on the same machine as Claude Code, with the episode's project open.
- About 1-2 GB for the *Extended AI Transcription Language Support 2* Extras package, which Turkish needs. The rough cutter installs it the first time (step 3 of [the A-roll](#2-rough-cut-the-a-roll)).

### Other software

| Software | Used by |
|---|---|
| [Claude Code](https://claude.com/claude-code) | everything |
| Python 3 (developed and tested with 3.12) with `venv` | everything |
| Node.js 22 or newer, with npm | graphics, B-roll, shorts |
| FFmpeg and FFprobe | graphics, B-roll, shorts |
| fontconfig (`fc-match`) | B-roll and shorts placeholders |
| A free [Pixabay API key](https://pixabay.com/api/docs/) | stock, B-roll (NASA needs no key) |

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

## Other editors (Kdenlive, Shotcut, Premiere, CapCut)

`kurgu_makinesi.py` turns a **cut plan** into a project file for another editor. It needs only Python 3.11 or newer; FFprobe is optional but recommended (it reads each file's length, frame rate, size and audio, and rejects cuts past the end of a file). It doesn't use Resolve, and it doesn't transcribe or decide cuts: you give it the cuts, it lays them end to end on one video track with its audio and puts a marker at each chapter.

```bash
python3 kurgu_makinesi.py import plan.json --script script.md --format all --out out/
```

| Option | Meaning |
|---|---|
| `--format` | `kdenlive`, `shotcut`, `premiere`, `capcut` or `all` (default) |
| `--script` | a script whose `## ` headings name the chapters (see below) |
| `--out` | output folder (default: current folder) |
| `--name` | project name (default: the plan's `name`) |

`python3 kurgu_makinesi.py list [DIR]` lists script files (`.txt`, `.md`, `.rst`, `.html`) under a folder.

### The cut plan

```json
{
  "name": "cop31-ch1",
  "fps": 25, "width": 1920, "height": 1080,
  "clips": [
    {"file": "cam1.mp4", "in": 1.0, "out": 3.0, "chapter": 1},
    {"file": "cam1.mp4", "in": 4.0, "out": 6.5, "chapter": 1},
    {"file": "cam1.mp4", "in": 7.0, "out": 9.0, "chapter": "Outro"}
  ]
}
```

- `in` and `out` are seconds in the source file. `out` may be left out to use the end of the file (needs FFprobe).
- `file` is relative to the plan's folder, or absolute.
- `chapter` is a 1-based number into the script's `## ` headings, or a title. A marker is placed where it changes.
- `fps`, `width` and `height` default to the first clip's values (or 25 fps, 1920x1080 without FFprobe).
- Problems (missing `clips`, `in` not below `out`, a cut past the end of the file, bad JSON) stop with a one-line error. A file FFprobe can't read is only a warning.

### What each editor gets

| Editor | File | Chapters | Status |
|---|---|---|---|
| Shotcut | `<name>.mlt` | timeline markers | written to Shotcut's own layout, not opened in Shotcut |
| Kdenlive | `<name>.kdenlive` | guides | Kdenlive's document version 1.04, which Kdenlive upgrades on load; not opened in Kdenlive. Audio and video are not grouped: group them in Kdenlive if you want them to move together |
| Premiere Pro | `<name>.xml` | sequence markers | Final Cut Pro 7 XML (xmeml v4): use *File › Import*; not opened in Premiere. A native `.prproj` isn't written because its format is undocumented |
| CapCut | `<name>/` folder | `chapters.txt` (no markers) | **experimental**: CapCut has no documented import format, newer versions encrypt drafts, and it hasn't been tried in CapCut |

Tests check the generated files' structure (timing, ids, markers, links) and that the XML is well-formed. They can't tell whether an editor accepts the file, so open the result and report anything that doesn't load.

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
| `.claude/skills/` | the skills, their scripts and tests |
| `kurgu_makinesi.py`, `shared/`, `test_kurgu.py` | the Kdenlive / Shotcut / Premiere / CapCut writer and its tests |
| `templates/script/` | the script template for writers and its reader |
| `graphics/` | designs and graphic templates |
| `docs/` | specs, plans and the development log |
| `episodes/`, `demo/`, `assets/` | local working data, not in git |

Run the tests (Resolve and network not needed):
```bash
for d in .claude/skills/*/tests templates/script/tests; do python3 -m unittest discover -s "$d"; done
python3 -m unittest test_kurgu    # the other-editors writer; needs FFmpeg
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
