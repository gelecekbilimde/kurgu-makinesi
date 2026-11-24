"""Editor-neutral multi-track timeline model for Kurgu Makinesi.

Supports:
- Sequential A-roll clips on V1 (with optional embedded audio on A1)
- Synced external recorder WAV clips on A2 (with frame-accurate offset_f)
- Multi-track B-roll on V2 ([STOK], [KAYNAK]) and overlays on V3 ([GRAFIK], [YAZI])
- Color-coded point & range markers matching DaVinci Resolve's Kurgu Makinesi palette
- Vertical Shorts (9:16 1080x1920) with per-clip face-crop CropRect and SRT captions
- Per-chapter timeline splitting with freeze/unfreeze tracking
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .script_parser import ChapterInfo, parse_script

# Kurgu Makinesi marker color palette (aligned with DaVinci Resolve skills)
# Each entry maps canonical color name -> (hex_rgb, kdenlive_category_id, premiere_ppro_color)
# Premiere pproColor values are 32-bit ARGB integers used by Premiere Pro FCP7 XML.
MARKER_COLORS: Dict[str, Tuple[str, int, int]] = {
    "Green": ("#00aa00", 0, 4281740498),      # Chapters
    "Sky": ("#38bdf8", 1, 4294741314),        # Subsections
    "Blue": ("#2563eb", 2, 4281740498),       # Source clip boundaries
    "Red": ("#dc2626", 3, 4281049552),        # Cue retakes removed
    "Rose": ("#f43f5e", 4, 4281049552),       # Repeated phrases removed
    "Purple": ("#9333ea", 5, 4289825711),     # Other removals
    "Cyan": ("#06b6d4", 6, 4294741314),       # Second-transcript-only cuts
    "Fuchsia": ("#d946ef", 7, 4289825711),    # Suggested cuts (range)
    "Pink": ("#ec4899", 8, 4289825711),       # Long retakes kept (range)
    "Yellow": ("#eab308", 9, 4282339765),     # Editor-reserved removal ranges
    "Lavender": ("#a78bfa", 10, 4289825711),  # [ARŞİV] placeholders
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def hex_to_canonical_color(hex_color: str) -> str:
    """Map an editor hex color back to the nearest canonical Kurgu Makinesi color name."""
    cleaned = hex_color.strip().lower()
    for name, (hx, _, _) in MARKER_COLORS.items():
        if hx.lower() == cleaned:
            return name
    # Common editor yellow aliases (Shotcut/Kdenlive defaults)
    if cleaned in {"#ffff00", "#ffd700", "#facc15", "#e5a50a", "#c8a000", "#f1c40f"}:
        return "Yellow"
    if cleaned in {"#00ff00", "#008000", "#22c55e"}:
        return "Green"
    if cleaned in {"#ff0000", "#ef4444"}:
        return "Red"
    return "Yellow" if "ff" in cleaned and "00" in cleaned else "Green"


@dataclass
class MediaInfo:
    duration: float = 0.0
    fps: float = 25.0
    width: int = 1920
    height: int = 1080
    has_audio: bool = True
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    is_image: bool = False


def probe(file_path: str | Path, default_fps: float = 25.0) -> MediaInfo:
    """Probe media metadata with ffprobe; fall back cleanly if unavailable."""
    p = Path(file_path)
    if p.suffix.lower() in IMAGE_EXTENSIONS:
        return MediaInfo(
            duration=5.0,
            fps=default_fps,
            width=1920,
            height=1080,
            has_audio=False,
            is_image=True,
        )

    if not p.exists():
        return MediaInfo(duration=0.0, fps=default_fps)

    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(p),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        if res.returncode != 0:
            return MediaInfo(duration=0.0, fps=default_fps)
        data = json.loads(res.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return MediaInfo(duration=0.0, fps=default_fps)

    info = MediaInfo(fps=default_fps, has_audio=False)
    fmt = data.get("format", {})
    if "duration" in fmt:
        try:
            info.duration = float(fmt["duration"])
        except (TypeError, ValueError):
            pass

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            info.width = int(stream.get("width", info.width) or info.width)
            info.height = int(stream.get("height", info.height) or info.height)
            r_fps = stream.get("r_frame_rate") or stream.get("avg_frame_rate")
            if r_fps and "/" in r_fps:
                num, den = r_fps.split("/", 1)
                try:
                    n, d = float(num), float(den)
                    if d > 0 and n > 0:
                        info.fps = round(n / d, 3)
                except ValueError:
                    pass
        elif codec_type == "audio":
            info.has_audio = True
            try:
                info.audio_sample_rate = int(stream.get("sample_rate", 48000))
            except (TypeError, ValueError):
                pass
            try:
                info.audio_channels = int(stream.get("channels", 2))
            except (TypeError, ValueError):
                pass

    return info


@dataclass
class CropRect:
    """Spatial transform / face-crop rectangle (used for vertical 9:16 shorts)."""

    x: float = 0.0        # Left offset in output pixels (or negative when zoomed)
    y: float = 0.0        # Top offset in output pixels
    scale: float = 1.0    # Uniform scale factor (e.g., 1.7778 to fill 1080x1920 from 16:9)
    center_x: float = 0.5 # Normalized horizontal face center (0.0=left, 0.5=center, 1.0=right)
    center_y: float = 0.5 # Normalized vertical center


@dataclass
class Clip:
    """An A-roll clip placed sequentially on V1."""

    file: str
    in_sec: float
    out_sec: Optional[float] = None
    chapter: Optional[str | int] = None
    subsection: Optional[str] = None
    external_audio: Optional[str] = None
    audio_offset_f: int = 0  # Frame offset between camera clip and recorder WAV
    mute_camera_audio: bool = False
    crop: Optional[CropRect] = None
    label: str = ""


@dataclass
class AudioClip:
    """An explicit external audio clip placed at a timeline position on A2."""

    file: str
    timeline_in_sec: float
    in_sec: float
    out_sec: float
    gain_db: float = 0.0
    label: str = ""


@dataclass
class OverlayClip:
    """A B-roll (track=2) or Graphic/Text overlay (track=3) placed at a timeline position."""

    file: str
    timeline_in_sec: float
    in_sec: float = 0.0
    out_sec: Optional[float] = None
    duration_sec: Optional[float] = None
    track: int = 2  # 2 = B-roll (V2), 3 = Graphics/Overlay (V3)
    kind: str = "STOK"  # STOK, GRAFIK, YAZI, KAYNAK, ARŞİV
    opacity: float = 1.0
    mute_audio: bool = True
    crop: Optional[CropRect] = None
    label: str = ""


@dataclass
class CaptionItem:
    """A timed caption/subtitle entry (for vertical shorts or burned/sidecar subtitles)."""

    start_sec: float
    end_sec: float
    text: str


@dataclass
class Marker:
    """A point or range marker on the timeline."""

    frame: int
    name: str
    color: str = "Green"
    note: str = ""
    duration_frames: int = 0  # 0 = point marker; >0 = range marker [frame, frame+duration_frames)

    @property
    def end_frame(self) -> int:
        return self.frame + max(0, self.duration_frames)


@dataclass
class PlacedClip:
    """A resolved A-roll clip positioned in integer frames."""

    clip: Clip
    index: int
    in_frame: int
    out_frame: int          # Inclusive last frame for MLT/XML compatibility
    duration_frames: int
    timeline_start: int
    timeline_end: int       # Exclusive end frame on timeline
    media: MediaInfo
    chapter_title: Optional[str] = None


@dataclass
class PlacedAudioClip:
    """A resolved external WAV audio clip positioned in integer frames on A2."""

    file: str
    in_frame: int
    out_frame: int
    duration_frames: int
    timeline_start: int
    timeline_end: int
    gain_db: float = 0.0
    label: str = ""
    linked_v1_index: Optional[int] = None


@dataclass
class PlacedOverlayClip:
    """A resolved B-roll (V2) or Graphic overlay (V3) positioned in integer frames."""

    overlay: OverlayClip
    in_frame: int
    out_frame: int
    duration_frames: int
    timeline_start: int
    timeline_end: int
    media: MediaInfo


def sec_to_frames(sec: float, fps: float) -> int:
    return int(round(sec * fps))


def frames_to_sec(frames: int, fps: float) -> float:
    return frames / fps if fps > 0 else 0.0


def format_tc_srt(sec: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    total_ms = max(0, int(round(sec * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_tc_mlt(sec: float) -> str:
    """Format seconds as Shotcut/MLT clock HH:MM:SS.mmm."""
    total_ms = max(0, int(round(sec * 1000)))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def format_tc_youtube(sec: float) -> str:
    """Format seconds as MM:SS or H:MM:SS for YouTube chapters."""
    total_s = max(0, int(round(sec)))
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def write_srt(captions: Sequence[CaptionItem], output_path: str | Path) -> Path:
    """Write a standard UTF-8 SubRip (.srt) file."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    blocks: List[str] = []
    for idx, cap in enumerate(captions, start=1):
        blocks.append(
            f"{idx}\n{format_tc_srt(cap.start_sec)} --> {format_tc_srt(cap.end_sec)}\n{cap.text.strip()}\n"
        )
    out.write_text("\n".join(blocks), encoding="utf-8")
    return out


