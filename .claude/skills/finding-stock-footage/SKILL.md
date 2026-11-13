---
name: finding-stock-footage
description: Use when an editor wants stock video footage for a description ("roket fırlatma görüntüsü", "rocket launch footage"), for a short or an episode, or when the B-roll skill needs candidates for STOK script rows - searching Pixabay, NASA and other configured stock sources, downloading candidates and collecting credits for the video description.
---

# Finding stock footage

## Overview
A deterministic script searches the enabled stock sources, ranks and downloads a few candidates and writes their credits. Your job is only to turn the request into English keywords, run the script, and report what it printed. Do not search the sites yourself or pick clips by judgement; the editor picks among the candidates.

## Steps
1. **Keywords.** Turn the description into 2-4 English keywords that a stock site would match: "uzakta kalkan roket" → `rocket launch`. Drop style words ("güzel", "etkileyici"). NASA only understands English.
2. **Run** from the repo root:
   ```
   python3 .claude/skills/finding-stock-footage/scripts/find_stock.py "rocket launch"
   ```
   - For a short (vertical video): add `--orientation vertical`. Vertical clips come first, horizontal ones fill the rest and get cropped.
   - Other flags: `--count N` (default 3), `--out DIR` (default `~/Downloads/stok/<keywords>/`), `--code R12`, `--sources nasa`, `--min-duration`/`--max-duration` (default 4-120 s), `--fresh` (skip clips already in the cache that match). See `--help`.
   - If it notes `PIXABAY_API_KEY yok`, the key is in `~/.bashrc` but this shell started before it was added: run it as `source ~/.bashrc && python3 ...`.
3. **Report** to the editor: the folder, each candidate line (code, source, size, duration, orientation, `önbellekten` if it came from the cache) and **every `!` warning**. `NASA dışı içerik (...)` means the clip is in NASA's library but credited to someone else (Rocket Lab, SpaceX, ESA, ...): tell the editor to check the rights before using it. Mention `kaynaklar.txt`: it is ready to paste under the sources list of the video description; lines of unused clips should be deleted.
4. **Exit code 2** ("Hiç aday bulunamadı") means nothing matched: try broader or different keywords once, then ask the editor.

## For the B-roll skill
Run all STOK rows in one call:
```
python3 .claude/skills/finding-stock-footage/scripts/find_stock.py --batch requests.json --out episodes/<ep>/broll/stok/
```
`requests.json` is `[{"code": "R12", "query": "rocket launch", "orientation": "horizontal", "count": 3}, ...]`. The result is `results.json` in `--out`, always `{"created", "notes", "requests": [{"query", "code", "orientation", "notes", "candidates": [...]}]}`. A re-run never replaces delivered files; new candidates continue the numbering (`R12-4`, ...).

## Sources and cache
- `sources.json` lists every source (`slug`, `url`, `priority`, `isEnabled`). Keys come only from the environment as `<SLUG>_API_KEY`. Pexels is shipped disabled: to turn it on, set `PEXELS_API_KEY` and `"isEnabled": true`.
- Adding a source: `scripts/sources/<slug>.py` with `SLUG`, `NEEDS_KEY` and a `Source(cfg, key, http)` class whose `search(query, orientation)` yields `model.Candidate`, plus an entry in `sources.json`.
- The cache is `assets/stock/` (clips plus one JSON sidecar each; `index.json` is derived). `find_stock.py --reindex` rebuilds the index. API responses are reused for 24 hours (Pixabay requires it).
