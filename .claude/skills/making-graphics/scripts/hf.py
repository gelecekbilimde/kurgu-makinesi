"""Builds and runs HyperFrames / FFmpeg commands for the making-graphics skill.

Every HyperFrames call runs the pinned local binary with telemetry off. Nothing here signs in to HeyGen or uses
the cloud.
"""
import os
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[2]
HF_BIN = SKILL_DIR / "node_modules" / ".bin" / "hyperframes"
TELEMETRY_OFF = {"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
SETUP_HINT = "HyperFrames kurulu değil; önce çalıştırın: python3 .claude/skills/making-graphics/scripts/setup.py"
FFMPEG_HINT = ("FFmpeg ve FFprobe bulunamadı. Önce RPM Fusion deposunu etkinleştirin "
               "(https://rpmfusion.org/Configuration), sonra kendi terminalinizde çalıştırın: sudo dnf install ffmpeg")


class ToolError(Exception):
    """A tool (HyperFrames, FFmpeg) failed; the message is Turkish and fit to show the editor."""


def hf_env(base):
    env = dict(base)
    env.update(TELEMETRY_OFF)
    return env


def hf_cmd(*args):
    return [str(HF_BIN), *args]


def run(cmd, cwd, runner=subprocess.run):
    cmd = [str(c) for c in cmd]
    try:
        return runner(cmd, cwd=str(cwd), env=hf_env(os.environ), capture_output=True, text=True)
    except FileNotFoundError as err:
        tool = Path(cmd[0]).name
        if tool in ("ffmpeg", "ffprobe"):
            raise ToolError(FFMPEG_HINT) from None
        if tool == "hyperframes":
            raise ToolError(SETUP_HINT) from None
        raise ToolError(f"çalıştırılamadı: {err.filename or tool} bulunamadı") from None


def last_line(text):
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    return lines[-1] if lines else ""
