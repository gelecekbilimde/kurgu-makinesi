# Stock footage finder: design

**Date:** 2026-11-13
**Status:** approved 2026-11-13
**Platform:** Linux only for now (decided); Windows and macOS later.
**Scope:** the first of three B-roll projects. The B-roll skill is built from small skills an editor can also call on their own:
1. **Stock finder** (this document): a plain description in, downloaded candidates and credits out.
2. **Graphics builder** (HyperFrames): one graphic per request, then iterate. Separate design.
3. **B-roll skill**: reads the script and the A-roll timeline, calls 1 and 2 per row, and places the results in Resolve as takes. Separate design.

## Why
Editors need stock footage for episodes and for shorts. Today they search the sites by hand, download, rename and collect credits for the description. The finder does that from one sentence, the same way every time, and the B-roll skill reuses it instead of searching on its own.

## Goals
- An editor types "rocket launch footage" (in Claude Code, through the skill) and gets a few candidate clips in a folder, each with its source and credit, plus a credits text ready to paste into the video description.
- The B-roll skill calls the **same script** with episode-specific parameters (output folder, row code) and gets the same result format back.
- Sources are easy to add and remove: one adapter file per source plus one entry in a single JSON config. Turning on Pexels later is "set the key, set `isEnabled: true`".
- A local cache under `assets/stock/` is checked before any API call, and no clip is ever downloaded twice.
- Search, ranking, download and credits are deterministic scripts. The LLM only turns the request into English keywords and calls the script.

