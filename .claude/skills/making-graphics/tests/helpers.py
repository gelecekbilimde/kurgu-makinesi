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
