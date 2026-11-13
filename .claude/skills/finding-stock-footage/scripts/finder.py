"""Find stock candidates for one request: local cache first, then the sources, then download into the cache.

Order of candidates: wanted orientation first (square next, the other orientation last), then clips already in
the cache that match the query, then API results with the sources taking turns in priority order.
"""
from dataclasses import dataclass, field
from pathlib import Path

import index
from model import SourceError

INSPECT_PER_SOURCE = 20   # hits looked at per source, per request
SPARE = 2                 # extra wanted-orientation candidates kept in case a download fails
MIN_LONG_SIDE = 1280


@dataclass
class Request:
    query: str
    code: str
    orientation: str = "horizontal"
    count: int = 3
    min_duration: float = 4
    max_duration: float = 120
    fresh: bool = False
    exclude: set = field(default_factory=set)


@dataclass
class Pick:
    entry: dict      # the clip's sidecar
    path: Path       # the clip in the cache
    from_cache: bool


def _orient_rank(orientation, wanted):
    return 0 if orientation == wanted else 1 if orientation == "square" else 2


def _passes(req, duration_s, width, height):
    return req.min_duration <= (duration_s or 0) <= req.max_duration and max(width or 0, height or 0) >= MIN_LONG_SIDE


def _local(req, cache):
    found = []
    for e in index.match(cache.read_index(), req.query, req.orientation):
        key = (e["source"], e["id"])
        if key in req.exclude or not cache.has_clip(*key):
            continue
        if _passes(req, e.get("duration_s"), e.get("width"), e.get("height")):
            found.append(e)
    return found


def _round_robin(req, sources, taken, wanted_have, notes):
    """API candidates in turn order, stopping once there are enough in the wanted orientation."""
    iters = [(s.slug, iter(s.search(req.query, req.orientation))) for s in sources]
    pulled = {slug: 0 for slug, _ in iters}
    out = []
    while iters and wanted_have < req.count + SPARE:
        for slug, it in list(iters):
            try:
                if pulled[slug] >= INSPECT_PER_SOURCE:
                    raise StopIteration
                c = next(it)
                pulled[slug] += 1
            except StopIteration:
                iters.remove((slug, it))
                continue
            except SourceError as err:
                notes.append(str(err))
                iters.remove((slug, it))
                continue
            key = (c.source, c.id)
            if key in req.exclude or key in taken or not _passes(req, c.duration_s, c.width, c.height):
                continue
            taken.add(key)
            out.append(c)
            if c.orientation == req.orientation:
                wanted_have += 1
    return out


def find(req, sources, cache, http, now):
    """(picks in final order, notes)."""
    notes = []
    local = [] if req.fresh else _local(req, cache)
    wanted_local = sum(1 for e in local if e.get("orientation") == req.orientation)
    if wanted_local >= req.count:
        picks = [Pick(cache.add_query(e["source"], e["id"], req.query), cache.clip_path(e["source"], e["id"]), True)
                 for e in local[:req.count]]
        cache.write_index()
        return picks, notes

    taken = {(e["source"], e["id"]) for e in local}
    api = _round_robin(req, sources, taken, wanted_local, notes)
    ranked = [(_orient_rank(e.get("orientation"), req.orientation), 0, i, e) for i, e in enumerate(local)]
    ranked += [(_orient_rank(c.orientation, req.orientation), 1, i, c) for i, c in enumerate(api)]
    ranked.sort(key=lambda r: r[:3])

    picks = []
    for _, is_api, _, item in ranked:
        if len(picks) >= req.count:
            break
        if not is_api:
            side = cache.add_query(item["source"], item["id"], req.query)
            picks.append(Pick(side, cache.clip_path(item["source"], item["id"]), True))
            continue
        from_cache = cache.has_clip(item.source, item.id)
        if not from_cache:
            try:
                http.download(item.source, item.download_url, cache.clip_path(item.source, item.id))
            except SourceError as err:
                notes.append(str(err))
                continue
        side = cache.write_sidecar(item, req.query, now)
        picks.append(Pick(side, cache.clip_path(item.source, item.id), from_cache))

    if len(picks) < req.count:
        notes.append(f"{req.code}: {len(picks)}/{req.count} aday bulundu")
    cache.write_index()
    return picks, notes
