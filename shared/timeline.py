"""Editor-neutral rough-cut timeline: what every exporter (Kdenlive, Shotcut, Premiere, CapCut) consumes.

A cut plan is JSON:
{
  "name": "COP31 ch1",            # optional
  "fps": 25, "width": 1920, "height": 1080,   # optional: default to the first clip's values (ffprobe)
  "clips": [
    {"file": "cam1.mp4", "in": 1.2, "out": 9.8, "chapter": 1},     # seconds; chapter = 1-based index
    {"file": "cam1.mp4", "in": 12.0, "out": 20.5, "chapter": "Intro"}  # ... or a title
  ]
}
Clips are laid end to end on one video track (+ its audio). Each time `chapter` changes, a marker is placed.
"""
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_FPS = Fraction(25, 1)


class PlanError(ValueError):
    """The cut plan is unusable; the message is fit for the user."""


@dataclass
class Clip:
    file: str
    src_in: float
    src_out: float
    name: str = ""
    chapter: Optional[str] = None
    has_audio: bool = True          # False only when ffprobe says there is no audio stream
    src_duration: Optional[float] = None  # whole source file, seconds (ffprobe), None if unknown


@dataclass
class Marker:
    frame: int
    text: str


@dataclass
class Placed:
    clip: Clip
    start: int      # record frame, inclusive
    end: int        # record frame, exclusive
    src_in: int     # source frame, inclusive
    src_out: int    # source frame, exclusive


@dataclass
class Timeline:
    name: str
    fps: Fraction
    width: int
    height: int
    clips: List[Clip] = field(default_factory=list)

    # ---- frame math -------------------------------------------------------
    def frames(self, seconds: float) -> int:
        return int(round(seconds * float(self.fps)))

    @property
    def fps_num(self) -> int:
        return self.fps.numerator

    @property
    def fps_den(self) -> int:
        return self.fps.denominator

    def layout(self) -> List[Placed]:
        out, pos = [], 0
        for c in self.clips:
            a, b = self.frames(c.src_in), self.frames(c.src_out)
            n = max(1, b - a)
            out.append(Placed(c, pos, pos + n, a, a + n))
            pos += n
        return out

    @property
    def total_frames(self) -> int:
        lay = self.layout()
        return lay[-1].end if lay else 0

    def markers(self) -> List[Marker]:
        """One marker at the first clip of each run of equal chapter titles."""
        out, last = [], None
        for p in self.layout():
            ch = p.clip.chapter
            if ch and ch != last:
                out.append(Marker(p.start, ch))
            last = ch
        return out

    def clock(self, frames: int) -> str:
        """MLT clock time HH:MM:SS.mmm for a frame count."""
        ms = int(round(frames * 1000 * self.fps_den / self.fps_num))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def unique_files(self) -> List[str]:
        seen: Dict[str, None] = {}
        for c in self.clips:
            seen.setdefault(c.file, None)
        return list(seen)


# ---- probing --------------------------------------------------------------

def probe(path: str) -> Optional[dict]:
    """{duration, fps (Fraction|None), width, height, has_audio} from ffprobe; None when it can't be read."""
    if not shutil.which("ffprobe") or not Path(path).exists():
        return None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                           capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    info = {"duration": None, "fps": None, "width": None, "height": None,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}
    try:
        info["duration"] = float((data.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        pass
    if v:
        info["width"], info["height"] = v.get("width"), v.get("height")
        try:
            info["fps"] = Fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0").limit_denominator(1001)
            if info["fps"] <= 0:
                info["fps"] = None
        except (ValueError, ZeroDivisionError):
            pass
    return info


# ---- loading --------------------------------------------------------------

def _fps(value) -> Fraction:
    try:
        f = Fraction(str(value)).limit_denominator(1001)
    except (ValueError, ZeroDivisionError):
        raise PlanError(f"geçersiz fps / invalid fps: {value!r}")
    if f <= 0:
        raise PlanError(f"geçersiz fps / invalid fps: {value!r}")
    return f


def load_cutplan(path: str, chapters: Optional[List[str]] = None) -> Tuple[Timeline, List[str]]:
    """Cut plan JSON -> (Timeline, warnings). chapters: titles from the script, for numeric `chapter` values."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PlanError(f"cut plan not found: {path}")
    except ValueError as err:
        raise PlanError(f"{path}: not valid JSON ({err})")
    if not isinstance(raw, dict) or not isinstance(raw.get("clips"), list) or not raw["clips"]:
        raise PlanError(f"{path}: needs a non-empty 'clips' list")

    warnings: List[str] = []
    clips: List[Clip] = []
    first_probe = None
    for i, c in enumerate(raw["clips"], 1):
        if not isinstance(c, dict) or not c.get("file"):
            raise PlanError(f"clip {i}: 'file' is required")
        f = Path(c["file"])
        f = f if f.is_absolute() else (p.parent / f)
        file = str(f.resolve())
        info = probe(file)
        if info is None:
            warnings.append(f"clip {i}: {file} not readable by ffprobe (missing file or no ffprobe); "
                            "using the plan's numbers unchecked")
        elif first_probe is None:
            first_probe = info
        try:
            a = float(c.get("in", 0))
            b = c.get("out")
            b = float(b) if b is not None else (info or {}).get("duration")
        except (TypeError, ValueError):
            raise PlanError(f"clip {i}: 'in'/'out' must be numbers (seconds)")
        if b is None:
            raise PlanError(f"clip {i}: no 'out' and the file's duration is unknown")
        if a < 0 or b <= a:
            raise PlanError(f"clip {i}: need 0 <= in < out (got in={a}, out={b})")
        dur = (info or {}).get("duration")
        if dur is not None and b > dur + 0.05:
            raise PlanError(f"clip {i}: out={b}s is past the end of {f.name} ({dur:.2f}s)")
        ch = c.get("chapter")
        if isinstance(ch, int) and not isinstance(ch, bool):
            if chapters and 1 <= ch <= len(chapters):
                ch = chapters[ch - 1]
            else:
                warnings.append(f"clip {i}: chapter {ch} not in the script ({len(chapters or [])} chapters); "
                                f"using 'Chapter {ch}'")
                ch = f"Chapter {ch}"
        clips.append(Clip(file=file, src_in=a, src_out=b, name=c.get("name") or f.stem,
                          chapter=str(ch) if ch else None,
                          has_audio=(info or {}).get("has_audio", True), src_duration=dur))

    fps = _fps(raw["fps"]) if raw.get("fps") else ((first_probe or {}).get("fps") or DEFAULT_FPS)
    width = int(raw.get("width") or (first_probe or {}).get("width") or 1920)
    height = int(raw.get("height") or (first_probe or {}).get("height") or 1080)
    if width < 16 or height < 16:
        raise PlanError(f"invalid size {width}x{height}")
    return Timeline(str(raw.get("name") or p.stem), fps, width, height, clips), warnings
