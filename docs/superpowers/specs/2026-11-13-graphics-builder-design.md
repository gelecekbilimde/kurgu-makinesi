# Graphics builder: design

Status: rewritten 2026-11-18 after a scope change. Pending document review.
Skill name: `making-graphics` (sibling of `finding-stock-footage`).

## Intent

Gelecek Bilimde has never had per-episode graphics, and its brand assets (series intros, outros, social overlays, watermark) each speak a different visual language. Editors will fix that. This project gives them the means to.

**The repo ships the framework, and editors own the design.**
- The skill finalises no colours, fonts, layouts or motion.
- It gives editors working in Claude Code what they need to:
  - decide a design language;
  - turn their decisions into reusable HyperFrames templates;
  - render B-roll graphics from those templates by tool call.

The rule from the stock finder carries over to rendering:
- Deterministic scripts do the work, and the LLM only translates a request into a tool call.
- Once a template exists, a request like "a number callout: 10^67 years…" becomes a `make_graphic.py` call with named fields. Nobody rewrites HTML per request, so the same inputs always give the same video.
- Writing HTML is reserved for the design workflow, when an editor creates or changes a template on purpose.

The skill is one of the small, separately callable skills that the B-roll skill will later compose. The B-roll skill picks from whatever templates exist and fills their fields. It never designs.

## Goals

- **Setup:** a pinned local HyperFrames install, plus the checks an editor needs to get it running.
- **Design workflow:** a documented way for an editor and Claude Code to explore and decide a design language. It covers browser mockups, side-by-side options, previews of real templates with sample data, and recording the rulings in editor-owned files.
- **Template contract:** a manifest format that makes any HyperFrames composition a renderable template with named, validated fields. A scaffold command creates one.
- **Generic render CLI:** it works for any template that meets the contract. Output, archive and credits work as in the finder.
- **Review tooling:** sample renders, contact sheets and a showcase page, for any design and template set.
- **A starter example:** the design explored in the 2026-11-13 brainstorm, shipped as an editable and clearly labelled example. It proves every framework feature end to end, and editors may change it or throw it away.

## Non-goals (this project)

- Deciding the channel's design language. That is the editors' job, done with this framework.
- Series intros, outros, social overlays and the subscribe reminder. Editors build those with the skill later.
- Placing graphics in Resolve. The B-roll skill does that.
- macOS and Windows. Linux only for now, as in the finder.

## Anti-goals

- **Design rules inside framework code.** No colour, font, size or easing is hardcoded in the CLI, the engine helpers or SKILL.md. Every visual value lives in a design's files.
- **HTML at render time.** An LLM writing or editing HTML/CSS to fulfil a render request is out. When no template fits, Claude says so and offers the design workflow; it doesn't improvise a one-off.
- **Leaving the machine.** No cloud rendering, no HeyGen accounts, no HyperFrames telemetry. Nothing about the project or the user leaves the machine.
- **A starter that looks final.** The starter must not read as the channel's approved design. Its folder name, README and every sample say "starter example".

## Concepts

- **Design.** One editor-owned folder of visual decisions:
  - tokens (colours, fonts, sizes, motion timings) as CSS custom properties;
  - the bundled fonts with their licences;
  - optional **variants**, which are named token overrides (for example one per series);
  - a `design.md` where the editors record their rulings and why.
- **Template.** A HyperFrames composition plus a `template.json` manifest. It belongs to one design.
  - It reads visual values only through the design's CSS custom properties, so editing tokens or switching the variant restyles it without touching its HTML.
  - It may use the design's assets (a logo SVG, motifs).
- **Render.** One call that fills a template's fields, picks a variant and orientation, and produces a clip or still.

## Layout in the repo