@dataclass
class Timeline:
    """Complete editor-neutral multi-track timeline."""

    name: str = "kurgu"
    fps: float = 25.0
    width: int = 1920
    height: int = 1080
    clips: List[Clip] = field(default_factory=list)
    audio_clips: List[AudioClip] = field(default_factory=list)
    overlays: List[OverlayClip] = field(default_factory=list)
    markers: List[Marker] = field(default_factory=list)
    captions: List[CaptionItem] = field(default_factory=list)
    chapters: List[ChapterInfo] = field(default_factory=list)
    frozen_chapters: List[int] = field(default_factory=list)
    is_vertical: bool = False

    def resolve_chapter_title(self, chapter: Optional[str | int]) -> Optional[str]:
        if chapter is None:
            return None
        if isinstance(chapter, int):
            for ch in self.chapters:
                if ch.index == chapter:
                    return f"ch{ch.index} {ch.title}"
            return f"Chapter {chapter}"
        return str(chapter)

    def layout(
        self,
    ) -> Tuple[List[PlacedClip], List[PlacedAudioClip], List[PlacedOverlayClip], List[Marker], int]:
        """Lay out V1 A-roll, A2 external WAVs, V2 B-roll, V3 overlays, and markers."""
        placed_v1: List[PlacedClip] = []
        placed_a2: List[PlacedAudioClip] = []
        placed_ov: List[PlacedOverlayClip] = []
        all_markers: List[Marker] = []
        media_cache: Dict[str, MediaInfo] = {}

        def get_media(path: str) -> MediaInfo:
            if path not in media_cache:
                media_cache[path] = probe(path, default_fps=self.fps)
            return media_cache[path]

        cursor = 0
        last_chapter: Optional[str] = None
        last_file: Optional[str] = None

        for idx, clip in enumerate(self.clips):
            media = get_media(clip.file)
            in_f = max(0, sec_to_frames(clip.in_sec, self.fps))
            if clip.out_sec is not None:
                out_excl = sec_to_frames(clip.out_sec, self.fps)
            elif media.duration > 0:
                out_excl = sec_to_frames(media.duration, self.fps)
            else:
                out_excl = in_f + sec_to_frames(5.0, self.fps)

            dur = max(1, out_excl - in_f)
            out_incl = in_f + dur - 1
            ch_title = self.resolve_chapter_title(clip.chapter)

            if ch_title and ch_title != last_chapter:
                all_markers.append(
                    Marker(frame=cursor, name=ch_title, color="Green", note="Chapter start")
                )
                last_chapter = ch_title

            if clip.subsection:
                all_markers.append(
                    Marker(frame=cursor, name=clip.subsection, color="Sky", note="Subsection")
                )

            if last_file is not None and clip.file != last_file:
                all_markers.append(
                    Marker(
                        frame=cursor,
                        name=Path(clip.file).name,
                        color="Blue",
                        note="Source clip change",
                    )
                )
            last_file = clip.file

            placed = PlacedClip(
                clip=clip,
                index=idx,
                in_frame=in_f,
                out_frame=out_incl,
                duration_frames=dur,
                timeline_start=cursor,
                timeline_end=cursor + dur,
                media=media,
                chapter_title=ch_title,
            )
            placed_v1.append(placed)

            # Auto-derive synced external recorder WAV placement if specified on the clip
            if clip.external_audio:
                wav_in = max(0, in_f + clip.audio_offset_f)
                wav_out = wav_in + dur - 1
                placed_a2.append(
                    PlacedAudioClip(
                        file=clip.external_audio,
                        in_frame=wav_in,
                        out_frame=wav_out,
                        duration_frames=dur,
                        timeline_start=cursor,
                        timeline_end=cursor + dur,
                        label=f"WAV:{Path(clip.external_audio).name}",
                        linked_v1_index=idx,
                    )
                )

            cursor += dur

        # Explicit standalone external audio clips
        for ac in self.audio_clips:
            t_start = max(0, sec_to_frames(ac.timeline_in_sec, self.fps))
            in_f = max(0, sec_to_frames(ac.in_sec, self.fps))
            out_excl = sec_to_frames(ac.out_sec, self.fps)
            dur = max(1, out_excl - in_f)
            placed_a2.append(
                PlacedAudioClip(
                    file=ac.file,
                    in_frame=in_f,
                    out_frame=in_f + dur - 1,
                    duration_frames=dur,
                    timeline_start=t_start,
                    timeline_end=t_start + dur,
                    gain_db=ac.gain_db,
                    label=ac.label or Path(ac.file).name,
                )
            )
            cursor = max(cursor, t_start + dur)

        # B-roll (V2) and Graphics/Overlays (V3)
        for ov in self.overlays:
            media = get_media(ov.file)
            t_start = max(0, sec_to_frames(ov.timeline_in_sec, self.fps))
            in_f = max(0, sec_to_frames(ov.in_sec, self.fps))
            if ov.duration_sec is not None:
                dur = max(1, sec_to_frames(ov.duration_sec, self.fps))
            elif ov.out_sec is not None:
                dur = max(1, sec_to_frames(ov.out_sec, self.fps) - in_f)
            elif media.duration > 0:
                dur = max(1, sec_to_frames(media.duration, self.fps) - in_f)
            else:
                dur = sec_to_frames(4.0, self.fps)

            placed_ov.append(
                PlacedOverlayClip(
                    overlay=ov,
                    in_frame=in_f,
                    out_frame=in_f + dur - 1,
                    duration_frames=dur,
                    timeline_start=t_start,
                    timeline_end=t_start + dur,
                    media=media,
                )
            )
            cursor = max(cursor, t_start + dur)

        # Merge explicit user/pipeline markers (preserve order, sort by frame)
        all_markers.extend(self.markers)
        all_markers.sort(key=lambda m: (m.frame, m.name))
        placed_a2.sort(key=lambda a: a.timeline_start)
        placed_ov.sort(key=lambda o: (o.overlay.track, o.timeline_start))

        return placed_v1, placed_a2, placed_ov, all_markers, max(cursor, 1)

    def split_by_chapter(self) -> List[Tuple[int, str, "Timeline"]]:
        """Split this timeline into per-chapter timelines, shifting overlays/markers/captions."""
        grouped: List[Tuple[int, str, List[Clip]]] = []
        by_key: Dict[str, int] = {}

        for clip in self.clips:
            ch_num = clip.chapter if isinstance(clip.chapter, int) else (len(grouped) + 1)
            ch_title = self.resolve_chapter_title(clip.chapter) or "unassigned"
            if ch_title not in by_key:
                by_key[ch_title] = len(grouped)
                grouped.append((ch_num, ch_title, []))
            grouped[by_key[ch_title]][2].append(clip)

        # Compute global frame boundaries of each chapter to slice overlays/markers/captions
        placed_v1, _, _, _, _ = self.layout()
        ch_spans: Dict[str, Tuple[int, int]] = {}
        for pc in placed_v1:
            key = pc.chapter_title or "unassigned"
            if key not in ch_spans:
                ch_spans[key] = (pc.timeline_start, pc.timeline_end)
            else:
                s, e = ch_spans[key]
                ch_spans[key] = (min(s, pc.timeline_start), max(e, pc.timeline_end))

        results: List[Tuple[int, str, Timeline]] = []
        for idx, (ch_num, ch_title, ch_clips) in enumerate(grouped, start=1):
            span_start, span_end = ch_spans.get(ch_title, (0, 0))
            span_start_sec = frames_to_sec(span_start, self.fps)
            span_end_sec = frames_to_sec(span_end, self.fps)

            ch_overlays = [
                OverlayClip(
                    file=ov.file,
                    timeline_in_sec=max(0.0, ov.timeline_in_sec - span_start_sec),
                    in_sec=ov.in_sec,
                    out_sec=ov.out_sec,
                    duration_sec=ov.duration_sec,
                    track=ov.track,
                    kind=ov.kind,
                    opacity=ov.opacity,
                    mute_audio=ov.mute_audio,
                    crop=ov.crop,
                    label=ov.label,
                )
                for ov in self.overlays
                if span_start_sec <= ov.timeline_in_sec < span_end_sec
            ]
            ch_markers = [
                Marker(
                    frame=m.frame - span_start,
                    name=m.name,
                    color=m.color,
                    note=m.note,
                    duration_frames=m.duration_frames,
                )
                for m in self.markers
                if span_start <= m.frame < span_end
            ]
            ch_captions = [
                CaptionItem(
                    start_sec=max(0.0, c.start_sec - span_start_sec),
                    end_sec=max(0.0, c.end_sec - span_start_sec),
                    text=c.text,
                )
                for c in self.captions
                if span_start_sec <= c.start_sec < span_end_sec
            ]

            safe_slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in ch_title).strip("_")
            sub_tl = Timeline(
                name=f"{self.name}_ch{idx}_{safe_slug[:32]}",
                fps=self.fps,
                width=self.width,
                height=self.height,
                clips=ch_clips,
                overlays=ch_overlays,
                markers=ch_markers,
                captions=ch_captions,
                chapters=self.chapters,
                is_vertical=self.is_vertical,
            )
            results.append((ch_num if isinstance(ch_num, int) else idx, ch_title, sub_tl))

        return results


