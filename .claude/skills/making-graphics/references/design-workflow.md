# Design workflow

Use this when an editor wants a new look, a new series dialect, a change to the design, or a kind of graphic no template covers. **The editor makes every design decision.** Your job is to show options, build what they choose, and record it. Never decide colours, fonts, layout or motion on their behalf, and never present the starter as the channel's design.

## 1. Explore with the editor
- Ask what the graphic is for and where it will be seen (episode, short, which series), what they have liked elsewhere, and what would make them wince.
- Show, don't describe: make throwaway mockups in the brainstorm visual companion (superpowers:brainstorming's visual companion; mockups stay in `.superpowers/`, which is gitignored). Side-by-side options, variations on request, the editor's own words for what to change.
- Use real Turkish text in mockups, including the longest text they expect and ğ ş ı İ ç ö ü.

## 2. Record the decisions
- New design: `make_graphic.py --new-design <name>` (blank: every token listed, empty) or `--new-design <name> --from starter` (a copy to change). Activate it in `graphics/config.json` when the editor says so.
- Put every visual value the editor chose in the design's `tokens.css`; series overrides in `variants/<variant>.css` (`design.json` names the default variant); fonts under `fonts/` **with their licence files** (OFL or similar, Turkish coverage checked).
- Shared building blocks (CSS classes, a motion script) may live in the design folder next to the tokens; they are design decisions too.
- Write each decision in the design's `design.md` with the date and the editor's reason.

## 3. Build the template
- `make_graphic.py --new-template <name>` (blank skeleton) or `--new-template <name> --from <template>` (copy). Fill `template.json` (see `template-contract.md`): description in one Turkish line (the B-roll skill picks templates by it), fields with types and length limits, output, canvas, vertical, frame limits.
- Write `index.html` from the approved mockup. Every colour, font, size and timing comes from tokens (`var(--…)`, `kit.token()`); a grep for hex colours or `rgba(` in the template should print nothing.
- Motion is a pure function of time through `kit.onFrame(t => …)`. No clock, timers or `requestAnimationFrame`.
- Text that can be long: `kit.fit(el, maxWidthPx)` after `document.fonts.ready`. Hand-written reveals: `kit.reveal` (it leaves room for overhanging last glyphs).
- Overlays: the design hides its page when `<html data-background="none">` (the default render); make sure the graphic reads over bright and dark footage.
- `samples.json`: one row per variant, vertical if supported, and a row with **every field at its maximum length** in Turkish.

## 4. Look at it
- `make_graphic.py --preview <template>` opens HyperFrames Studio with the first sample (or `--set …`); scrub through it with the editor. Stop it with `--stop-preview <template>`.
- `make_graphic.py --samples <template>` renders every sample and `contact.png`. Look at the contact sheet and at late frames yourself before showing the editor: clipped glyphs, overlaps, text running off the frame.
- For overlays, check them composited over footage (`ffmpeg … overlay`), not only on black.
- `make_graphic.py --showcase` builds one page of all templates for the editor (and anyone they want to show).

## 5. Final
- Change `status` to `final` in `template.json` only when the editor says so. After that, every change to the template bumps `version`.
- Commit the design and template files when the editor asks.
