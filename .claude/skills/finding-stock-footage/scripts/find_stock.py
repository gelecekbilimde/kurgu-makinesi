"""Find and download stock video candidates for a plain description.

  python3 find_stock.py "rocket launch" [--count 3] [--orientation horizontal|vertical] [--out DIR] [--code CODE]
                        [--sources pixabay,nasa] [--min-duration 4] [--max-duration 120] [--fresh]
  python3 find_stock.py --batch requests.json --out DIR      # [{"code", "query", "orientation"?, "count"?}, ...]
  python3 find_stock.py --reindex                            # rebuild assets/stock/index.json from the sidecars

Keys come from <SLUG>_API_KEY environment variables; sources are configured in sources.json next to scripts/.
Exit codes: 0 delivered something, 2 nothing found, 1 any other failure.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import deliver  # noqa: E402
from cache import Cache  # noqa: E402
from finder import Request, find  # noqa: E402
from http_client import Http  # noqa: E402
from sources import load_sources  # noqa: E402

DEFAULT_CONFIG = HERE.parent / "sources.json"
DEFAULT_CACHE = HERE.parents[3] / "assets" / "stock"
ORIENT_TR = {"horizontal": "yatay", "vertical": "dikey", "square": "kare"}
NOTHING = "Hiç aday bulunamadı. Başka anahtar kelimeler deneyin."


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def parse(argv):
    p = Parser(prog="find_stock.py", description=__doc__.split("\n\n")[0])
    p.add_argument("query", nargs="?")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--orientation", choices=["horizontal", "vertical"], default="horizontal")
    p.add_argument("--out")
    p.add_argument("--code")
    p.add_argument("--sources")
    p.add_argument("--min-duration", type=float, default=4)
    p.add_argument("--max-duration", type=float, default=120)
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--batch")
    p.add_argument("--reindex", action="store_true")
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    a = p.parse_args(argv)
    if sum([a.query is not None, a.batch is not None, a.reindex]) != 1:
        raise UsageError("bir arama, --batch veya --reindex verin (yalnızca biri)")
    if a.batch and not a.out:
        raise UsageError("--batch için --out gerekli")
    return a


def _summary_line(c):
    line = (f"{c['code']}  {c['source']}  {c['width']}x{c['height']}  {round(c['duration_s'])} sn  "
            f"{ORIENT_TR.get(c['orientation'], c['orientation'])}")
    return line + ("  önbellekten" if c["from_cache"] else "")


def _run_rows(rows, a, sources, cache, http, now, out, results, delivered_now):
    for row in rows:
        req = Request(query=row["query"], code=row["code"],
                      orientation=row.get("orientation", a.orientation), count=row.get("count", a.count),
                      min_duration=a.min_duration, max_duration=a.max_duration, fresh=a.fresh,
                      exclude=deliver.delivered(results, row["code"]))
        picks, notes = find(req, sources, cache, http, now)
        entry = deliver.add_request(out, results, req.query, req.code, req.orientation, picks, notes)
        new = entry["candidates"][len(entry["candidates"]) - len(picks):] if picks else []
        delivered_now.append((new, notes))


def main(argv, env=os.environ, http_factory=Http, now=None):
    try:
        a = parse(argv)
    except UsageError as err:
        print(f"Kullanım hatası: {err}", file=sys.stderr)
        return 1
    try:
        now = now or datetime.now().astimezone()
        cache = Cache(Path(a.cache))
        if a.reindex:
            print(f"{len(cache.write_index())} klip dizinlendi")
            return 0
        if a.batch:
            with open(a.batch, encoding="utf-8") as f:
                rows = json.load(f)
            out = Path(a.out)
        else:
            rows = [{"query": a.query, "code": a.code or deliver.slugify(a.query)}]
            home = Path(env.get("HOME") or Path.home())
            out = Path(a.out) if a.out else home / "Downloads" / "stok" / deliver.slugify(a.query)

        http = http_factory(cache)
        only = [s.strip() for s in a.sources.split(",") if s.strip()] if a.sources else None
        sources, run_notes = load_sources(a.config, env, http, only=only)
        results = deliver.load_results(out)
        delivered_now = []
        try:
            _run_rows(rows, a, sources, cache, http, now, out, results, delivered_now)
        finally:
            deliver.save(out, results, run_notes, now)  # rows done so far keep their results and credits

        for new, notes in delivered_now:
            for c in new:
                print(_summary_line(c))
                for w in c["warnings"]:
                    print(f"  ! {w}")
        for note in run_notes + [n for _, notes in delivered_now for n in notes]:
            print(f"Not: {note}")
        if not any(new for new, _ in delivered_now):
            print(NOTHING, file=sys.stderr)
            return 2
        print(f"Klasör: {out}")
        print(f"Kaynaklar: {out / 'kaynaklar.txt'}")
        return 0
    except Exception as err:  # noqa: BLE001  (a clear one-line error for the editor)
        print(f"Hata: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
