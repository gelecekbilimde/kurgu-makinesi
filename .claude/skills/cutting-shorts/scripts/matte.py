"""The teaser's speaker cut-out: the teaser frames at the short's crop, a matte per frame from an injectable
segmenter, encoded as ProRes 4444 with alpha (1080x1920), so the caption can sit behind the head on plain tracks.

`segment(png_path) -> mask png path` (grey, white = speaker; mediapipe in shorts_media.py, a fake in tests)."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import crop
from faces import MediaError, seek

TL = (1080, 1920)


def _run(runner, cmd, what):
    try:
        p = runner(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise MediaError("FFmpeg bulunamadı") from None
    if p.returncode != 0:
        last = ((p.stderr or "").strip().splitlines() or [""])[-1]
        raise MediaError(f"{what}: {last}")


def cutout(video, src_range, transform, out, segment, runner=subprocess.run, *, src_size, fps):
    """Write out (.mov): source frames [src_in, src_out) of video framed by `transform` (the item's crop on the
    1080x1920 timeline), with the speaker's matte as alpha. Frames and masks live in a temp dir next to out."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    src_in, src_out = src_range
    x, y, w, h = (round(v) for v in crop.window(transform, *src_size, *TL))
    work = Path(tempfile.mkdtemp(prefix=out.stem + "-", dir=out.parent))
    try:
        frames, masks = work / "frames", work / "masks"
        frames.mkdir()
        masks.mkdir()
        _run(runner, ["ffmpeg", "-y", "-loglevel", "error", "-ss", seek(src_in, fps), "-i", str(video),
                      "-frames:v", str(src_out - src_in),
                      "-vf", f"crop={w}:{h}:{x}:{y},scale={TL[0]}:{TL[1]}:flags=lanczos",
                      "-pix_fmt", "rgb24", "-start_number", "0", str(frames / "f%05d.png")],
             f"{video} teaser kareleri alınamadı")
        pngs = sorted(frames.glob("f*.png"))
        if len(pngs) != src_out - src_in:
            raise MediaError(f"{video}: {src_out - src_in} kare beklendi, {len(pngs)} alındı")
        for i, png in enumerate(pngs):
            os.replace(segment(str(png)), masks / f"m{i:05d}.png")
        _run(runner, ["ffmpeg", "-y", "-loglevel", "error",
                      "-framerate", str(fps), "-i", str(frames / "f%05d.png"),
                      "-framerate", str(fps), "-i", str(masks / "m%05d.png"),
                      "-filter_complex", "[1:v]format=gray[a];[0:v][a]alphamerge,format=yuva444p10le",
                      "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(out)],
             f"{out.name} yazılamadı")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out
