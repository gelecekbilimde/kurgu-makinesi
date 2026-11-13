"""NASA Image and Video Library (https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf). No key.

Search hits carry no size or duration, so each hit needs two more requests (its asset list and metadata.json),
made lazily, only for the hits the finder actually looks at, and cached by the HTTP layer.
The library includes third-party footage (Rocket Lab, SpaceX, ESA, ...): those are flagged and credited to
the third party, never as plain NASA.
"""
import re
import urllib.parse

from model import MAX_LONG_SIDE, Candidate, SourceError

SLUG = "nasa"
NEEDS_KEY = False
PAGE_SIZE = 20
LICENCE = "NASA Images and Media Usage Guidelines"
NASA_WORDS = {"NASA", "JPL"}
CENTERS = {"ARC", "AFRC", "GRC", "GSFC", "JSC", "KSC", "LARC", "MSFC", "SSC", "WFF", "HQ"}
LARGE_LONG_SIDE = 1920


def fix_url(href):
    """NASA lists files as http:// and with raw spaces; make them fetchable."""
    if href.startswith("http://"):
        href = "https://" + href[len("http://"):]
    return urllib.parse.quote(href, safe=":/~%@")


def credit_for(meta):
    """(credit line, third_party) from metadata.json: XMP:Credit, else XMP:Creator."""
    raw = meta.get("XMP:Credit") or meta.get("XMP:Creator") or ""
    credit = ", ".join(map(str, raw)) if isinstance(raw, list) else str(raw)
    credit = credit.strip()
    if not credit:
        return "NASA", False
    words = set(re.findall(r"[A-Z]+", credit.upper()))
    # NASA or JPL anywhere; a center code only when the credit is nothing but center codes ("KSC"),
    # so "SpaceX HQ" or "ARC Films" stay third party
    if words & NASA_WORDS or words <= CENTERS:
        return (credit if credit.upper().startswith("NASA") else f"NASA / {credit}"), False
    return f"NASA / {credit}", True


def parse_duration(value):
    """'0:00:30', '0:01:02.5', '12.5 s' or a number -> seconds; None if unreadable."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    m = re.fullmatch(r"(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*s", text)
    return float(m.group(1)) if m else None


def _scaled(width, height, long_side):
    f = long_side / max(width, height)
    return int(round(width * f / 2) * 2), int(round(height * f / 2) * 2)


class Source:
    def __init__(self, cfg, key, http):
        self.slug = SLUG
        self.priority = cfg.get("priority", 99)
        self.url = cfg["url"].rstrip("/")
        self.http = http

    def _get(self, url, params=None):
        return self.http.get_json(SLUG, url, params or {})

    def search(self, query, orientation):
        data = self._get(f"{self.url}/search", {"q": query, "media_type": "video", "page_size": PAGE_SIZE})
        for item in data.get("collection", {}).get("items", []):
            try:
                c = self._candidate(item)
            except SourceError as err:
                if "429" in err.message:
                    raise
                continue
            if c is not None:
                yield c

    def _candidate(self, item):
        hit = (item.get("data") or [{}])[0]
        nasa_id = hit.get("nasa_id")
        if not nasa_id:
            return None
        files = [i.get("href", "") for i in self._get(f"{self.url}/asset/{urllib.parse.quote(nasa_id)}")
                 .get("collection", {}).get("items", [])]
        orig = next((f for f in files if f.endswith("~orig.mp4")), None)
        large = next((f for f in files if f.endswith("~large.mp4")), None)
        meta_url = next((f for f in files if f.endswith("metadata.json")), None)
        if not (orig or large) or not meta_url:
            return None
        meta = self._get(fix_url(meta_url))
        width, height = meta.get("QuickTime:ImageWidth"), meta.get("QuickTime:ImageHeight")
        duration = parse_duration(meta.get("QuickTime:Duration"))
        if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0) or duration is None:
            return None
        if orig and max(width, height) <= MAX_LONG_SIDE:
            href = orig
        elif large:
            href = large
            width, height = _scaled(width, height, LARGE_LONG_SIDE)
        else:
            return None
        fps = meta.get("QuickTime:VideoFrameRate")
        credit, third_party = credit_for(meta)
        warnings = []
        if third_party:
            who = credit[len("NASA / "):]
            warnings.append(f"NASA dışı içerik ({who}): kullanım hakkını kontrol et")
        return Candidate(source=SLUG, id=nasa_id, page_url=f"https://images.nasa.gov/details/{urllib.parse.quote(nasa_id)}",
                         creator=credit, title=hit.get("title", ""), description=hit.get("description", ""),
                         keywords=list(hit.get("keywords", [])), width=width, height=height,
                         fps=float(fps) if isinstance(fps, (int, float)) else None, duration_s=duration,
                         download_url=fix_url(href), licence=LICENCE, credit=credit, warnings=warnings,
                         third_party=third_party)
