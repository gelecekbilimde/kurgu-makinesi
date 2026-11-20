"""Stills for B-roll rows: placeholders (FFmpeg drawtext), KAYNAK screenshots (HyperFrames' Chrome) and the
fully built frame of a graphic that is shorter than its row (hold).

Every function takes a `runner` (default subprocess.run) so tests never start FFmpeg or Chrome.
"""
import functools
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

GRAPHICS_DIR = Path(__file__).resolve().parents[2] / "making-graphics"
W, H = 1920, 1080
WRAP = 60
MIN_SHOT_BYTES = 20_000
BLOCKED = "sayfa engelli olabilir"
FAILED = "sayfa açılmadı"
TELEMETRY_OFF = {"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
# placeholder look: (font size, max description lines); full frame on dark grey, overlay on a lower-third band
FULL = (54, 12)
OVERLAY = (40, 2)
FULL_BG = "0x303030"
BAND = ("black@0.6", int(H * 0.72), int(H * 0.2))  # colour, top, height


class StillError(Exception):
    """FFmpeg/fc-match failed; the message is Turkish and fit to show the editor."""


@functools.lru_cache(maxsize=None)
def _font(runner=subprocess.run):
    try:
        p = runner(["fc-match", "-f", "%{file}", "sans"], capture_output=True, text=True)
    except FileNotFoundError:
        raise StillError("fc-match bulunamadı (fontconfig kurulu değil)") from None
    path = (p.stdout or "").strip()
    if p.returncode != 0 or not path:
        raise StillError("yazı tipi bulunamadı: fc-match -f '%{file}' sans boş döndü")
    return path


def _q(value):
    """Quote a value for an FFmpeg filter option."""
    return "'" + str(value).replace("'", r"'\''") + "'"


def _text(row_id, tag, text, max_lines):
    lines = textwrap.wrap(" ".join(str(text or "").split()), WRAP) or []
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:WRAP - 1].rstrip() + "…"
    return "\n".join([f"{row_id} · {tag}", *lines]) + "\n"


def placeholder(out, row_id, tag, text, overlay, runner=subprocess.run):
    """A 1920x1080 PNG with "<row_id> · <tag>" and the wrapped description: full frame dark grey, or (overlay)
    transparent with a lower-third band. Raises StillError."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    size, max_lines = OVERLAY if overlay else FULL
    font = _font(runner)
    fd, tf = tempfile.mkstemp(prefix=out.stem + "-", suffix=".txt", dir=out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_text(row_id, tag, text, max_lines))
        draw = (f"drawtext=fontfile={_q(font)}:textfile={_q(tf)}:fontsize={size}:fontcolor=white"
                f":line_spacing={size // 3}:x=(w-text_w)/2")
        if overlay:  # the band padded with transparency (drawbox can't write alpha); drawtext keeps alpha
            colour, top, height = BAND
            src = f"color=c={colour}:s={W}x{height}:d=1,format=rgba,pad={W}:{H}:0:{top}:color=black@0"
            vf = f"{draw}:y={top}+({height}-text_h)/2"
        else:
            src = f"color=c={FULL_BG}:s={W}x{H}:d=1"
            vf = f"{draw}:y=(h-text_h)/2"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-vf", vf, "-frames:v", "1"]
        if overlay:
            cmd += ["-pix_fmt", "rgba"]
        cmd.append(str(out))
        try:
            p = runner(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise StillError("FFmpeg bulunamadı; kurulum için making-graphics setup.py'ye bakın") from None
        if p.returncode != 0 or not out.exists():
            last = ((p.stderr or "").strip().splitlines() or [""])[-1]
            raise StillError(f"yer tutucu üretilemedi ({out.name}): {last}")
    finally:
        try:
            os.unlink(tf)
        except OSError:
            pass
    return out


@functools.lru_cache(maxsize=None)
def _chrome(runner=subprocess.run):
    try:
        p = runner(["npx", "--no-install", "hyperframes", "browser", "path"], cwd=str(GRAPHICS_DIR),
                   env={**os.environ, **TELEMETRY_OFF}, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = (p.stdout or "").strip().splitlines()
    return lines[-1].strip() if p.returncode == 0 and lines else None


def screenshot(url, out, timeout_s=30, runner=subprocess.run):
    """1920x1080 screenshot of url into out. None when it worked, else the note: FAILED or BLOCKED."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    chrome = _chrome(runner)
    if not chrome:
        return FAILED
    cmd = [chrome, "--headless", "--hide-scrollbars", f"--window-size={W},{H}", f"--screenshot={out}", url]
    try:
        p = runner(cmd, capture_output=True, text=True, timeout=timeout_s)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return FAILED
    if p.returncode != 0 or not out.exists():
        return FAILED
    if out.stat().st_size < MIN_SHOT_BYTES:
        return BLOCKED
    return None


def frame_at(video, n, out, runner=subprocess.run):
    """Frame n (0-based, exact: decoded and selected by index) of video as a PNG. True when out was written."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"select=eq(n\\,{int(n)})",
           "-fps_mode", "passthrough", "-frames:v", "1", str(out)]
    try:
        p = runner(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return p.returncode == 0 and out.exists()
