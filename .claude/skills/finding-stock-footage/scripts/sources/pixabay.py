"""Pixabay video search (https://pixabay.com/api/docs/). Needs PIXABAY_API_KEY.

The video API has no orientation filter, so orientation comes from each clip's size and the finder ranks.
Pixabay asks that search responses be cached for 24 hours (the HTTP layer does) and forbids mass downloads.
"""
from model import Candidate, best_rendition

SLUG = "pixabay"
NEEDS_KEY = True
PER_PAGE = 20


class Source:
    def __init__(self, cfg, key, http):
        self.slug = SLUG
        self.priority = cfg.get("priority", 99)
        self.url = cfg["url"]
        self.key = key
        self.http = http

    def search(self, query, orientation):
        data = self.http.get_json(SLUG, self.url, {"key": self.key, "q": query, "per_page": PER_PAGE,
                                                   "safesearch": "true"}, secret_params=("key",))
        for hit in data.get("hits", []):
            videos = hit.get("videos", {})
            best = best_rendition([(v.get("width", 0), v.get("height", 0), v.get("url", ""))
                                   for v in (videos.get(k, {}) for k in ("large", "medium", "small", "tiny"))])
            if best is None:
                continue
            tags = hit.get("tags", "")
            user = hit.get("user", "")
            yield Candidate(source=SLUG, id=str(hit["id"]), page_url=hit.get("pageURL", ""), creator=user,
                            title=tags, description="", keywords=[t for t in tags.split(", ") if t],
                            width=best[0], height=best[1], fps=None, duration_s=float(hit.get("duration", 0)),
                            download_url=best[2], licence="Pixabay Content License", credit=f"Pixabay / {user}")
