"""Shared test helpers: puts this skill's scripts/, placing-b-roll's and the rough cutter's scripts/ on sys.path."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
BROLL_SCRIPTS = SKILL.parent / "placing-b-roll" / "scripts"
ROUGH_SCRIPTS = SKILL.parent / "rough-cutting-a-roll" / "scripts"
for p in (ROUGH_SCRIPTS, BROLL_SCRIPTS, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def make_episode(tmp, **manifest) -> Path:
    """Write episode.json (defaults: prefix TEST, fps 25, language tr, frozen [], broll_frozen [], clips []) into a new dir in tmp."""
    n = 0
    while (Path(tmp) / f"episode{n}").exists():
        n += 1
    d = Path(tmp) / f"episode{n}"
    d.mkdir(parents=True)
    m = {"prefix": "TEST", "fps": 25, "language": "tr", "frozen": [], "broll_frozen": [], "clips": []}
    m.update(manifest)
    (d / "episode.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return d
