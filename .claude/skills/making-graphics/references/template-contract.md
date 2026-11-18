# Template contract

A template is a folder `graphics/templates/<design>/<name>/` with:
- `template.json`: the manifest (below);
- `index.html`: a HyperFrames composition;
- `samples.json`: sample requests for review (`[{"label", "fields", "variant"?, "vertical"?, "frames"?}]`).

## template.json

```json
{"name": "number", "description": "Tek sayı vurgusu: büyük değer, birim, açıklama, kaynak",
 "version": 1, "status": "draft",
 "output": "fullscreen", "output_by": {"field": "state", "map": {"static": "still"}},
 "canvas": "frame", "vertical": true,
 "frames": {"default": 150, "min": 75, "max": 375},
 "fields": [{"name": "value", "type": "number", "required": true, "help": "3,7 ya da 10^67"}]}
```

| Key | Meaning |
|---|---|
| `name` | folder name; also the composition id |
| `description` | one Turkish line; `--list` shows it and the B-roll skill chooses by it |
| `version`, `status` | `draft` until the editor approves; `final` after; bump `version` on every change after final |
| `output` | `fullscreen` (has a page; renders as a transparent overlay unless `--background`), `overlay` (no page), `still` (transparent PNG) |
| `output_by` | optional: an `enum` field whose values switch the output, e.g. watermark `state=static` → `still` |
| `canvas` | `"frame"` (1920×1080 composition rendered at 4K; 1080×1920 when vertical) or `{"width", "height"}` (fixed pixels, e.g. a logo the editor scales in Resolve; ignores `--vertical`/`--resolution`) |
| `vertical` | whether a 9:16 version exists |
| `frames` | default, min, max length in frames **at 25 fps**; scaled for other fps |

### Field types

| Type | Value given | Value the template gets | Checks |
|---|---|---|---|
| `text` | text | trimmed string | `max_len` |
| `highlight` | text | string | must occur in the field named by `of` |
| `number` | `3,7`, `1.234.567,89`, `10^67`, `-1.5^-3` | `{"base", "exp", "text"}` | number syntax |
| `enum` | one of `values` | string | membership |
| `list` | repeated `--set` / JSON list | list of strings (`item: "text"`) or `{"label", "value"}` (`item: "pair"`, `label=value`; `numeric: true` makes value a number) | `min_items`, `max_items`, `max_len` per label/item |
| `source` | text | string; collected into `kaynaklar.txt` | `max_len` |

Any field may set `required` and `help`. A text field may set `one_of_labels: "<list field>"` (its value must equal one of that list's labels). Unknown fields, missing required fields and every other problem are reported together, in Turkish, with exit code 2.

## What the CLI does per render (staging)

It builds a temporary HyperFrames project:
- the template folder (without `template.json` / `samples.json`);
- `design/`: the design without `design.md` and `reference/`, plus `design/variant.css` (the chosen variant, or empty);
- `kit/hf-kit.js`;
- `vars.json`: one string per field (lists and numbers JSON-encoded; the kit decodes them).

In `index.html` it rewrites the first element carrying `data-composition-id`: `data-duration` (frames/fps), `data-fps`, `data-width`, `data-height`. It also sets `<html data-composition-variables>` from the manifest, `<html data-background="none|page">` and a `<script id="kit-types">` with the field types. **So templates never hold a length or size of their own**, and link only `design/…` and `kit/hf-kit.js`.

## The kit (`window.kit`)

| Call | Does |
|---|---|
| `vars()` | field values, decoded (lists and numbers as objects) |
| `duration()`, `fps()`, `orientation()` | clip length in seconds, fps, `"horizontal"`/`"vertical"` (also set as `<html data-orientation>`) |
| `onFrame(fn)` | `fn(t)` on every HyperFrames seek (`hf-seek`) and once at t=0; **all motion goes here** |
| `progress(t, start, dur, ease)` | 0..1; easings `linear`, `out-cubic`, `out-quint`, `in-out-cubic`, `in-out-sine` |
| `token(name)`, `tokenNum(name)` | read a CSS custom property (string / number) |
| `reveal(el, p)` | left-to-right clip reveal that never clips an overhanging last glyph |
| `draw(svgShape, p)` | stroke draw-on |
| `fit(el, maxWidthPx)`, `textWidth(el)` | shrink text to a width (never grows); measure laid-out text |

Rules HyperFrames imposes: motion must be a function of `t` alone (frames render out of order); build after `document.fonts.ready`; measure layout once, not inside `onFrame`.
