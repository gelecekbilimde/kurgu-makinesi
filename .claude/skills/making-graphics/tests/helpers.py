"""Shared test helpers: puts scripts/ on sys.path; paths to fixtures and the kit."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
FIXTURES = HERE / "fixtures"
KIT = SKILL / "kit" / "hf-kit.js"
REPO = SKILL.parents[2]
LIVE = os.environ.get("GRAPHICS_LIVE") == "1"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def make_root(tmp):
    """A graphics root in tmp: designs/{demo,other}, templates/demo/{demo,fixed}, config.json -> demo."""
    import json
    import shutil
    root = Path(tmp) / "graphics"
    shutil.copytree(FIXTURES / "designs", root / "designs")
    for name in ("demo", "fixed"):
        shutil.copytree(FIXTURES / "templates" / name, root / "templates" / "demo" / name)
    (root / "config.json").write_text(json.dumps({"design": "demo"}))
    return root