| Path | Owner | Contents |
|---|---|---|
| `.claude/skills/making-graphics/` | framework | SKILL.md, `scripts/` (Python CLI, setup, engine helpers JS), `package.json` + lock pinning HyperFrames, reference docs (design workflow, template contract), tests |
| `graphics/designs/<design>/` | editors | `tokens.css`, `variants/<variant>.css`, `fonts/` + licence files, `assets/`, `design.md` |
| `graphics/templates/<design>/<template>/` | editors | `index.html` (composition), `template.json`, `samples.json` |
| `graphics/config.json` | editors | the active design and default variant |
| `assets/graphics/` | generated | the render archive (gitignored, ignored by `fetch-assets.sh`) |

*(my call: editor-owned files sit outside the skill folder so that editors' design changes don't look like framework changes in git, and the framework can be updated without touching them.)*

## Template contract

`template.json` declares:
- `name`, `description` (one line, used by the B-roll skill to pick it), `version`, `status` (`draft` | `final`);
- `output`: `overlay` (alpha `.mov`), `fullscreen` (`.mp4`) or `still` (transparent PNG); a template may list several, for example a watermark that has both a still and animated states;
- `canvas`: `frame` (follows `--resolution` and `--vertical`) or a fixed pixel size (for example a tight logo canvas the editor scales in Resolve);
- `vertical`: supported or not;
- `frames`: default, min and max length, in integer frames at the given fps;
- `fields`: name, type, required, max length, help text. Field types:

  | Type | Example use | Validation |
  |---|---|---|
  | `text` | headline, name | length limit |
  | `highlight` | a phrase to mark | must be a substring of the named field |
  | `number` | `10^67` | parsed into value and exponent |
  | `enum` | watermark state | one of the listed values |
  | `list` | bars `label=value`, steps | item count range, per-item limits |
  | `source` | credit line | collected into `kaynaklar.txt` |

New field types are added in the framework when a template needs one, with tests.

Validation is generic, driven by the manifest. The CLI rejects input it can't lay out instead of rendering something broken, with errors in Turkish like the finder's.

## Design workflow (documented in the skill, run with Claude Code)

This is where design decisions get made. The skill's reference doc tells Claude how to run it, and every decision belongs to the editor.

