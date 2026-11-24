# Kurgu Makinesi — Multi-Editor Implementation (Kdenlive, Shotcut, Premiere Pro, CapCut)

Drop-in multi-editor implementation extending [`gelecekbilimde/kurgu-makinesi`](https://github.com/gelecekbilimde/kurgu-makinesi) beyond DaVinci Resolve Studio to **Kdenlive**, **Shotcut** ([`mltframework/shotcut`](https://github.com/mltframework/shotcut)), **Adobe Premiere Pro**, and **CapCut Desktop**.

## What Was Added / Fixed

| Capability | Kdenlive (`.kdenlive`) | Shotcut (`.mlt`) | Premiere Pro (FCP7 `.xml`) | CapCut (Draft Folder) |
| :--- | :--- | :--- | :--- | :--- |
| **A-Roll (`V1`) + Camera Audio** | Yes + **A/V grouped** (`kdenlive:docproperties.groups`) | Yes (`playlist0`) | Yes + `<link>` A1/A2 | Yes (Video Track 0) |
| **Synced External WAV Audio** | `A2` track + grouped with `V1` (`offset_f`) | `A1` (`playlist3`) + `mix` | `A3`/`A4` stereo tracks | Audio Track 0 |
| **Multi-Track B-Roll (`V2`) & Overlays (`V3`)** | `V2` + `V3` with `qtblend` | `playlist1`/`playlist2` with `frei0r.cairoblend` & `qimage` stills | `V2` + `V3` tracks | Video Track 1 + Video Track 2 |
| **Color-Coded Point & Range Markers** | `guidesCategories` + `guides` JSON | `shotcut:markers:{n}` with hex color & start/end | Sequence `<marker>` with `<pproColor>` & `<in>`/`<out>` | `chapters.txt` + `markers.json` |
| **Marker Feedback Readback (`read-markers`)** | Reads Yellow guides → `edits.json` | Reads Yellow `shotcut:markers` → `edits.json` | Reads Yellow `<marker>` → `edits.json` | Reads Yellow `markers.json` → `edits.json` |
| **Per-Chapter Projects & Freeze/Unfreeze** | `--chapters`, `freeze`/`unfreeze` | `--chapters`, `freeze`/`unfreeze` | `--chapters`, `freeze`/`unfreeze` | `--chapters`, `freeze`/`unfreeze` |
| **Vertical Shorts (`1080x1920` + Face Crop + Captions)** | 9:16 profile + `qtblend` crop + `.srt` | 9:16 profile + `affine` crop + `.srt` | 9:16 sequence + Basic Motion crop + `.srt` | 9:16 canvas + `clip` scale/transform + native text track + `.srt` |

## Installation (Drop-In Overlay)

Copy `kurgu_makinesi.py` and `shared/` into the root of your `gelecekbilimde/kurgu-makinesi` clone (zero external Python dependencies beyond the standard library; `ffprobe` is optional and gracefully falls back to 25 fps / 1920×1080).

## Quick Usage

```bash
# 1. Build projects for all 4 editors (plus per-chapter files)
python3 kurgu_makinesi.py import cutplan.json --script script.md --format all --chapters --out build/

# README-compatible `make` alias also works:
python3 kurgu_makinesi.py make shotcut cutplan.json --script script.md --out build/

# 2. Freeze signed-off chapters before rebuilding
python3 kurgu_makinesi.py freeze 1 2 --out build/

# 3. Build 9:16 Vertical Shorts (with face crop & captions)
python3 kurgu_makinesi.py shorts short_plan.json --format all --out build/shorts/

# 4. Read Yellow edit-range markers back from an edited project into edits.json
python3 kurgu_makinesi.py read-markers build/shotcut/ep01.mlt --color Yellow --out edits/ep01-edits.json
```

## Notes & Caveats

- **Adobe Premiere Pro**: Uses Final Cut Pro 7 XML (`<xmeml version="4">`) imported via **File → Import** (native `.prproj` is proprietary).
- **CapCut Desktop**: `draft_content.json` targets unencrypted CapCut Desktop 5.x drafts. CapCut Desktop ≥ 6.0 encrypts newly saved drafts; `chapters.txt`, `markers.json`, and `<name>.srt` remain usable across versions.
- **Automated Verification**: Run `python3 -m unittest test_kurgu_multi_editor.py -v` to validate XML/JSON schemas, A/V grouping, external WAV sync, multi-track overlays, vertical shorts, freeze logic, and marker readback across all 4 editors.