def _parse_crop(raw: Optional[Dict[str, Any]]) -> Optional[CropRect]:
    if not raw:
        return None
    return CropRect(
        x=float(raw.get("x", 0.0)),
        y=float(raw.get("y", 0.0)),
        scale=float(raw.get("scale", 1.0)),
        center_x=float(raw.get("center_x", 0.5)),
        center_y=float(raw.get("center_y", 0.5)),
    )


def load_cutplan(
    cutplan_path: str | Path,
    script_path: Optional[str | Path] = None,
    name_override: Optional[str] = None,
    vertical_short: bool = False,
) -> Timeline:
    """Load a Kurgu Makinesi cut plan JSON (simple or multi-track) into a Timeline."""
    p = Path(cutplan_path)
    data = json.loads(p.read_text(encoding="utf-8"))

    chapters: List[ChapterInfo] = parse_script(script_path) if script_path else []
    fps = float(data.get("fps", 25.0))
    is_vertical = bool(vertical_short or data.get("vertical", False))
    default_w, default_h = (1080, 1920) if is_vertical else (1920, 1080)
    width = int(data.get("width", default_w))
    height = int(data.get("height", default_h))
    if is_vertical and width > height:
        width, height = default_w, default_h
    name = name_override or str(data.get("name", p.stem))

    clips: List[Clip] = []
    for item in data.get("clips", []):
        # Support both seconds ("in"/"out") and frame-native ("in_f"/"out_f")
        in_sec = (
            float(item["in"])
            if "in" in item
            else frames_to_sec(int(item.get("in_f", 0)), fps)
        )
        out_sec: Optional[float] = None
        if "out" in item and item["out"] is not None:
            out_sec = float(item["out"])
        elif "out_f" in item and item["out_f"] is not None:
            out_sec = frames_to_sec(int(item["out_f"]), fps)

        clips.append(
            Clip(
                file=str(item["file"]),
                in_sec=in_sec,
                out_sec=out_sec,
                chapter=item.get("chapter"),
                subsection=item.get("subsection"),
                external_audio=item.get("external_audio") or item.get("wav"),
                audio_offset_f=int(item.get("audio_offset_f", item.get("offset_f", 0))),
                mute_camera_audio=bool(
                    item.get("mute_camera_audio", bool(item.get("external_audio") or item.get("wav")))
                ),
                crop=_parse_crop(item.get("crop")),
                label=str(item.get("label", "")),
            )
        )

    audio_clips: List[AudioClip] = []
    for item in data.get("audio_clips", []):
        audio_clips.append(
            AudioClip(
                file=str(item["file"]),
                timeline_in_sec=float(item.get("timeline_in", 0.0)),
                in_sec=float(item.get("in", 0.0)),
                out_sec=float(item["out"]),
                gain_db=float(item.get("gain_db", 0.0)),
                label=str(item.get("label", "")),
            )
        )

    overlays: List[OverlayClip] = []
    for key, default_track, default_kind in (
        ("broll", 2, "STOK"),
        ("broll_clips", 2, "STOK"),
        ("overlays", 3, "GRAFIK"),
        ("overlay_clips", 3, "GRAFIK"),
    ):
        for item in data.get(key, []):
            overlays.append(
                OverlayClip(
                    file=str(item["file"]),
                    timeline_in_sec=float(item.get("timeline_in", item.get("at", 0.0))),
                    in_sec=float(item.get("in", 0.0)),
                    out_sec=float(item["out"]) if item.get("out") is not None else None,
                    duration_sec=(
                        float(item["duration"]) if item.get("duration") is not None else None
                    ),
                    track=int(item.get("track", default_track)),
                    kind=str(item.get("kind", default_kind)),
                    opacity=float(item.get("opacity", 1.0)),
                    mute_audio=bool(item.get("mute_audio", True)),
                    crop=_parse_crop(item.get("crop")),
                    label=str(item.get("label", "")),
                )
            )

    markers: List[Marker] = []
    for item in data.get("markers", []):
        frame = (
            int(item["frame"])
            if "frame" in item
            else sec_to_frames(float(item.get("time", 0.0)), fps)
        )
        dur_f = (
            int(item["duration_frames"])
            if "duration_frames" in item
            else sec_to_frames(float(item.get("duration", 0.0)), fps)
        )
        markers.append(
            Marker(
                frame=frame,
                name=str(item.get("name", "")),
                color=str(item.get("color", "Green")),
                note=str(item.get("note", "")),
                duration_frames=dur_f,
            )
        )

    captions: List[CaptionItem] = []
    for item in data.get("captions", []):
        captions.append(
            CaptionItem(
                start_sec=float(item["start"]),
                end_sec=float(item["end"]),
                text=str(item["text"]),
            )
        )

    return Timeline(
        name=name,
        fps=fps,
        width=width,
        height=height,
        clips=clips,
        audio_clips=audio_clips,
        overlays=overlays,
        markers=markers,
        captions=captions,
        chapters=chapters,
        frozen_chapters=[int(c) for c in data.get("frozen_chapters", [])],
        is_vertical=is_vertical,
    )