## Non-goals
- Placing clips in Resolve, matching them to script rows, or building the final credits list of an episode. That is the B-roll skill.
- Graphics, AI generation (Firefly), article screenshots (KAYNAK) and the Dropbox archive (ARŞİV).
- Still images. Video only in this version (my call: NASA's photo library is valuable, so a photo mode is a likely follow-up).
- Judging whether a clip actually shows what was asked. The editor (or later the B-roll skill) picks among the candidates.
- Cache eviction or size limits.

## Anti-goals (a failure even if it works)
- **Credits get lost.** Every file the finder delivers must carry its source, creator and page link, also when it comes from the cache months later.
- **It hammers the APIs.** Pixabay forbids mass downloads and requires 24-hour caching of searches; Pexels allows 200 requests an hour. The finder downloads only what it was asked for.
- **It silently delivers footage we may not use.** NASA's library contains third-party material (a test search for "rocket launch" returned clips credited to Rocket Lab). Those compete for slots like any other clip (decided) but always carry a visible `third_party` warning and are credited to the third party, never as plain "NASA".
- **A missing key or a dead source stops the run.** It is skipped with a note; the other sources still deliver.

## How it is used
**On its own.** The editor asks in Claude Code; the skill translates the description into English keywords and runs:

```
python3 .claude/skills/finding-stock-footage/scripts/find_stock.py "rocket launch" \
    [--count 3] [--orientation horizontal|vertical] [--out DIR] [--code CODE] \
    [--sources pixabay,nasa] [--min-duration 4] [--max-duration 120] [--fresh]
```

- `--out` defaults to `~/Downloads/stok/<query-slug>/` (for example `~/Downloads/stok/rocket-launch/`).
- `--orientation` defaults to `horizontal`. `vertical` (for shorts) ranks vertical clips first and fills the remaining slots with horizontal ones, which the editor crops.
- `--count` defaults to 3.
- `--fresh` skips the local cache match (step 1 below) but still never re-downloads a cached clip.

**From the B-roll skill.** Same script, with `--out episodes/<ep>/broll/stok/` and `--code` set to the script row's code, or with `--batch requests.json` (a list of `{code, query, orientation, count}`) to run every STOK row in one call and write one combined `results.json`. Batch mode is my call: it keeps the per-row loop in a script instead of in the LLM.

## What it does, in order
1. **Local match.** Look in the cache index for clips whose stored keywords (the queries that found them, plus the source's tags and title) contain every query word. If that gives `--count` clips in the wanted orientation, use them and make no API call. Otherwise keep them and continue. (My call; the exact matching rule is the builder's, as long as it is deterministic.)
2. **Search.** Ask every enabled source, highest priority first. A search response is stored in the cache and reused for 24 hours (Pixabay requires this; it is applied to every source).
3. **Filter.** Drop clips shorter than `--min-duration` (default 4 s) or longer than `--max-duration` (default 120 s; NASA has 30-minute press conferences), and clips whose largest version is under 1280 px on the long side.
4. **Rank.** Orientation match first; then sources take turns in priority order (round-robin: first pixabay hit, first nasa hit, second pixabay hit, ...), each source in its own relevance order. Round-robin is my call, so one source cannot crowd out the others; with one result short, the next source fills in.
5. **Download.** The largest version up to 3840 px on the long side, into the cache, with a sidecar of metadata. Already cached clips are not downloaded again.
6. **Deliver.** Hard-link (copy if linking fails) each chosen clip into `--out`, then write `results.json` and `kaynaklar.txt` there, and print a short Turkish summary: one line per candidate with code, source, resolution, duration, orientation and any warning.

## Sources
### Config: `.claude/skills/finding-stock-footage/sources.json` (decided)
One file holds every source. Each entry has the slug, the base URL (anything the API needs except credentials), the priority (1 fills first) and `isEnabled`:

```json
{
  "sources": [
    {"slug": "pixabay", "url": "https://pixabay.com/api/videos/",    "priority": 1, "isEnabled": true},
    {"slug": "nasa",    "url": "https://images-api.nasa.gov",        "priority": 2, "isEnabled": true},
    {"slug": "pexels",  "url": "https://api.pexels.com/v1/videos/",  "priority": 3, "isEnabled": false}
  ]
}
```

### Keys (decided)
Read from the environment only, named `<SLUG>_API_KEY` (`PIXABAY_API_KEY`, `PEXELS_API_KEY`). Never written to the repo, a log or `results.json`. A source that needs a key and has none is skipped with the note `pexels: PEXELS_API_KEY yok, atlandı`. NASA needs no key.

### Adapters
One file per source in `scripts/sources/<slug>.py`, all with the same small interface (builder's choice of exact shape): **search** (keywords, orientation, how many) returning candidates with id, page URL, creator, title/tags, width, height, fps if known, duration, and the download URL of the chosen version; and the **credit and licence** text for a candidate. Adding a source means one adapter file and one config entry. All three adapters ship in this version; Pexels ships disabled and is tested against the sample responses in its documentation.

| Source | What the API gives (checked 2026-11-13) | Adapter notes |
|---|---|---|
| **Pixabay** | `GET /api/videos/?key&q`; per hit `videos.{large,medium,small,tiny}` with url/width/height/size, `duration`, `user`, `pageURL`, `tags`. No orientation filter for video. 100 requests / 60 s. | Orientation from width/height. `large` (usually 3840×2160) may be empty; fall back to `medium`. No fps in the API: `fps` is null. |
| **NASA** | `GET /search?q&media_type=video` gives `nasa_id`, title, description, keywords, center. File list from `GET /asset/{nasa_id}` (`~orig.mp4`, `~large.mp4`, `~medium.mp4`, ...). `metadata.json` in that list has `QuickTime:ImageWidth/ImageHeight`, `QuickTime:VideoFrameRate`, `QuickTime:Duration`, `XMP:Credit`, `XMP:Creator`. No key. | Two extra requests per candidate (asset list, metadata): fetch them only for as many hits as needed, and cache both. Use `~orig.mp4` when it is at most 3840 px wide, else `~large.mp4`. Plain NASA means `XMP:Credit` (else `XMP:Creator`) is empty or names NASA, a NASA center or JPL ("NASA", "NASA/JPL-Caltech", "NASA/Bill Ingalls", "KSC"); anything else (Rocket Lab, SpaceX, ESA, ...) marks the candidate `third_party` (a boolean in the sidecar and `results.json`) with a warning; a center code alone counts as NASA only when the credit is nothing but center codes ("KSC"), so "SpaceX HQ" stays third party, and the credit line reads `NASA / <credit>`. Flagged clips rank like any other (decided). Page link: `https://images.nasa.gov/details/<nasa_id>`. |
| **Pexels** | `GET /v1/videos/search?query&orientation&size&per_page`, header `Authorization: <key>`; per video `video_files` with quality/width/height/fps/link, `duration`, `user.name/url`, `url`. 200 requests / hour. | Pass `orientation=portrait` for vertical. Pexels asks for a visible link to Pexels and credit to the creator. |

## The cache: `assets/stock/`
- `assets/stock/clips/<slug>/<id>.mp4` and a sidecar `<id>.json` holding everything `results.json` needs for that clip (source, id, page URL, creator, licence, credit line, width, height, fps, duration, orientation, the queries that found it, download date, warnings).
- `assets/stock/searches/<slug>/<hash>.json`: raw search (and NASA asset/metadata) responses with their fetch time.
- **Designed to be indexed like the archive (decided).** The Dropbox archive (ARŞİV) will later get an index that the B-roll skill searches; the stock cache must fit into that same index without migration. So (details are my calls):
  - The **sidecar is the source of truth**, one per clip, in a schema that is not stock-specific: `kind` (`stock` now, `archive` later), `source`, `id`, `file` (path relative to its root), `title`, `description`, `keywords` (source tags plus the queries that found it), `width`, `height`, `fps`, `duration_s`, `orientation`, `creator`, `credit`, `licence`, `page_url`, `warnings`, `added`, and a `schema` version number. Later passes may add fields (for example a shot description or a content hash); readers ignore fields they do not know.
  - The **index is derived**: a single `assets/stock/index.json` built from the sidecars, used for the local match, and rebuildable at any time with `find_stock.py --reindex`. Nothing is stored only in the index.
  - Search over the index lives in its own small module with no knowledge of APIs, so the archive indexer can reuse it.
- `assets/` is gitignored already. `scripts/fetch-assets.sh` must ignore `assets/stock/` in both `verify` (today it reports every cached clip as "unexpected file") and `manifest` (which would otherwise add the clips to the brand pack's checksum list).

## Output contract (shared with the B-roll skill and every later finder-type skill)
In `--out`:
- The clips, named `<code>-<n>_<slug>-<id>.mp4` (for example `R12-1_pixabay-1234567.mp4`). Without `--code`, the code is the query slug (`rocket-launch-1_nasa-...`).
- `results.json`, always one shape, whether one query or a batch (planning amendment: one shape means one reader and an easy merge on re-runs):

```json
{
  "created": "2026-11-13T10:00:00+03:00",
  "notes": ["pexels: PEXELS_API_KEY yok, atlandı"],
  "requests": [
    {"query": "rocket launch", "code": "R12", "orientation": "horizontal", "notes": [],
     "candidates": [
       {"code": "R12-1", "file": "R12-1_pixabay-1234567.mp4", "source": "pixabay", "id": "1234567",
        "page_url": "https://pixabay.com/videos/id-1234567/", "creator": "kullanici",
        "licence": "Pixabay Content License", "credit": "Pixabay / kullanici",
        "width": 3840, "height": 2160, "fps": null, "duration_s": 14.0, "orientation": "horizontal",
        "from_cache": false, "warnings": [], "third_party": false}
     ]}
  ]
}
```

  Durations here are metadata in seconds; anything that cuts converts to frames from the media itself.
- **Batch mode** (my call): all clips go flat into the one `--out` (the code prefix keeps rows apart), one entry in `requests` per row. A row with no candidates gets a note; the exit code is 2 only if every row is empty. The same clip may be a candidate for two rows; it is then linked twice under each row's name.
- **Running again into the same `--out`** (my call): a delivered file is never replaced or renamed, because the B-roll skill may already have placed it in Resolve, so a name always means the same clip. New candidates for a code continue the numbering (`R12-4`, ...), clips already delivered for that code are not delivered again, and `results.json` and `kaynaklar.txt` are merged, not overwritten. `--fresh` therefore yields clips that are new for that code.
- `kaynaklar.txt`: one line per candidate, ready to paste under the sources list in the description, for example `Pixabay / kullanici: https://pixabay.com/videos/id-1234567/` and `NASA / Rocket Lab: https://images.nasa.gov/details/...`. It lists every delivered candidate; the editor deletes the lines of clips not used (the B-roll skill will build an episode's list from what is on the timeline).

## Errors
- Missing key, HTTP 429 or a network failure on one source: note it, carry on with the others.
- Fewer candidates than asked: deliver what there is, say so in the summary and in `notes`.
- Nothing found at all: exit code 2 with a Turkish message suggesting other keywords. Other failures exit 1.

## Skill
`.claude/skills/finding-stock-footage/SKILL.md`: when to use it (an editor wants stock video for a description; the B-roll skill's STOK rows), how to turn a Turkish description into 2-4 English keywords, the command, and how to report the result (folder path, the summary, any warnings, especially `third_party`). Python 3.12, standard library only, like `templates/script/`.

## Testing
- Adapters are tested offline against saved responses: real Pixabay and NASA responses recorded once during development (with the key stripped), and the Pexels documentation samples.
- Ranking, filtering, round-robin, local match, 24-hour reuse, naming, `results.json` and `kaynaklar.txt` are tested with fake sources, no network.
- One opt-in live test (`STOCK_LIVE=1`) runs a real NASA and Pixabay search and a single small download.
- Acceptance: on this machine, `find_stock.py "rocket launch"` delivers 3 horizontal candidates with correct credits; repeating it makes no API call; `--orientation vertical` puts vertical clips first; with `PIXABAY_API_KEY` unset it still delivers NASA clips with a note.

## Left to the builder
Module layout inside `scripts/`, the adapter interface's exact shape, the cache index format, the local-match details, HTTP retry policy, and the wording of Turkish messages.
