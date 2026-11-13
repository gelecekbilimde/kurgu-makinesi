"""Shared test helpers: puts scripts/ on sys.path and builds candidates."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIXTURES = os.path.join(HERE, "fixtures")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from model import Candidate  # noqa: E402


def cand(source="pixabay", id="1", width=1920, height=1080, duration_s=10.0, title="rocket launch",
         keywords=None, **kw):
    fields = dict(source=source, id=str(id), page_url=f"https://example.org/{source}/{id}", creator="someone",
                  title=title, description="", keywords=list(keywords if keywords is not None else ["rocket"]),
                  width=width, height=height, fps=None, duration_s=duration_s,
                  download_url=f"https://example.org/{source}/{id}.mp4", licence="Test License",
                  credit=f"{source.capitalize()} / someone")
    fields.update(kw)
    return Candidate(**fields)
