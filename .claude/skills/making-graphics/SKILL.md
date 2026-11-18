---
name: making-graphics
description: Use when an editor wants a graphic for a video or short - a title card, number callout, bar chart, name line (isim altyazısı), logo or watermark, any motion graphic or overlay ("bölüm başlığı grafiği", "10^67 yıl vurgusu", "isim altyazısı") - when the B-roll skill needs GRAFİK rows rendered, or when an editor wants to create or change the channel's graphic design or templates with HyperFrames.
---

# Making graphics

## Overview
Graphics are rendered by a deterministic script from **templates** (HyperFrames compositions with a `template.json`) of the active **design** under `graphics/`. A render request becomes one `make_graphic.py` call with named fields; you never write HTML/CSS to fulfil a render. Designing (a new look, a new template) is a separate path, run with the editor, where every design decision is theirs.

Two paths:
- **Render path:** the editor wants a graphic. Use an existing template.
- **Design path:** the editor wants a new look or a new kind of graphic, or no template fits. Read `references/design-workflow.md` and follow it.

## Render path
1. **List** the templates of the active design and their fields:
   ```
   python3 .claude/skills/making-graphics/scripts/make_graphic.py --list --json
   ```
2. **Pick** the template whose description fits. If none fits, say so plainly and offer the design path. Do not improvise a one-off graphic.
3. **Render** with one `--set field=value` per field (repeat `--set` for list fields, e.g. `--set bars=2024=425 --set bars=2020=414`):
   ```
   python3 .claude/skills/making-graphics/scripts/make_graphic.py number --set value=10^67 --set unit=yıl \
       --set "explanation=Kara deliklerin buharlaşma süresi" --set source=NASA
   ```
   - Numbers as the editor writes them: `3,7`, `1.234.567`, `10^67`.
   - Series look: `--variant uzay|diyalog|kurgu|muhendislik|notlar|ev` (see `graphics/designs/<design>/variants/`).
   - Short (9:16): `--vertical` (if the template supports it). Length: `--frames N` (frames, never seconds; default per template, 25 fps).
   - Output: a transparent ProRes 4444 `.mov` that overlays any footage in Resolve (no keying). `--background` gives an `.mp4` on the design's page instead. Still templates (e.g. watermark `state=static`) give a transparent `.png`.
   - `--out DIR` (default `~/Downloads/grafik/<template>-<slug>/`), `--code G12`, `--resolution 1080p` for a quick draft, `--fresh` to ignore the archive.
4. **Report** to the editor: the folder, each output line (code, file, frames, size, `arşivden` if reused) and `kaynaklar.txt` (every `source` field, ready for the video description). Name the optional fields you left empty (e.g. a `hand` note) so the editor can ask for them, and if the active design is `starter`, say it is the example design. On exit code 2 (`Geçersiz istek`), relay the listed problems and ask for the missing or shorter text; don't guess content.

## For the B-roll skill
```
python3 .claude/skills/making-graphics/scripts/make_graphic.py --batch rows.json --out episodes/<ep>/broll/grafik/
```
`rows.json` is `[{"template": "number", "code": "G12", "fields": {"value": "10^67", "source": "NASA"}, "variant"?, "vertical"?, "frames"?, "background"?}, ...]`; list fields take a JSON list. The result is `results.json` in `--out`: `{"created", "notes", "renders": [{"code", "file", "template", "version", "design", "variant", "vertical", "frames", "fps", "resolution", "output", "background", "values", "sources", "from_archive", "archive_id"}]}`. A bad row is reported in `notes` and the other rows still render. Files are never replaced; numbering continues.

## Setup
`python3 .claude/skills/making-graphics/scripts/setup.py` checks Node 22, FFmpeg and FFprobe, installs the pinned HyperFrames (`npm ci`) and its Chrome, and turns telemetry off. It never runs sudo: if it reports FFmpeg missing, tell the editor to run `sudo dnf install ffmpeg` (RPM Fusion) in their own terminal.

## Designs, templates, archive
- `graphics/config.json` names the active design. `graphics/designs/starter/` is the **starter example** from the first design session, not the channel's approved design; say so if an editor treats it as final.
- Templates: `graphics/templates/<design>/<template>/` (`index.html`, `template.json`, `samples.json`). The manifest format and the kit are in `references/template-contract.md`.
- Every render is archived in `assets/graphics/<template>/<id>/` (`vars.json` is the truth; `--reindex` rebuilds `index.json`). The same request reuses its render; any change to the design re-renders.
- Review tools: `--samples <template>` (all samples + `contact.png`), `--showcase` (one page of every template), `--preview <template>` (HyperFrames Studio in the browser; `--stop-preview <template>`).
