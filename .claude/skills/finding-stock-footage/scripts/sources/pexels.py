"""Pexels video search (https://www.pexels.com/api/documentation/). Needs PEXELS_API_KEY; shipped disabled
until the team has a key. Pexels asks for a visible link to Pexels and credit to the creator."""
import re

from model import Candidate, best_rendition

SLUG = "pexels"
NEEDS_KEY = True
PER_PAGE = 20


def title_from_url(url):
    """https://www.pexels.com/video/video-of-forest-1448735/ -> 'video of forest'."""
    last = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"-?\d+$", "", last).replace("-", " ").strip()


class Source:
    def __init__(self, cfg, key, http):
        self.slug = SLUG
        self.priority = cfg.get("priority", 99)
        self.url = cfg["url"]
        self.key = key
        self.http = http

    def search(self, query, orientation):
        params = {"query": query, "per_page": PER_PAGE,
                  "orientation": "portrait" if orientation == "vertical" else "landscape"}
        data = self.http.get_json(SLUG, self.url + "search", params, headers={"Authorization": self.key})
        for v in data.get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
            best = best_rendition([(f.get("width") or 0, f.get("height") or 0, f.get("link", "")) for f in files])
            if best is None:
                continue
            fps = next((f.get("fps") for f in files if f.get("link") == best[2]), None)
            name = v.get("user", {}).get("name", "")
            title = title_from_url(v.get("url", ""))
            yield Candidate(source=SLUG, id=str(v["id"]), page_url=v.get("url", ""), creator=name, title=title,
                            description="", keywords=[title] if title else [], width=best[0], height=best[1],
                            fps=float(fps) if isinstance(fps, (int, float)) else None,
                            duration_s=float(v.get("duration", 0)), download_url=best[2], licence="Pexels License",
                            credit=f"Pexels / {name}")
