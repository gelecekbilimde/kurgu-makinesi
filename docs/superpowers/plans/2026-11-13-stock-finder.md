# Stock Footage Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude Code skill plus a stdlib Python CLI that turns a plain description into downloaded, credited stock video candidates from Pixabay and NASA (Pexels ready but disabled), with a cache under `assets/stock/` that the future archive index can absorb.

**Architecture:** One adapter module per source behind a common `Candidate` model; a cached HTTP layer (24-hour response reuse); a cache of clips with per-clip sidecars as the source of truth and a derived `index.json`; a finder that filters, ranks (orientation first, round-robin by priority) and downloads; a delivery step that links clips into `--out` and merges `results.json` / `kaynaklar.txt`; a thin CLI.

**Tech Stack:** Python 3.12 standard library only (`urllib`, `json`, `argparse`, `unittest`, `http.server` for tests), bash for `fetch-assets.sh`.

**Spec:** `docs/superpowers/specs/2026-11-13-stock-finder-design.md`

## Global Constraints

- Python 3.12, standard library only; Linux only.
- Skill lives in `.claude/skills/finding-stock-footage/`; scripts in `scripts/`, tests in `tests/`, config `sources.json` in the skill root.
- API keys only from the environment, named `<SLUG>_API_KEY`; never written to the cache, a log, `results.json`, a fixture or stdout. Cache keys and stored URLs exclude the key.
- HTTP `User-Agent: stock-finder/1.0`. No project, person or email in any request.
- Every API response (search, NASA asset list, NASA metadata) is cached and reused for 24 hours.
- Downloads: largest version with long side ≤ 3840 px. Filters: `--min-duration 4`, `--max-duration 120`, long side ≥ 1280.
- Defaults: `--count 3`, `--orientation horizontal`, `--out ~/Downloads/stok/<query-slug>/`, cache `<repo>/assets/stock/`.
- A delivered file in `--out` is never replaced or renamed.
- User-facing CLI messages and `kaynaklar.txt` are Turkish. No double em dashes anywhere.
- Exit codes: 0 delivered something, 2 nothing found in any request, 1 any other failure.
- Work on branch `stock-finder`; commit per task; never push or merge without asking. Never stage `*.rpm` or `wiki/.obsidian/workspace.json`.
- Test command (whole suite): `cd .claude/skills/finding-stock-footage && python3 -m unittest discover -s tests -v`. Tests put `scripts/` on `sys.path` like `templates/script/tests/` do. No test touches the network unless `STOCK_LIVE=1`.

## Review Focus

1. A NASA hit with no `~orig.mp4`, a missing `metadata.json`, or a duration in `"12.5 s"` form instead of `"0:00:30"` is skipped or parsed, never a crash (Task 4).
2. A Pixabay hit with an empty `large` rendition falls back to `medium` (Task 3).
3. A query with Turkish or punctuation characters ("Ay'a iniş!") gives a safe slug and code (Task 7).
4. An interrupted download never leaves a file in the cache that later counts as a complete clip (Task 2).
5. A re-run where the editor deleted a delivered file from `--out` still continues numbering from `results.json` and does not crash (Task 7).

---

### Task 1: Model, cache and index

**Files:**
- Create: `.claude/skills/finding-stock-footage/scripts/model.py`, `scripts/cache.py`, `scripts/index.py`
- Test: `.claude/skills/finding-stock-footage/tests/test_cache.py`, `tests/test_index.py`

