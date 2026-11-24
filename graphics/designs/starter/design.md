# Starter design

Bu bir başlangıç örneğidir (starter example), kanalın onaylı tasarımı değildir.

It records what was explored in the 2026-11-13 design session, so editors can keep, change or throw away any of it. The real design decisions are the editors'. Record them here, with the reason, as you make them.

## Files

| File | What it holds |
|---|---|
| `tokens.css` | every visual value: fonts, colours, sizes, motion timings and easing names |
| `variants/*.css` | series overrides: colour, tick, motif, page pattern |
| `base.css` | shared building blocks (page, dot grid, label, heading, hand note, highlight), using tokens only |
| `motion.js` | the "calm" motion vocabulary (entry, highlight, draw, hand reveal, exit), timings from tokens |
| `assets/` | logo and series motifs |
| `fonts/` | Fraunces, JetBrains Mono, Caveat (SIL OFL, licences beside them) |
| `reference/` | the session's prototypes (open them directly in a browser); not used by renders |

## What the session explored

**References.** Editorial videos with an editorial serif, monospaced labels, marker highlights and handwritten notes.

**Page.**
- Pure black `#000`, true black on OLED screens.
- A dim dot grid sits on the page and fades to black towards the edges.
- Mühendislik Sohbetleri uses graph paper instead.
- No persistent header or corner bug. The watermark is the only exception.

**Type.**
- Headline in Fraunces: the first line upright, the second line italic and light, in the series colour.
- Labels in JetBrains Mono caps, with a short coloured tick before them.
- Body text in light Fraunces.
- Sources as mono caps, "KAYNAK · …".
- Handwritten notes in Caveat, tilted about -4°.

**Colour.**

| Role | Colour |
|---|---|
| Ink (headlines) | `#ECE6DA` |
| Body | `#B9B3A8` |
| Label | `#8F8A80` |
| Source | `#6E6A62` |
| Marker highlight and all handwriting ("look here") | star-orange `#FFB46A` |
| Highlight fill | `rgba(255,154,60,.45)` |
| Logo only | green `#19B34A`, petrol `#0B5F7A` |

**Series variants.** These set the second line, the tick and the motif.

| Variant | Series | Colour / tick | Motif |
|---|---|---|---|
| `uzay` | Uzay Gündemi | `#7FA8FF` / `#4F7DF0` | orbits |
| `diyalog` | Bilim Diyalog | `#E6CFA0` / `#C9A55E` | two overlapping circles |
| `kurgu` | Bilim mi Kurgu mu | `#B9A8F2` / `#8D75E6` | split film frame BİLİM / KURGU |
| `muhendislik` | Mühendislik Sohbetleri | `#9FE6F2` / `#4FC9DE` | graph paper, technical drawing with a dimension line |
| `notlar` | Teknoloji ve Bilim Notları | `#8FE0B0` / `#3FBF78` | ruled notebook |
| `ev` (default) | shorts, one-off videos | `#C7CBD3` / `#8E94A0` | none |

**Motion: "calm".**
- Elements fade in with a small rise, about 150 ms apart.
- Then the marker sweeps on, strokes draw themselves and the hand notes are revealed left to right.
- A quick fade at the end.

**Logo (R3).**
- A faithful refresh of the old globe: a petrol circle with green continents.
- The two-line wordmark "gelecek / *bilimde*" is set in Fraunces.
- It must read at 24 px.

## Watermark (living logo)

Prototype: `reference/watermark-v9.html`. The `watermark` template rebuilds it, with these states:

| State | Behaviour |
|---|---|
| static | Full-colour logo. |
| wireframe | Outlines only, with thick lines; the name is filled and see-through. |
| revolve | The name grows, bends onto the sphere and revolves in 3D. It passes behind the globe, then returns to static. |
| revolve-wireframe | The same, in wireframe. |
| star | A star fades in far outside the logo, crosses on a long straight path and fades out far outside. |
| star-noname | The same, globe only. |

- Every animated state starts and ends on the exact static logo, so the states chain seamlessly.
  - The wireframe states fade in from the colour logo and back out to it.
  - `star-noname` starts and ends on the globe without the name.
- All states share one canvas, with the globe at the same place. The editor scales and positions it in Resolve.
  - Canvas: 3800×2600 px, transparent; the globe is 1600 px across, at the centre.
  - `static` is a PNG; the other states are ProRes 4444 `.mov`.
- Suggested lengths: revolve 150 frames (6 s, the default), wireframe 100, star 75.
  - The star crosses in `--star-travel` seconds (2.4), starting `--star-start` (0.3) in, whatever the clip length.
- Change from the prototype: the wordmark is projected so that its flat state is exactly the static logo's size. In v9 it looked about 11% larger whenever it was flat.

**Rejected during the session:** extruded (thick 3D) letters, a curved or elliptical star path, a persistent header.

## Overlay and page

- Every render is a transparent overlay by default. `base.css` hides the page, the dot grid and the series motif when `<html data-background="none">`, and gives text a soft shadow.
- `--background` keeps the page, for a full-screen `.mp4`.
- The bars are partly transparent (`--bar-opacity-min`), so footage shows through them in overlays.

## Decisions by the editors

(record decisions here, with the date and why)

**2026-11-24, editors' demo video.** The user left the creative decisions to Claude; the points marked *user* are the user's own rulings.
- New draft templates: `points`, `date-range`, `teaser-caption`, `end-card`, `step-note`.
- **Teaser caption** *(user)*: the text stays mostly visible; only a small bit falls behind the head, for depth. A gentle curve over the head, not too strong. Built as pages of one or two large lines (`--caption-*` tokens, tuned on the COP31 framing).
- **Watermark** *(user)*: animated in shorts and long videos. At least a minute between animated states, so they seem almost random; wireframe while a graphic shows.
- **Short subtitles** *(user)*: green border (`#19B34A`). Resolve's API can't set it, so it is set by hand on the subtitle track.
- **Tutorial videos** *(user)*: in Turkish; a header with every stage and the current one highlighted; notes to the editor with arrows and other pointers; the parts where Claude thinks are sped up; the finished videos at the end. The screen recording must fit its section, and a zoom must not cut the chat window (`step-note`).
