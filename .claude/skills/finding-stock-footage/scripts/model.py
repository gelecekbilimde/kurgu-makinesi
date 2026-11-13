"""The candidate every stock source adapter produces, and the error they raise."""
from dataclasses import dataclass, field


class SourceError(Exception):
    """A source failed (no key, rate limit, network). The run notes it and carries on with other sources."""

    def __init__(self, slug, message):
        super().__init__(f"{slug}: {message}")
        self.slug = slug
        self.message = message


@dataclass
class Candidate:
    source: str
    id: str
    page_url: str
    creator: str
    title: str
    description: str
    keywords: list
    width: int
    height: int
    fps: float | None
    duration_s: float
    download_url: str
    licence: str
    credit: str
    warnings: list = field(default_factory=list)

    @property
    def orientation(self):
        if self.width > self.height:
            return "horizontal"
        if self.height > self.width:
            return "vertical"
        return "square"

    @property
    def long_side(self):
        return max(self.width, self.height)


MAX_LONG_SIDE = 3840


def best_rendition(renditions):
    """The largest (width, height, url) with a url, real dimensions and long side <= 3840, or None."""
    ok = [r for r in renditions if r[2] and r[0] > 0 and r[1] > 0 and max(r[0], r[1]) <= MAX_LONG_SIDE]
    return max(ok, key=lambda r: r[0] * r[1], default=None)