**Interfaces:**
- Produces:
  - `model.Candidate` dataclass: `source: str, id: str, page_url: str, creator: str, title: str, description: str, keywords: list[str], width: int, height: int, fps: float | None, duration_s: float, download_url: str, licence: str, credit: str, warnings: list[str] = []`; properties `orientation -> "horizontal" | "vertical" | "square"` and `long_side -> int`.
  - `model.SourceError(Exception)` with `.slug`.
  - `cache.Cache(root: Path)`: `clip_path(slug, id) -> Path` (`clips/<slug>/<id>.mp4`), `sidecar_path(slug, id)`, `has_clip(slug, id) -> bool` (mp4 and sidecar both exist), `write_sidecar(c: Candidate, query: str, now: datetime) -> dict` (adds `query` to `keywords` if the sidecar exists, else creates it), `read_sidecars() -> list[dict]`, `get_response(slug, key, max_age_s, now: float) -> dict | None`, `put_response(slug, key, data, now: float)` (`searches/<slug>/<sha256(key)>.json` with `fetched` time), `write_index() -> list[dict]` (writes `index.json`).
  - Sidecar fields exactly: `schema: 1, kind: "stock", source, id, file` (relative to cache root), `title, description, keywords, width, height, fps, duration_s, orientation, creator, credit, licence, page_url, warnings, added` (ISO 8601).
  - `index.match(entries: list[dict], query: str, orientation: str | None = None) -> list[dict]`: lower-cased word tokens (`\w+`, Unicode); an entry matches when every query token is in the tokens of `title` + `keywords`; result sorted by (orientation ≠ wanted, `added` descending, `source`, `id`). No API knowledge in this module.

- [ ] **Step 1: Write the failing tests**
  - `test_orientation`: 1920×1080 → horizontal, 1080×1920 → vertical, 1080×1080 → square; `long_side` of 1080×1920 is 1920.
  - `test_sidecar_roundtrip`: `write_sidecar` then `read_sidecars()` returns one dict with `schema == 1`, `kind == "stock"`, `file == "clips/pixabay/42.mp4"`, keywords containing the query.
  - `test_sidecar_adds_query`: writing the same clip with query "launch" then "rocket" gives keywords containing both, no duplicates.
  - `test_has_clip_needs_both_files`: only the mp4 present → False; both → True.
  - `test_response_cache_age`: `put_response` at t=0; `get_response(max_age_s=86400)` at t=86399 returns data, at t=86401 returns None.
  - `test_index_rebuilt_from_sidecars`: delete `index.json`, `write_index()` recreates it with one entry per sidecar.
  - `test_match_all_words`: entry keywords `["rocket", "launch pad"]`: "rocket launch" matches, "rocket moon" does not; "Rocket" matches case-insensitively.
  - `test_match_orientation_first`: a vertical and a horizontal match, `orientation="vertical"` puts the vertical one first.
- [ ] **Step 2: Run** `cd .claude/skills/finding-stock-footage && python3 -m unittest tests.test_cache tests.test_index -v`. Expected: FAIL (`ModuleNotFoundError: model`).
- [ ] **Step 3: Implement** `model.py`, `cache.py`, `index.py` per Interfaces. Sidecars and index are written via a temp file + `os.replace`.
- [ ] **Step 4: Run** the same command. Expected: all PASS.
- [ ] **Step 5: Commit** `git add .claude/skills/finding-stock-footage && git commit -m "finder: candidate model, clip cache and index"`

### Task 2: Cached HTTP layer

**Files:**
- Create: `scripts/http_client.py` (not `http.py`, which would shadow the stdlib)
- Test: `tests/test_http_client.py`

**Interfaces:**
- Consumes: `Cache.get_response/put_response`, `SourceError`.
- Produces: `http_client.Http(cache: Cache, clock=time.time)` with
  - `get_json(slug, url, params: dict, headers: dict | None = None, secret_params: tuple = ()) -> dict`: cache key = `url` + sorted params minus `secret_params`; a hit younger than 86400 s is returned without a request. HTTP 429 → `SourceError(slug, "istek sınırı aşıldı (429)")`; other HTTP errors and `URLError` → `SourceError` with the reason. Never puts secret values in the error text.
  - `download(slug, url, dest: Path)`: streams to `dest.with_suffix(".part")`, then `os.replace` to `dest`; on any failure removes the `.part` and raises `SourceError`. `http://` URLs are upgraded to `https://`.
  - Every request sends `User-Agent: stock-finder/1.0`.

