"""CapCut Desktop draft folder writer and marker reader for Kurgu Makinesi.

IMPORTANT COMPATIBILITY NOTE:
- CapCut Desktop 5.x reads unencrypted draft_content.json / draft_meta_info.json.
- CapCut Desktop >= 6.0 encrypts newly saved drafts, so unencrypted JSON drafts
  are marked experimental for v6+. chapters.txt and <name>.srt work on all versions.

Features:
- Multi-track draft_content.json (microsecond timings):
  - Video Track 0: V1 A-roll
  - Video Track 1: V2 B-roll ([STOK], [KAYNAK])
  - Video Track 2: V3 Overlays / Graphics ([GRAFIK], [YAZI])
  - Audio Track 0: A1 External Synced WAV
  - Text Track 0: Native caption segments (for Vertical Shorts)
- Vertical Shorts (1080x1920) canvas_config + per-segment clip scale/transform
- YouTube-formatted chapters.txt + machine-readable markers.json + sidecar .srt
- Round-trip marker readback (read_capcut_markers)
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .timeline import (
    MARKER_COLORS,
    CropRect,
    Marker,
    Timeline,
    format_tc_youtube,
    frames_to_sec,
    sec_to_frames,
    write_srt,
)


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _frames_to_us(frames: int, fps: float) -> int:
    return int(round((frames / fps) * 1_000_000)) if fps > 0 else 0


def _sec_to_us(sec: float) -> int:
    return int(round(sec * 1_000_000))


def _clip_transform(crop: Optional[CropRect]) -> Dict[str, Any]:
    if crop is None:
        return {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        }
    return {
        "alpha": 1.0,
        "flip": {"horizontal": False, "vertical": False},
        "rotation": 0.0,
        "scale": {"x": round(crop.scale, 4), "y": round(crop.scale, 4)},
        "transform": {
            "x": round(-(crop.center_x - 0.5) * 2.0, 4),
            "y": round(-(crop.center_y - 0.5) * 2.0, 4),
        },
    }


def write_capcut(timeline: Timeline, output_dir: str | Path) -> Path:
    """Write a CapCut Desktop draft folder (<output_dir>/<name>/)."""
    draft_dir = Path(output_dir) / timeline.name
    draft_dir.mkdir(parents=True, exist_ok=True)

    placed_v1, placed_a2, placed_ov, markers, total_frames = timeline.layout()
    fps = timeline.fps
    total_us = _frames_to_us(total_frames, fps)
    now_us = int(time.time() * 1_000_000)

    materials_videos: List[Dict[str, Any]] = []
    materials_audios: List[Dict[str, Any]] = []
    materials_texts: List[Dict[str, Any]] = []
    materials_speeds: List[Dict[str, Any]] = []

    v1_segments: List[Dict[str, Any]] = []
    v2_segments: List[Dict[str, Any]] = []
    v3_segments: List[Dict[str, Any]] = []
    a1_segments: List[Dict[str, Any]] = []
    t1_segments: List[Dict[str, Any]] = []

    def add_speed() -> str:
        sid = _uid()
        materials_speeds.append({"curve_speed": None, "id": sid, "mode": 0, "speed": 1.0, "type": "speed"})
        return sid

    # V1 A-roll
    for pc in placed_v1:
        mat_id = _uid()
        spd_id = add_speed()
        resolved = str(Path(pc.clip.file).resolve()) if Path(pc.clip.file).exists() else pc.clip.file
        src_dur_us = _frames_to_us(pc.in_frame + pc.duration_frames, fps)
        materials_videos.append(
            {
                "id": mat_id,
                "material_name": Path(pc.clip.file).name,
                "path": resolved,
                "type": "photo" if pc.media.is_image else "video",
                "width": pc.media.width,
                "height": pc.media.height,
                "duration": src_dur_us,
                "has_audio": pc.media.has_audio and not pc.clip.mute_camera_audio,
            }
        )
        v1_segments.append(
            {
                "id": _uid(),
                "material_id": mat_id,
                "extra_material_refs": [spd_id],
                "enable_adjust": True,
                "volume": 0.0 if pc.clip.mute_camera_audio else 1.0,
                "clip": _clip_transform(pc.clip.crop),
                "source_timerange": {
                    "start": _frames_to_us(pc.in_frame, fps),
                    "duration": _frames_to_us(pc.duration_frames, fps),
                },
                "target_timerange": {
                    "start": _frames_to_us(pc.timeline_start, fps),
                    "duration": _frames_to_us(pc.duration_frames, fps),
                },
            }
        )

    # V2 B-roll & V3 Overlays
    for ov in placed_ov:
        mat_id = _uid()
        spd_id = add_speed()
        resolved = str(Path(ov.overlay.file).resolve()) if Path(ov.overlay.file).exists() else ov.overlay.file
        src_dur_us = _frames_to_us(ov.in_frame + ov.duration_frames, fps)
        materials_videos.append(
            {
                "id": mat_id,
                "material_name": Path(ov.overlay.file).name,
                "path": resolved,
                "type": "photo" if ov.media.is_image else "video",
                "width": ov.media.width,
                "height": ov.media.height,
                "duration": src_dur_us,
                "has_audio": not ov.overlay.mute_audio,
            }
        )
        seg = {
            "id": _uid(),
            "material_id": mat_id,
            "extra_material_refs": [spd_id],
            "enable_adjust": True,
            "volume": 0.0 if ov.overlay.mute_audio else 1.0,
            "clip": _clip_transform(ov.overlay.crop),
            "source_timerange": {
                "start": _frames_to_us(ov.in_frame, fps),
                "duration": _frames_to_us(ov.duration_frames, fps),
            },
            "target_timerange": {
                "start": _frames_to_us(ov.timeline_start, fps),
                "duration": _frames_to_us(ov.duration_frames, fps),
            },
        }
        if ov.overlay.track <= 2:
            v2_segments.append(seg)
        else:
            v3_segments.append(seg)

    # A1 External Synced WAV
    for ac in placed_a2:
        mat_id = _uid()
        spd_id = add_speed()
        resolved = str(Path(ac.file).resolve()) if Path(ac.file).exists() else ac.file
        materials_audios.append(
            {
                "id": mat_id,
                "name": Path(ac.file).name,
                "path": resolved,
                "type": "extract_music",
                "duration": _frames_to_us(ac.in_frame + ac.duration_frames, fps),
            }
        )
        a1_segments.append(
            {
                "id": _uid(),
                "material_id": mat_id,
                "extra_material_refs": [spd_id],
                "volume": 1.0,
                "source_timerange": {
                    "start": _frames_to_us(ac.in_frame, fps),
                    "duration": _frames_to_us(ac.duration_frames, fps),
                },
                "target_timerange": {
                    "start": _frames_to_us(ac.timeline_start, fps),
                    "duration": _frames_to_us(ac.duration_frames, fps),
                },
            }
        )

    # T1 Captions (native text track)
    for cap in timeline.captions:
        txt_id = _uid()
        text_content = json.dumps(
            {
                "text": cap.text,
                "styles": [
                    {
                        "fill": {"content": {"solid": {"color": [1.0, 1.0, 1.0]}}},
                        "size": 7.0,
                        "range": [0, len(cap.text)],
                    }
                ],
            },
            ensure_ascii=False,
        )
        materials_texts.append(
            {
                "id": txt_id,
                "type": "subtitle",
                "content": text_content,
                "alignment": 1,
            }
        )
        dur_us = max(1, _sec_to_us(cap.end_sec - cap.start_sec))
        t1_segments.append(
            {
                "id": _uid(),
                "material_id": txt_id,
                "clip": {
                    "alpha": 1.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": -0.65},
                },
                "target_timerange": {
                    "start": _sec_to_us(cap.start_sec),
                    "duration": dur_us,
                },
            }
        )

    tracks: List[Dict[str, Any]] = [
        {"id": _uid(), "type": "video", "attribute": 0, "segments": v1_segments},
    ]
    if v2_segments:
        tracks.append({"id": _uid(), "type": "video", "attribute": 0, "segments": v2_segments})
    if v3_segments:
        tracks.append({"id": _uid(), "type": "video", "attribute": 0, "segments": v3_segments})
    if a1_segments:
        tracks.append({"id": _uid(), "type": "audio", "attribute": 0, "segments": a1_segments})
    if t1_segments:
        tracks.append({"id": _uid(), "type": "text", "attribute": 0, "segments": t1_segments})

    draft_id = _uid()
    draft_content: Dict[str, Any] = {
        "id": draft_id,
        "name": timeline.name,
        "fps": fps,
        "duration": total_us,
        "canvas_config": {
            "width": timeline.width,
            "height": timeline.height,
            "ratio": "9:16" if timeline.is_vertical else "16:9",
        },
        "platform": {"app_version": "5.9.0", "os": "windows"},
        "materials": {
            "videos": materials_videos,
            "audios": materials_audios,
            "texts": materials_texts,
            "speeds": materials_speeds,
        },
        "tracks": tracks,
    }

    draft_meta: Dict[str, Any] = {
        "draft_id": draft_id,
        "draft_name": timeline.name,
        "draft_fold_path": str(draft_dir.resolve()),
        "draft_root_path": str(draft_dir.parent.resolve()),
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": total_us,
    }

    (draft_dir / "draft_content.json").write_text(
        json.dumps(draft_content, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (draft_dir / "draft_meta_info.json").write_text(
        json.dumps(draft_meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Write chapters.txt (YouTube timestamp format)
    chapter_lines: List[str] = []
    for m in markers:
        if m.color == "Green":
            chapter_lines.append(f"{format_tc_youtube(frames_to_sec(m.frame, fps))} {m.name}")
    (draft_dir / "chapters.txt").write_text("\n".join(chapter_lines) + ("\n" if chapter_lines else ""), encoding="utf-8")

    # Write machine-readable markers.json (for color-coded review & round-trip readback)
    markers_payload = {
        "fps": fps,
        "markers": [
            {
                "frame": m.frame,
                "duration_frames": m.duration_frames,
                "start_sec": round(frames_to_sec(m.frame, fps), 3),
                "end_sec": round(frames_to_sec(m.end_frame, fps), 3),
                "name": m.name,
                "color": m.color,
                "hex": MARKER_COLORS.get(m.color, MARKER_COLORS["Green"])[0],
                "note": m.note,
            }
            for m in markers
        ],
    }
    (draft_dir / "markers.json").write_text(
        json.dumps(markers_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if timeline.captions:
        write_srt(timeline.captions, draft_dir / f"{timeline.name}.srt")

    return draft_dir


def read_capcut_markers(
    capcut_path: str | Path,
    color_filter: Optional[str] = "Yellow",
    default_fps: float = 25.0,
) -> List[Marker]:
    """Read markers from a CapCut draft folder's markers.json (or direct markers.json path)."""
    p = Path(capcut_path)
    markers_file = p / "markers.json" if p.is_dir() else p
    if not markers_file.exists():
        return []

    data = json.loads(markers_file.read_text(encoding="utf-8"))
    fps = float(data.get("fps", default_fps))
    results: List[Marker] = []
    for item in data.get("markers", []):
        color = str(item.get("color", "Green"))
        if color_filter and color.lower() != color_filter.lower():
            continue
        frame = (
            int(item["frame"])
            if "frame" in item
            else sec_to_frames(float(item.get("start_sec", 0.0)), fps)
        )
        dur_f = (
            int(item["duration_frames"])
            if "duration_frames" in item
            else max(0, sec_to_frames(float(item.get("end_sec", 0.0)), fps) - frame)
        )
        results.append(
            Marker(
                frame=frame,
                duration_frames=dur_f,
                name=str(item.get("name", "Marker")),
                color=color,
                note=str(item.get("note", "")),
            )
        )
    return results
