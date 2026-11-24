"""Unified marker-to-edits feedback readback for Kdenlive, Shotcut, Premiere Pro, and CapCut.

Mirrors Kurgu Makinesi's Resolve `markers_to_edits.py` workflow:
reads Yellow (editor-reserved) range markers from an edited project file and
writes `edits/<stem>-edits.json` so the rough-cut pipeline can apply manual
removals and rebuild timelines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capcut import read_capcut_markers
from .kdenlive import read_kdenlive_markers
from .premiere import read_premiere_markers
from .shotcut import read_shotcut_markers
from .timeline import Marker, frames_to_sec


def detect_editor(project_path: str | Path) -> str:
    """Detect the NLE format from a project path."""
    p = Path(project_path)
    if p.is_dir() or p.name in {"draft_content.json", "markers.json"}:
        return "capcut"
    ext = p.suffix.lower()
    if ext == ".kdenlive":
        return "kdenlive"
    if ext == ".mlt":
        return "shotcut"
    if ext == ".xml":
        return "premiere"
    raise ValueError(f"Cannot infer editor format from '{project_path}'. Pass --editor explicitly.")


def read_markers(
    project_path: str | Path,
    editor: Optional[str] = None,
    color_filter: Optional[str] = "Yellow",
    fps: float = 25.0,
) -> List[Marker]:
    """Read markers from any supported editor project file."""
    fmt = (editor or detect_editor(project_path)).lower()
    if fmt == "kdenlive":
        return read_kdenlive_markers(project_path, color_filter=color_filter, default_fps=fps)
    if fmt == "shotcut":
        return read_shotcut_markers(project_path, color_filter=color_filter, default_fps=fps)
    if fmt == "premiere":
        return read_premiere_markers(project_path, color_filter=color_filter)
    if fmt == "capcut":
        return read_capcut_markers(project_path, color_filter=color_filter, default_fps=fps)
    raise ValueError(f"Unsupported editor: {fmt}")


def markers_to_edits_payload(
    markers: List[Marker],
    source_project: str | Path,
    fps: float = 25.0,
) -> Dict[str, Any]:
    """Convert read-back Markers into Kurgu Makinesi's edits JSON schema."""
    removals: List[Dict[str, Any]] = []
    for m in markers:
        removals.append(
            {
                "action": "remove",
                "start_f": m.frame,
                "end_f": m.end_frame,
                "duration_f": m.duration_frames,
                "start_sec": round(frames_to_sec(m.frame, fps), 3),
                "end_sec": round(frames_to_sec(m.end_frame, fps), 3),
                "color": m.color,
                "reason": m.name,
                "note": m.note,
            }
        )
    return {
        "source_project": str(source_project),
        "fps": fps,
        "edits": removals,
    }


def write_edits_json(
    project_path: str | Path,
    output_path: str | Path,
    editor: Optional[str] = None,
    color_filter: Optional[str] = "Yellow",
    fps: float = 25.0,
) -> Path:
    """Read editor markers and write a Kurgu Makinesi edits JSON file."""
    markers = read_markers(project_path, editor=editor, color_filter=color_filter, fps=fps)
    payload = markers_to_edits_payload(markers, source_project=project_path, fps=fps)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