- [ ] **Step 1: Write the failing tests** using a local `http.server.ThreadingHTTPServer` on 127.0.0.1 in a thread (a handler that counts requests and serves JSON, a 429, a file, and a connection that drops halfway):
  - `test_second_call_served_from_cache`: two `get_json` calls → server saw 1 request.
  - `test_cache_expires_after_a_day`: fake clock advanced 86401 s → server saw 2 requests.
  - `test_secret_not_in_cache_key_or_file`: call with `params={"key": "SECRET", "q": "x"}, secret_params=("key",)`; no file under the cache root contains `SECRET`, and the same call with a different key value is a cache hit.
  - `test_429_raises_source_error`: message contains `429`, not the key.
  - `test_user_agent`: the handler saw `stock-finder/1.0`.
  - `test_interrupted_download_leaves_nothing` (Review Focus 4): the server closes mid-body (Content-Length larger than sent); `SourceError` raised, neither `dest` nor `.part` exists.
  - `test_download_ok`: bytes equal, no `.part` left.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_http_client -v`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** `http_client.py` with `urllib.request`. The https upgrade must not apply to the 127.0.0.1 test server: upgrade only when the host is not `127.0.0.1`/`localhost`.
- [ ] **Step 4: Run** it. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "finder: cached HTTP client with atomic downloads"`

### Task 3: Pixabay adapter

**Files:**
- Create: `scripts/sources/__init__.py` (empty for now), `scripts/sources/pixabay.py`, `tests/fixtures/pixabay_search.json`, `tests/fakes.py`
- Test: `tests/test_pixabay.py`

