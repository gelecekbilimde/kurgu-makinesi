---
name: placing-b-roll
description: Use when an editor wants B-roll placed over frozen A-roll chapters in DaVinci Resolve from the script's STOK/GRAFİK/YAZI/KAYNAK/ARŞİV rows - fetching stock, rendering graphics from templates, screenshotting sources, putting placeholders where nothing fits, and rebuilding the chapter B-roll timelines without losing the editor's changes. Also for freezing a chapter's B-roll and building the "<prefix> B-roll" master. Built for Gelecek Bilimde episodes.
---

# Placing B-roll

## Overview
For every non-KAMERA row of a **frozen** A-roll chapter, deterministic scripts find or make the visual and place it over the frames where the row's words are spoken, on a new timeline `<chapter timeline> B-roll`: V1 = the frozen chapter nested, V2 = full-screen B-roll (stock, screenshots, full-screen graphics with background), V3 = overlays (YAZI, transparent graphics). Rows that can't be filled get a placeholder. A mixed `[KAMERA, X]` row keeps the presenter on screen: its B-roll goes on V3 only (overlays; a full-screen template is rendered without background) and covers only the row's own words. **Your only judgment step is filling `broll/requests.json`**; everything else is running scripts and relaying what they print. Never place clips through the Resolve MCP, pick clips yourself or invent graphics.

`broll/plan.json` is the truth about what is on the B-roll timelines. Each `build` reads the timeline back first: anything the editor changed is kept and never touched again.

## Requirements
- An episode folder `episodes/<ep>/` from the rough cutter with `script.json` (`templates/script/script_doc.py`), transcripts, `sections.json`, and chapters frozen by `chapters.py freeze` (`"frozen"` in `episode.json`).
- Resolve Studio running with the episode's project open. Resolve steps go through the rough cutter's `rv.sh`.
- The stock finder (`PIXABAY_API_KEY`) and making-graphics (`setup.py` done) work on their own.

Shorthands below: `B=.claude/skills/placing-b-roll/scripts`, `RV="bash .claude/skills/rough-cutting-a-roll/scripts/rv.sh"`, `EP=episodes/<ep>`.

## Steps
1. **Requests:** `python3 $B/broll.py requests $EP`. It prints the rows that still need a request as JSON on stdout (id, key, tags without KAMERA, visual, links) and fills ARŞİV (placeholder), KAYNAK (the row's link) and untagged rows ("tür yok" placeholder) itself.
2. **Fill `$EP/broll/requests.json`** (you). `rows` maps the row `key` to a list with one request per tag:
   - **STOK:** `{"tag": "STOK", "kind": "stock", "query": "truck border crossing"}` with 2-4 English keywords, as in finding-stock-footage.
   - **GRAFİK / YAZI:** run `python3 .claude/skills/making-graphics/scripts/make_graphic.py --list --json`. Use `{"tag": "GRAFİK", "kind": "graphic", "template": "bar-chart", "fields": {...}}` **only** when a template fits and the row's cell carries every required value (list fields as JSON lists, numbers as the writer wrote them). Otherwise use `{"tag": "YAZI", "kind": "placeholder", "reason": "şablon yok", "need": "<one line: what template would fit>"}`. Never invent data or a template. Optional: `"variant"`, `"background": false` (puts a full-screen template on V3 as an overlay).
   - Never overwrite an existing entry. Deleting an entry makes its row pending again. A found row with a tag that has no request gets an `istek yok` placeholder at `fetch` until the request is written.
3. **Layout:** `$RV $B/broll_resolve.py layout $EP` reads each frozen chapter's V1 (read-only).
4. **Align:** `python3 $B/broll.py align $EP` maps rows to frames (`ch3: 2/2 B-roll satırı bulundu`). A row not found was cut or not spoken; it is listed, not placed.
5. **Fetch:** `python3 $B/broll.py fetch $EP` runs the stock finder, making-graphics and the screenshots, and makes the placeholder stills. Only changed or new requests are fetched again. A graphic longer than its template maximum plays to 70 % and holds that frame to the row's end.
6. **Build:** `$RV $B/broll_resolve.py build $EP [N ...]` creates or updates the chapter B-roll timelines and writes `broll/plan.json` and `broll/kaynaklar.txt`. Unused candidates go to the bin `<prefix> B-roll/ch<N>/<row id>`.
7. **Report** the summary as printed. It covers only the chapters built in that run. Per chapter `eklendi / kaldırıldı / korundu (düzenleyici öğesi)`, `Yerleştirilen satırlar`, `Düzenleyicide (güncellenmiyor)` (rows the editor touched), `Yer tutucular` by reason, `Bölümde bulunamadı`, `stok yetmedi`, `satırı kayboldu` (editor entries whose row left the script), every `Uyarı`, and the **`Gereken şablonlar`** list (offer the making-graphics design path for them). Mention `kaynaklar.txt` for the video description.
8. **Review loop:** the editor works in Resolve; after a request change, run `fetch` then `build` again. Rebuilding is always safe.
9. **Sign off:** `python3 $B/broll.py freeze $EP N` (build then skips that chapter; `unfreeze` undoes it). `$RV $B/broll_resolve.py master $EP` rebuilds `<prefix> B-roll`: each chapter's B-roll timeline in order, the frozen A-roll chapter where there is none yet. The master is deleted and regenerated on every run, so don't edit it; edit the chapter B-roll timelines.

## What the editor may do in Resolve
Everything on V2/V3 and beyond: move, trim, zoom/transform, crop, opacity, speed, colour, swap in a candidate from the row's bin, delete, add their own clips, markers and tracks. Read-back keeps all of it: a changed item becomes an editor item that build never touches, a deleted item stays empty ("nothing here", never refilled), an added item is kept. Touching one item of a row freezes the whole row against rebuilds (it is listed under `Düzenleyicide (güncellenmiyor)`); rows the editor didn't touch are still updated by later builds. A moved item reads either as a changed item (if Resolve keeps its uid) or as "ours deleted + the editor's own added"; either way, the editor's version is kept.

**Markers:** Lavender ranged marker = placeholder (`<row id> <tag>: <description> (<reason/need>)`, customData `broll:<item id>`). Green markers on the master = chapter starts. The editor's own markers are never touched.

## Common mistakes
- **Running on an unfrozen chapter.** Only `"frozen"` chapters get B-roll; freeze the A-roll first (`chapters.py freeze`). Layout and align read the frozen timeline as it is.
- **Editing the frozen A-roll chapter timeline.** It is nested on V1; the skill never changes it, and neither should anyone else. To change the A-roll, unfreeze it in the rough cutter and rebuild from `layout`.
- **Deleting or hand-editing `broll/plan.json`.** It is what tells our items from the editor's. Without it, build takes everything on the existing timeline for the editor's own items and places every row again on top. Edit `requests.json` instead.
- **Filling a GRAFİK row with guessed numbers or a near-fit template.** Use a placeholder with a `need` line; the gap must stay visible.
- **Skipping `fetch` after a request change.** Build places what `fetched.json` holds.
- **Running Resolve steps with plain `python3`.** They need `rv.sh`.

See `reference.md` for file formats, Resolve API facts and the acceptance run.
