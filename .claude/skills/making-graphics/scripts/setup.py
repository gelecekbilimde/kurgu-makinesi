"""Check and prepare the toolchain for making-graphics.

  python3 .claude/skills/making-graphics/scripts/setup.py

Checks Node 22, npm, FFmpeg and FFprobe; installs the pinned HyperFrames (npm ci) when node_modules is missing;
fetches its Chrome (browser ensure); turns telemetry off; runs `hyperframes doctor`. Never runs sudo: missing system
packages are reported with the command to run. Exit 0 when everything is ready, 1 otherwise.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hf  # noqa: E402

FFMPEG_HINT = hf.FFMPEG_HINT


def check(which=shutil.which, run=subprocess.run):
    problems = []
    if not which("node"):
        problems.append("Node bulunamadı. Node 22 kurun (sudo dnf install nodejs22).")
    else:
        out = run(["node", "--version"], capture_output=True, text=True).stdout.strip()
        m = re.match(r"v(\d+)", out)
        if not m or int(m.group(1)) < 22:
            problems.append(f"Node sürümü {out or 'bilinmiyor'}; Node 22 veya üstü gerekli.")
    if not which("npm"):
        problems.append("npm bulunamadı. Node 22 ile birlikte kurun.")
    if not which("ffmpeg") or not which("ffprobe"):
        problems.append(FFMPEG_HINT)
    return problems


def _step(cmd, cwd, label):
    r = hf.run(cmd, cwd)
    if r.returncode != 0:
        return [f"{label} başarısız: {hf.last_line(r.stderr) or hf.last_line(r.stdout)}"]
    return []


def main():
    problems = check()
    if not any("npm" in p or "Node" in p for p in problems):
        if not hf.HF_BIN.exists():
            print("HyperFrames kuruluyor (npm ci)...")
            problems += _step(["npm", "ci", "--no-fund", "--no-audit"], hf.SKILL_DIR, "npm ci")
        if hf.HF_BIN.exists():
            problems += _step(hf.hf_cmd("browser", "ensure"), hf.SKILL_DIR, "Chrome kurulumu (browser ensure)")
            _step(hf.hf_cmd("telemetry", "disable"), hf.SKILL_DIR, "telemetri kapatma")
            r = hf.run(hf.hf_cmd("doctor"), hf.SKILL_DIR)
            fails = [x.strip() for x in r.stdout.splitlines() if "✗" in x]
            problems += [f"hyperframes doctor: {x}" for x in fails
                         if not re.search(r"ffmpeg|ffprobe|docker|optional|available", x, re.I)]
    for p in problems:
        print(f"Eksik: {p}", file=sys.stderr)
    if not problems:
        print("Hazır: Node, FFmpeg, HyperFrames ve Chrome kurulu.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