**Interfaces:**
- Consumes: `Candidate`, `Http.get_json`.
- Produces (the adapter contract every source follows):
  - module constants `SLUG = "pixabay"`, `NEEDS_KEY = True`
  - `class Source: __init__(self, cfg: dict, key: str | None, http)`, attributes `slug`, `priority`; `search(self, query: str, orientation: str) -> Iterator[Candidate]` (one page of 20 results, in the API's order, lazily).
  - `tests/fakes.FakeHttp(responses: dict[str, dict])`: `get_json` returns the fixture whose key is a substring of the URL; records calls; `download` writes `b"video"`.
- Pixabay specifics: request `GET cfg["url"]` with `key, q, per_page=20, safesearch=true`, `secret_params=("key",)`; rendition = largest of `large/medium/small/tiny` with a non-empty `url` and long side ≤ 3840; `title` = `tags`; `keywords` = tags split on `", "`; `creator` = `user`; `credit` = `"Pixabay / <user>"`; `licence` = `"Pixabay Content License"`; `fps` = None; `page_url` = `pageURL`.

- [ ] **Step 1: Record the fixture.** With `source ~/.bashrc` loaded, fetch one real response for `q=rocket launch&per_page=20` once, replace the `key` anywhere it appears, trim to 4 hits, and make sure at least one hit has `large.url == ""` (edit one if none does). Save as `tests/fixtures/pixabay_search.json`. Check: `grep -c "$PIXABAY_API_KEY" tests/fixtures/pixabay_search.json` prints 0.
- [ ] **Step 2: Write the failing tests**
  - `test_maps_fields`: first candidate has `source == "pixabay"`, `credit` starting `"Pixabay / "`, `page_url` from `pageURL`, `fps is None`, `download_url` equal to the `large.url`.
  - `test_empty_large_falls_back_to_medium` (Review Focus 2).
  - `test_key_sent_but_secret`: FakeHttp saw `key` in params and `secret_params == ("key",)`.
  - `test_lazy`: taking one candidate from the iterator makes exactly 1 `get_json` call.
- [ ] **Step 3: Run** `python3 -m unittest tests.test_pixabay -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `sources/pixabay.py` and `tests/fakes.py`.
- [ ] **Step 5: Run** it. Expected: PASS.
- [ ] **Step 6: Commit** `git commit -m "finder: Pixabay adapter"`

### Task 4: NASA adapter

**Files:**
- Create: `scripts/sources/nasa.py`, `tests/fixtures/nasa_search.json`, `tests/fixtures/nasa_asset.json`, `tests/fixtures/nasa_metadata.json`, `tests/fixtures/nasa_metadata_thirdparty.json`
- Test: `tests/test_nasa.py`

**Interfaces:**
- Consumes: adapter contract from Task 3.
- Produces: `SLUG = "nasa"`, `NEEDS_KEY = False`, `Source`; plus `nasa.credit_for(meta: dict) -> tuple[str, bool]` (credit line, third_party).
- NASA specifics: search `GET {url}/search` with `q, media_type=video, page_size=20`; per hit, lazily, `GET {url}/asset/{nasa_id}` and the `metadata.json` from that list (both through `get_json`, so cached). Width/height from `QuickTime:ImageWidth/ImageHeight`, fps from `QuickTime:VideoFrameRate`, duration from `QuickTime:Duration` in `H:MM:SS(.fff)` or `"<number> s"`. Rendition `~orig.mp4` if its long side ≤ 3840, else `~large.mp4` with width/height scaled to long side 1920. `page_url` = `https://images.nasa.gov/details/<nasa_id>`; `title`, `description`, `keywords` from the search hit; `licence` = `"NASA Images and Media Usage Guidelines"`.
- Credit rule: credit text = `XMP:Credit`, else `XMP:Creator` (list joined with `", "`), else empty. Plain NASA when empty or when it contains a word `NASA`, `JPL`, or a NASA center code (`ARC AFRC GRC GSFC JSC KSC LaRC MSFC SSC WFF HQ`), case-insensitive. Plain: credit line `"NASA"` if empty, else `"NASA / <credit>"` unless the credit already starts with `NASA`, then the credit itself. Third party: credit line `"NASA / <credit>"`, warning `"NASA dışı içerik (<credit>): kullanım hakkını kontrol et"`.

- [ ] **Step 1: Record fixtures** from the live API (no key needed): search `rocket launch` trimmed to 4 hits; one asset list; one metadata with a NASA credit; the Rocket Lab metadata (`KSC-20230507-MH-RLS01-TROPICS_Rocket_Launch-Rocket_Lab-WON_3330130`) as `nasa_metadata_thirdparty.json`.
- [ ] **Step 2: Write the failing tests**
  - `test_credit_rule` table: `""`→(`"NASA"`, False); `"NASA/JPL-Caltech"`→(`"NASA/JPL-Caltech"`, False); `"NASA/Bill Ingalls"`→ plain; `"KSC"`→(`"NASA / KSC"`, False); `"Rocket Lab"`→(`"NASA / Rocket Lab"`, True); `"ESA"`→ third party; Creator list `["SpaceX"]` with no Credit → third party.
  - `test_third_party_candidate_has_warning`: candidate from the Rocket Lab fixture has the warning text and credit `"NASA / Rocket Lab"`.
  - `test_dimensions_fps_duration`: 1920, 1080, 50.0, 30.0 from the fixture.
  - `test_duration_formats`: `"0:00:30"`→30.0, `"0:01:02.5"`→62.5, `"12.5 s"`→12.5.
  - `test_missing_orig_or_metadata_skipped` (Review Focus 1): an asset list without any `.mp4`, and a hit whose metadata `get_json` raises `SourceError`, are skipped; the next hit is still yielded.
  - `test_https_and_lazy`: `download_url` starts with `https://`; taking one candidate fetches search + 1 asset + 1 metadata only.
- [ ] **Step 3: Run** `python3 -m unittest tests.test_nasa -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `sources/nasa.py`.
- [ ] **Step 5: Run** it. Expected: PASS.
- [ ] **Step 6: Commit** `git commit -m "finder: NASA adapter with third-party credit rule"`

### Task 5: Pexels adapter and source loading

**Files:**
- Create: `scripts/sources/pexels.py`, `tests/fixtures/pexels_search.json`, `.claude/skills/finding-stock-footage/sources.json`
- Modify: `scripts/sources/__init__.py`
- Test: `tests/test_pexels.py`, `tests/test_sources.py`

**Interfaces:**
- Produces:
  - `SLUG = "pexels"`, `NEEDS_KEY = True`, `Source`: `GET {url}search` with `query, per_page=20`, `orientation=portrait` when vertical else `landscape`, header `Authorization: <key>` (headers are never cached or logged); rendition = largest `video_files` entry with `file_type == "video/mp4"` and long side ≤ 3840; fps from that file; `creator` = `user.name`; `title` from the last path segment of `url` with the trailing id and dashes removed; `credit` = `"Pexels / <name>"`; `licence` = `"Pexels License"`.
  - `sources.load_sources(config_path: Path, env: Mapping, http, only: list[str] | None = None) -> tuple[list[Source], list[str]]`: reads the JSON, keeps `isEnabled` entries (and only those in `only` if given), imports `sources.<slug>`; a `NEEDS_KEY` source without `<SLUG>_API_KEY` in `env` is skipped with note `"<slug>: <SLUG>_API_KEY yok, atlandı"`; a slug with no module → note `"<slug>: bu kaynak için kod yok, atlandı"`; returns sources sorted by `priority` ascending.
  - `sources.json` exactly as in the spec (pixabay 1 enabled, nasa 2 enabled, pexels 3 disabled, Pexels URL `https://api.pexels.com/v1/videos/`).

- [ ] **Step 1: Fixture.** Copy the "Search for Videos" example response from https://www.pexels.com/api/documentation/#videos-search into `tests/fixtures/pexels_search.json`; add an `fps` to each `video_files` entry if the sample lacks it.
- [ ] **Step 2: Write the failing tests**
  - Pexels: `test_maps_fields` (credit `"Pexels / <name>"`, fps present, mp4 only), `test_orientation_param` (vertical → `portrait`), `test_auth_header_not_in_params`.
  - Loading: `test_priority_order` (nasa priority 1, pixabay 2 in a temp config → nasa first); `test_disabled_skipped_silently`; `test_missing_key_note` (`"pixabay: PIXABAY_API_KEY yok, atlandı"`, NASA still loaded); `test_unknown_slug_note`; `test_only_filter`; `test_shipped_config` (the real `sources.json` loads with an env holding `PIXABAY_API_KEY` → `[pixabay, nasa]`, no notes).
- [ ] **Step 3: Run** `python3 -m unittest tests.test_pexels tests.test_sources -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `sources/pexels.py`, `load_sources`, `sources.json`.
- [ ] **Step 5: Run** it. Expected: PASS.
- [ ] **Step 6: Commit** `git commit -m "finder: Pexels adapter (disabled) and sources.json loading"`

### Task 6: Finder core

**Files:**
- Create: `scripts/finder.py`
- Test: `tests/test_finder.py`

**Interfaces:**
- Consumes: `Cache`, `index.match`, `Candidate`, `SourceError`, adapters (`search`), `Http.download`.
- Produces:
  - `finder.Request` dataclass: `query: str, code: str, orientation: str = "horizontal", count: int = 3, min_duration: float = 4, max_duration: float = 120, fresh: bool = False, exclude: set[tuple[str, str]] = set()` (source, id pairs already delivered for this code).
  - `finder.Pick` dataclass: `entry: dict` (sidecar), `path: Path` (cached mp4), `from_cache: bool`.
  - `finder.find(req: Request, sources: list, cache: Cache, http, now: datetime) -> tuple[list[Pick], list[str]]` (picks in final order, notes).
- Behaviour:
  1. Unless `fresh`: `index.match` over the current index, drop `exclude`, drop entries failing the filters; those are local picks.
  2. If local picks ≥ `count` in the wanted orientation: return the first `count`, no source called.
  3. Otherwise iterate the sources' iterators round-robin in list order (already priority-sorted), skipping excluded, already-picked and filter-failing candidates, until each iterator is exhausted or 20 candidates per source were inspected. A `SourceError` from a source adds note `"<slug>: <message>"` and drops that source.
  4. Order: orientation rank (wanted 0, square 1, other 2), then local picks before API picks, then round-robin position. Take `count`.
  5. Download chosen API candidates not already cached (`cache.has_clip`) via `http.download` to `cache.clip_path`; write/refresh sidecars with the query for every pick; a download `SourceError` drops that pick, adds a note and the next ranked candidate takes its place. Finally `cache.write_index()`.
  6. Fewer than `count`: note `"<code>: <n>/<count> aday bulundu"`.
- Filters: `min_duration ≤ duration_s ≤ max_duration` and `long_side ≥ 1280`.

- [ ] **Step 1: Write the failing tests** with fake sources (lists of Candidates) and `FakeHttp`:
  - `test_round_robin`: A=[a1,a2,a3], B=[b1,b2], count 4 → a1, b1, a2, b2.
  - `test_vertical_first_then_fill`: wanted vertical; A has 1 vertical among horizontals → it is first, horizontals fill the rest.
  - `test_filters`: a 3 s clip, a 200 s clip and a 1000×562 clip are never picked.
  - `test_local_match_avoids_api`: cache holds 3 matching horizontal clips → sources' iterators never advanced, picks `from_cache=True`.
  - `test_fresh_skips_local_match`: same cache, `fresh=True` → sources are asked.
  - `test_cached_clip_not_redownloaded`: an API candidate already in the cache → no `download` call, `from_cache=True`.
  - `test_exclude`: excluded (source, id) is never picked.
  - `test_source_error_noted`: one source raises `SourceError` → note present, other source still delivers.
  - `test_failed_download_replaced`: first pick's download raises → next ranked candidate picked, note added.
  - `test_short_note`: count 3, only 1 found → note `"R1: 1/3 aday bulundu"`.
  - `test_sidecar_and_index_written`: after a run, `index.json` lists the picks with the query in keywords.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_finder -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `finder.py`.
- [ ] **Step 4: Run** it. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "finder: filtering, ranking, local match and downloads"`

### Task 7: Delivery

**Files:**
- Create: `scripts/deliver.py`
- Test: `tests/test_deliver.py`

**Interfaces:**
- Consumes: `Pick`.
- Produces:
  - `deliver.slugify(text: str) -> str`: Turkish letters folded to ASCII (ç→c, ğ→g, ı→i, İ→i, ö→o, ş→s, ü→u), lower case, runs of non `[a-z0-9]` → `-`, stripped of `-`, max 40 chars, `"stok"` if empty.
  - `deliver.load_results(out: Path) -> dict` (empty `{"created": None, "notes": [], "requests": []}` if absent).
  - `deliver.delivered(results: dict, code: str) -> set[tuple[str, str]]`.
  - `deliver.add_request(out: Path, results: dict, query, code, orientation, picks: list[Pick], notes: list[str]) -> dict`: names files `<code>-<n>_<source>-<id>.mp4` with `n` continuing after the highest `n` recorded for `code` in `results` (not on disk); links with `os.link`, falls back to `shutil.copy2` on `OSError`; appends to the existing request with the same `code` or adds a new one; returns the request entry. Candidate fields as in the spec, `from_cache` from the Pick.
  - `deliver.save(out: Path, results: dict, notes: list[str], now: datetime)`: sets `created` if None, appends run notes, writes `results.json` (temp + replace) and regenerates `kaynaklar.txt` from all candidates in all requests: one line `"<credit>: <page_url>"` per candidate, first occurrence order, duplicates removed.

- [ ] **Step 1: Write the failing tests**
  - `test_slugify` (Review Focus 3): `"Ay'a iniş!"` → `"ay-a-inis"`, `"rocket launch"` → `"rocket-launch"`, `"!!!"` → `"stok"`.
  - `test_names_and_links`: two picks for code R12 → `R12-1_pixabay-1.mp4`, `R12-2_nasa-X.mp4`, same inode as the cache file.
  - `test_copy_fallback`: `os.link` patched to raise `OSError` → file copied.
  - `test_rerun_continues_numbering`: existing results with R12-1..3 → new pick named `R12-4`, old entries kept, existing files untouched (mtime and inode unchanged).
  - `test_rerun_after_editor_deleted_file` (Review Focus 5): R12-2 file removed from disk → next is still `R12-4`, no error.
  - `test_same_clip_two_codes`: one cached clip delivered for R1 and R2 → two files, both linked.
  - `test_kaynaklar`: lines `"Pixabay / kullanici: https://pixabay.com/videos/id-1/"` and `"NASA / Rocket Lab: https://images.nasa.gov/details/X"`, a clip in two requests listed once.
  - `test_results_shape`: `results.json` has `created`, `notes`, `requests[0].candidates[0]` with exactly the spec's candidate keys.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_deliver -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `deliver.py`.
- [ ] **Step 4: Run** it. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "finder: delivery, naming, results.json and kaynaklar.txt"`

### Task 8: CLI

**Files:**
- Create: `scripts/find_stock.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_sources`, `Cache`, `Http`, `finder.find`, `deliver.*`.
- Produces: `find_stock.main(argv: list[str], env: Mapping = os.environ, http_factory=Http, now=None) -> int`, and `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`.
  - Arguments: positional `query` (optional), `--count 3`, `--orientation {horizontal,vertical}`, `--out`, `--code`, `--sources a,b`, `--min-duration 4`, `--max-duration 120`, `--fresh`, `--batch FILE` (JSON list of `{code, query, orientation?, count?}`), `--reindex`, `--config` (default `<skill>/sources.json`), `--cache` (default `<repo>/assets/stock`, repo = `Path(__file__).resolve().parents[4]`).
  - Exactly one of `query`, `--batch`, `--reindex`; otherwise usage error, exit 1. `--batch` requires `--out`.
  - Default `--code` = `slugify(query)`; default `--out` = `~/Downloads/stok/<slugify(query)>/`.
  - `--reindex`: `cache.write_index()`, prints `"<n> klip dizinlendi"`, exit 0.
  - Summary to stdout, one line per candidate: `"<code>  <source>  <w>x<h>  <duration rounded> sn  <yatay|dikey|kare>[  önbellekten]"`, each warning on the next line prefixed `"  ! "`, then all notes, then `"Klasör: <out>"` and `"Kaynaklar: <out>/kaynaklar.txt"`.
  - Exit 2 with `"Hiç aday bulunamadı. Başka anahtar kelimeler deneyin."` when every request got 0 candidates; exit 1 with the error on unexpected exceptions.

- [ ] **Step 1: Write the failing tests** (FakeHttp via `http_factory`, temp cache/out, a temp config enabling only the fake-backed sources):
  - `test_single_query_end_to_end`: exit 0, `results.json` with one request, 3 files, summary lines contain `"sn"` and `"Klasör:"`.
  - `test_default_out_and_code`: with `HOME` pointed at a temp dir, `"rocket launch"` delivers into `<tmp>/Downloads/stok/rocket-launch/` with files `rocket-launch-1_...`.
  - `test_batch`: two requests → one `results.json` with two requests in one `--out`.
  - `test_batch_one_empty_row`: one row with no results → exit 0, note for that row.
  - `test_nothing_found`: exit 2 and the Turkish message.
  - `test_missing_key_still_delivers`: env without `PIXABAY_API_KEY` → NASA results, note printed.
  - `test_key_never_printed`: with `PIXABAY_API_KEY=SECRETKEY`, stdout, `results.json` and all cache files do not contain `SECRETKEY`.
  - `test_reindex`, `test_usage_errors`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_cli -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `find_stock.py`.
- [ ] **Step 4: Run** the whole suite. Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -m "finder: find_stock.py CLI with batch and reindex"`

### Task 9: Keep the stock cache out of the brand pack check

**Files:**
- Modify: `scripts/fetch-assets.sh:88-93` (`list_files`)
- Test: `.claude/skills/finding-stock-footage/tests/test_fetch_assets.py`

**Interfaces:**
- Produces: `list_files` excludes `./stock/*`, so `verify` and `manifest` both ignore `assets/stock/`.

- [ ] **Step 1: Write the failing test**: build a temp `ASSETS_DEST` with `a.txt` and an `assets.sha256` listing it (`sha256sum`), add `stock/clips/nasa/x.mp4`; run `ASSETS_DEST=<tmp> bash scripts/fetch-assets.sh verify`; assert exit 0 and no `"unexpected file"` in stderr. Second test: `manifest` on the same dir writes an `assets.sha256` without `stock/`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_fetch_assets -v`. Expected: FAIL with `unexpected file: stock/clips/nasa/x.mp4`.
- [ ] **Step 3: Implement**: add `! -path './stock/*'` to `list_files`, and a comment above it saying the stock cache is managed by the finding-stock-footage skill.
- [ ] **Step 4: Run** it, then the whole suite. Expected: PASS.
- [ ] **Step 5: Commit** `git add scripts/fetch-assets.sh .claude/skills/finding-stock-footage/tests/test_fetch_assets.py && git commit -m "fetch-assets: ignore the stock footage cache"`

### Task 10: Skill, live test and acceptance

**Files:**
- Create: `.claude/skills/finding-stock-footage/SKILL.md`, `tests/test_live.py`

**Interfaces:**
- Consumes: the CLI.

- [ ] **Step 1: Write `tests/test_live.py`**, skipped unless `STOCK_LIVE=1`: one real NASA search through the adapter (yields ≥ 1 candidate with width, height and duration) and, if `PIXABAY_API_KEY` is set, one Pixabay search; one real download of the smallest Pixabay `tiny` rendition into a temp cache.
- [ ] **Step 2: Run** `source ~/.bashrc && STOCK_LIVE=1 python3 -m unittest tests.test_live -v`. Expected: PASS (NASA and Pixabay).
- [ ] **Step 3: Write `SKILL.md`**: frontmatter `name: finding-stock-footage`, `description: Use when an editor wants stock video footage for a description ("roket fırlatma görüntüsü", "rocket launch footage"), for a short or an episode, or when the B-roll skill needs candidates for STOK script rows - searching Pixabay, NASA and other configured stock sources, downloading candidates and collecting credits.` Body (under 500 words): what it is; turn the Turkish description into 2-4 English keywords; the command and its flags (point to `--help`); vertical for shorts; how to report (folder, summary, every `!` warning, especially `NASA dışı içerik`); keys come from `<SLUG>_API_KEY` in the environment and a session started before the key was added must `source ~/.bashrc`; adding a source = adapter in `scripts/sources/<slug>.py` + entry in `sources.json`; batch format for the B-roll skill; the cache is `assets/stock/` and `--reindex` rebuilds its index.
- [ ] **Step 4: Acceptance on this machine** (spec "Testing"), each checked by reading the output:
  - `python3 .claude/skills/finding-stock-footage/scripts/find_stock.py "rocket launch"` → 3 horizontal candidates in `~/Downloads/stok/rocket-launch/`, correct `kaynaklar.txt`.
  - The same command again → no new API request (verify: no new files under `assets/stock/searches/` and output says `önbellekten`), and numbering continues only if new clips were delivered.
  - `--orientation vertical --out <scratch>` → vertical clips first if any exist.
  - `env -u PIXABAY_API_KEY python3 ... "rocket launch" --out <scratch>` → NASA clips plus the missing-key note.
  - `bash scripts/fetch-assets.sh verify` reports no `assets/stock` files.
- [ ] **Step 5: Commit** `git add .claude/skills/finding-stock-footage && git commit -m "finding-stock-footage skill: SKILL.md and live tests"`