1. **Explore.**
   - Claude makes throwaway mockups with the editor in the brainstorm visual companion (the way this project's own design was explored): references, side-by-side options, variations on request.
   - Mockups stay in `.superpowers/` (gitignored).
2. **Record.** The editor's rulings go into the design's `tokens.css`, `variants/` and `design.md`.
   - `make_graphic.py --new-design <name> [--from <design>]` scaffolds a design folder.
   - A new design starts from a blank skeleton with every token listed and empty, or as a copy of another design.
3. **Template.**
   - `make_graphic.py --new-template <name> [--from <template>]` scaffolds a composition plus a manifest wired to the active design.
   - Claude fills it from the approved mockup, using only tokens for visual values.
4. **Preview.**
   - `make_graphic.py --preview <template> [--variant V] [--vertical]` opens the template in the browser with its sample data. The editor watches it play and scrubs it before rendering.
   - *Left to the builder:* use HyperFrames' own preview if it fits, otherwise a local page.
5. **Review.**
   - `--samples <template>` renders every sample and a contact sheet.
   - `--showcase [design]` builds one page of all templates (the recording page from this brainstorm, made generic).
   - The editor marks a template `final` in its manifest. After that, every change bumps its `version`.

## Rendering

**CLI.**
- `scripts/make_graphic.py <template> --field value … [--variant V] [--vertical] [--frames N] [--fps 25] [--resolution 4k|1080p] [--out DIR] [--design D] [--still|--format …]`.
- `--batch FILE` takes JSON rows, for the B-roll skill.
- `--list [--json]` prints the templates of the active design with their descriptions and fields, so Claude and the B-roll skill can choose one and fill it.
- Python, standard library only, `unittest`, the same structure as the finder.

**Engine (HyperFrames, Apache-2.0).**
- Compositions are HTML. Variables are declared with `data-composition-variables`, and rendering seeks deterministically frame by frame.
- Output formats: `--format mov` gives ProRes 4444 with alpha; `--format mp4` gives H.264; `--resolution 4k` renders at 3840×2160.
- **Shipped in this repo** (user decision): `package.json` and `package-lock.json` in the skill folder pin an exact HyperFrames version (0.9.41 or later at build time). Setup runs `npm ci`, and `node_modules` stays gitignored.
- Chrome comes from `npx hyperframes browser ensure`.
- **Telemetry off:** every call runs with `HYPERFRAMES_NO_TELEMETRY=1` and `DO_NOT_TRACK=1`. The skill never signs in to HeyGen and never uses a cloud connector.
- **Host requirements:** Node 22 (present), plus FFmpeg and FFprobe on PATH. The setup script runs `hyperframes doctor` and reports in Turkish what is missing.
- **Engine helpers:** small JS helpers that templates may import. They are mechanics, not looks:
  - reading the variables;
  - a frame-based timeline;
  - text measuring and fitting;
  - a reveal that doesn't clip overhanging glyphs (learned in the brainstorm);
  - SVG stroke draw-on.
  - Durations and easings come from tokens.

**Output contract.**

| Setting | Value |
|---|---|
| Frame rate | 25 by default (the camera rate); `--fps` overrides |
| Resolution | 3840×2160 by default; `--resolution 1080p` for speed; vertical is 2160×3840; fixed-canvas templates ignore both |
| Format | per the manifest's `output` |
| Length | integer frames, the template's default unless `--frames` is given, checked against its min/max |

- `--out` defaults to `~/Downloads/grafik/<template>-<slug>/` when called on its own. The B-roll skill passes episode paths.
- A re-run never overwrites; numbering continues, as in the finder. *(my call)*
- Each output folder gets a `results.json` with, for every render:
  - template, version, design, variant, fields, file, frames, fps, resolution;
  - sources.
- Sources are appended to a `kaynaklar.txt` in the finder's format: raw text, deduplicated. *(my call)*

**Archive** (indexable, like the stock cache).
- `assets/graphics/<template>/<id>/` holds:
  - `vars.json`, the source of truth: template, version, design, variant, fields, engine version, created;
  - the render;
  - a poster PNG.
- `assets/graphics/index.json` is derived from them, and `--reindex` rebuilds it.
- `id` is a content hash of the template id + template version + a hash of the design's files + fields + variant + orientation + frames + fps + resolution. A repeated request reuses the archived render. Any change to the design invalidates the match. *(my call)*
- `--fresh` forces a new render even when an archived one matches.
- `scripts/fetch-assets.sh` ignores `assets/graphics/`.

## The starter example

- **Location:**
  - Design: `graphics/designs/starter/`.
  - Templates: `graphics/templates/starter/`.
  - The starter is the active design in `graphics/config.json` until the editors make their own.
- **Labelling:**
  - `design.md` opens by saying this is the brainstorm's example, not a channel decision.
  - It records what was explored, so editors can keep, change or drop any of it.
- **Content:** the values from the 2026-11-13 brainstorm, as tokens and variants:
  - pure black page with a fading dot grid (graph paper for one variant);
  - Fraunces headline, upright then italic second line;
  - JetBrains Mono labels with a tick;
  - Caveat handwriting;
  - ink `#ECE6DA`, star-orange `#FFB46A` highlights and handwriting;
  - the six series variants (`uzay` `#7FA8FF`, `diyalog` `#E6CFA0`, `kurgu` `#B9A8F2`, `muhendislik` `#9FE6F2`, `notlar` `#8FE0B0`, `ev` `#C7CBD3` as default) with their motifs;
  - calm motion timings;
  - the R3 globe logo as an SVG asset.
- **Starter templates:** one per framework capability, so each feature is proven by a real render. *(my call: the rest of the brainstorm catalogue is for editors to build)*

  | Template | Proves |
  |---|---|
  | `chapter-title` | full-screen `.mp4`, text fields, variants, vertical |
  | `number` | `number` and `highlight` field types, a hand note, `source` → `kaynaklar.txt` |
  | `bar-chart` | `list` fields with count limits |
  | `name-line` | alpha overlay `.mov` |
  | `watermark` | fixed canvas, `enum` state, still PNG + animated `.mov` from one template, 3D (the revolve passes behind the globe), seamless state chaining |

  The watermark keeps the delivery the user chose:
  - a tight high-resolution transparent canvas the editor scales and positions;
  - every state on the same canvas, with the globe in the same place;
  - static as PNG, the other states as ProRes 4444.

- **Animated logos are kept** (user, 2026-11-18).
  - The `watermark` template rebuilds all six living-logo states from the final prototype (`watermark-v9`), faithfully:
    - static;
    - wireframe;
    - revolve and revolve wireframe: the name grows, bends onto the sphere, revolves in 3D passing behind the globe, and returns to static;
    - star and star without name: it fades in far outside the logo, crosses on a long straight path, and fades out far outside.
  - Its `design.md` records the behaviour of each state and what was rejected along the way (extruded letters, the elliptical star path), so editors know the history before changing it.
- **The brainstorm prototypes ship as reference** in `graphics/designs/starter/reference/`, because `.superpowers/` is gitignored and they would otherwise be lost:
  - `watermark-v9.html` (the final living-logo prototype);
  - `logo-options.html` (the logo directions, R3 among them);
  - `showcase.html` (every graphic mocked up in the starter look).

  Each one is made standalone so it opens directly in a browser, without the brainstorm server. They are mockups, not templates, and the CLI never reads them.

## Order of work

*(my call)*
1. Setup and engine: pinned HyperFrames, setup/doctor check, telemetry env, engine helpers.
2. Template contract and the generic CLI: manifest parsing, validation, render, output contract, archive, `--list`, `--batch`.
3. Starter design plus `chapter-title`, the first real template, to prove steps 1 and 2 end to end. User review.
4. The remaining starter templates: `number`, `bar-chart`, `name-line`, `watermark`. A user review after each.
5. Design-workflow tooling: `--new-design`, `--new-template`, `--preview`, `--samples`, contact sheet, `--showcase`.
6. SKILL.md and the reference docs (design workflow, template contract). Then a live test: an editor-style session that makes a new template with Claude Code from scratch.

## Constraints

- Lengths and times are integer frames everywhere (project rule).
- No double em dashes in any text the skill writes.
- Never send the user's identity, project or email to an outside service. HyperFrames telemetry is off.
- Don't stage `*.rpm` files or `wiki/.obsidian/workspace.json`. `/demo/` and `/episodes/` stay gitignored.
- Fonts are OFL: keep their licence files next to them, and they must cover Turkish (ğ ş ı İ ç ö ü).

## Left to the builder

- **Template internals:** GSAP versus CSS timelines, and how the starter's 3D revolve is built. The brainstorm prototype used CSS 3D transforms with per-letter positions driven per frame.
- **Starter details:** default lengths and text limits for the starter templates. Propose them, then confirm in review.
- **Testing renders:** ffprobe checks on duration, size, codec and alpha, plus poster-frame checks.
- **Preview:** whether `--preview` uses HyperFrames' own preview.
- **SKILL.md wording:** follow the finder's style, with triggers in the description, steps, batch usage and Turkish messages.

## Decided after review

- **Framework only** (user, 2026-11-18). The repo ships the framework, and editors own the design. The brainstorm design ships as an editable, clearly labelled starter example.
- **FFmpeg on the machine** (user, 2026-11-13). The user installs FFmpeg and FFprobe on the host with RPM Fusion, then `dnf install ffmpeg`. Renders run locally, not in Docker. Setup checks for them and prints the install hint in Turkish; it never runs sudo.
- **Fixed-canvas delivery** (user, 2026-11-13, for the watermark). A logo-type graphic renders at high resolution on its own tight transparent canvas, and the editor scales and positions it in Resolve. The framework supports this through `canvas` in the manifest.
