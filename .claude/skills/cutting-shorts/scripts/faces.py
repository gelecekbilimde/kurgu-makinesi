"""The speaker's face per camera range: sampled frames (FFmpeg) + an injectable detector, median of detections.

`detect(png_path) -> {"cx","cy","h"} | None` in source pixels (mediapipe in shorts_media.py, a fake in tests);
`runner` is subprocess.run or a fake, so tests start no FFmpeg."""
import os
import statistics
import subprocess

SAMPLES = 9


class MediaError(Exception):
    """FFmpeg failed; the message is Turkish and fit to show the editor."""


def seek(frame, fps):
    """FFmpeg input -ss for source frame `frame`: its time floored to the microsecond, so the seek never lands
    after the frame's own timestamp."""
    us = frame * 1_000_000 // fps
    return f"{us // 1_000_000}.{us % 1_000_000:06d}"


def samples(src_in, src_out, n=SAMPLES):
    """n evenly spaced frames inside [src_in, src_out), each in the middle of its 1/n slice (fewer if short)."""
    length = src_out - src_in
    return sorted({src_in + (2 * i + 1) * length // (2 * n) for i in range(n)})


def frame_png(video, frame, fps, out, runner=subprocess.run):
    """Source frame `frame` of video as an 8-bit RGB PNG."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", seek(frame, fps), "-i", str(video), "-frames:v", "1",
           "-pix_fmt", "rgb24", str(out)]
    try:
        p = runner(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise MediaError("FFmpeg bulunamadı") from None
    if p.returncode != 0 or not os.path.exists(out):
        last = ((p.stderr or "").strip().splitlines() or [""])[-1]
        raise MediaError(f"{os.path.basename(str(video))} kare {frame} alınamadı: {last}")


def _median(found):
    if not found:
        return None
    return {k: statistics.median(f[k] for f in found) for k in ("cx", "cy", "h")}


def _detections(video, src_in, src_out, detect, runner, fps, workdir):
    """The faces found on the SAMPLES sampled frames of [src_in, src_out) (sample PNGs removed after detection)."""
    found = []
    for n in samples(src_in, src_out):
        png = os.path.join(workdir, f"face-{n}.png")
        frame_png(video, n, fps, png, runner)
        try:
            f = detect(png)
        finally:
            if os.path.exists(png):
                os.unlink(png)
        if f is not None:
            found.append(f)
    return found


def piece_faces(video, ranges, detect, runner=subprocess.run, *, fps, workdir):
    """Per [src_in, src_out) range of video: the per-key median of the faces found on SAMPLES sampled frames,
    or None when none was found. Sample PNGs go to workdir and are removed after detection."""
    return [_median(_detections(video, a, b, detect, runner, fps, workdir)) for a, b in ranges]


def pooled_face(video, ranges, detect, runner=subprocess.run, *, fps, workdir):
    """One face for all [src_in, src_out) ranges of video: the per-key median of every detection on the SAMPLES
    sampled frames of each range, or None when none was found."""
    found = []
    for a, b in ranges:
        found += _detections(video, a, b, detect, runner, fps, workdir)
    return _median(found)
