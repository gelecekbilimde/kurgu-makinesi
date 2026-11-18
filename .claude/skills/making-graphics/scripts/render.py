"""Render a staged HyperFrames project to a .mov (overlay), .mp4 (fullscreen) or .png (still), and grab posters.

A render goes to a temporary name next to the target and is moved into place only when HyperFrames succeeds, so a
failed render never leaves a partial or 0-byte file behind.
"""
import os
import shutil
from pathlib import Path

import hf

FORMATS = {"overlay": "mov", "fullscreen": "mp4", "still": "png-sequence"}
EXT = {"overlay": ".mov", "fullscreen": ".mp4", "still": ".png"}


def _resolution(resolution, fixed, vertical):
    if fixed or resolution != "4k":
        return []
    return ["--resolution", "portrait-4k" if vertical else "landscape-4k"]


def render(staged, output, resolution, fixed, vertical, fps, out_file, run=hf.run):
    staged, out_file = Path(staged), Path(out_file)
    tmp = out_file.with_name(f".{out_file.stem}.part" + ("" if output == "still" else out_file.suffix))
    cmd = hf.hf_cmd("render", staged, "--fps", str(fps), "--format", FORMATS[output],
                    "--variables-file", staged / "vars.json", "--strict-variables", "-o", tmp,
                    *_resolution(resolution, fixed, vertical))
    try:
        r = run(cmd, staged)
        if r.returncode != 0:
            raise hf.ToolError(f"HyperFrames çizimi başarısız: {hf.last_line(r.stderr) or hf.last_line(r.stdout)}")
        if output == "still":
            frames = sorted(tmp.glob("*.png"))
            if len(frames) != 1:
                raise hf.ToolError(f"durağan görsel için 1 kare bekleniyordu, {len(frames)} geldi")
            os.replace(frames[0], out_file)
        else:
            if not tmp.is_file() or tmp.stat().st_size == 0:
                raise hf.ToolError("HyperFrames çıktı dosyası üretmedi")
            os.replace(tmp, out_file)
    finally:
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp.exists():
            tmp.unlink()
    return out_file


def poster(file, frame, dest, run=hf.run):
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(file), "-vf", f"select=eq(n\\,{int(frame)})", "-vframes", "1",
           "-pix_fmt", "rgba", str(dest)]
    r = run(cmd, Path(dest).parent)
    if r.returncode != 0:
        raise hf.ToolError(f"poster karesi alınamadı: {hf.last_line(r.stderr)}")
    return Path(dest)
