"""CapCut writer: a draft folder with draft_content.json + draft_meta_info.json (+ chapters.txt).

EXPERIMENTAL. CapCut has no documented import format. This follows the community-reverse-engineered draft
layout (times in microseconds; one video track whose segments reference video materials). It could not be
verified against a real CapCut install here, and CapCut versions that encrypt drafts (CapCut >= 6 desktop
for new drafts) will not read it. Copy the folder into CapCut's drafts directory and check it opens.
Markers are not part of the draft layout used here; chapters are written to chapters.txt
(YouTube-style timestamps) instead.
"""
import json
import time
import uuid
from pathlib import Path
from typing import List

from .timeline import Timeline

_MATERIAL_LISTS = (
    "ai_translates", "audio_balances", "audio_effects", "audio_fades", "audio_track_indexes", "audios", "beats",
    "canvases", "chromas", "color_curves", "digital_humans", "drafts", "effects", "flowers", "green_screens",
    "handwrites", "hsl", "images", "log_color_wheels", "loudnesses", "manual_deformations", "material_animations",
    "material_colors", "multi_language_refs", "placeholders", "plugin_effects", "primary_color_wheels",
    "realtime_denoises", "shapes", "smart_crops", "smart_relights", "sound_channel_mappings", "speeds", "stickers",
    "tail_leaders", "text_templates", "texts", "time_marks", "transitions", "video_effects", "video_trackings",
    "videos", "vocal_beautifys", "vocal_separations")


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _us(tl: Timeline, frames: int) -> int:
    return int(round(frames * 1_000_000 * tl.fps_den / tl.fps_num))


def timestamp(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build(tl: Timeline) -> dict:
    materials = {k: [] for k in _MATERIAL_LISTS}
    mat_id = {}
    for f in tl.unique_files():
        c0 = next(c for c in tl.clips if c.file == f)
        mid = _uid()
        mat_id[f] = mid
        dur = c0.src_duration if c0.src_duration else max(c.src_out for c in tl.clips if c.file == f)
        materials["videos"].append({
            "id": mid, "type": "video", "path": f, "material_name": Path(f).name,
            "duration": int(round(dur * 1_000_000)), "width": tl.width, "height": tl.height,
            "has_audio": c0.has_audio, "category_name": "local", "check_flag": 63487})
    segments = []
    for p in tl.layout():
        speed_id = _uid()
        materials["speeds"].append({"id": speed_id, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        segments.append({
            "id": _uid(), "material_id": mat_id[p.clip.file], "speed": 1.0, "volume": 1.0, "visible": True,
            "target_timerange": {"start": _us(tl, p.start), "duration": _us(tl, p.end - p.start)},
            "source_timerange": {"start": _us(tl, p.src_in), "duration": _us(tl, p.src_out - p.src_in)},
            "extra_material_refs": [speed_id], "render_index": 0, "track_render_index": 0,
            "clip": {"alpha": 1.0, "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0},
                     "flip": {"horizontal": False, "vertical": False}}})
    return {
        "id": _uid(), "version": 360000, "new_version": "110.0.0", "name": tl.name,
        "fps": float(tl.fps), "duration": _us(tl, tl.total_frames),
        "canvas_config": {"width": tl.width, "height": tl.height, "ratio": "original"},
        "config": {"video_mute": False, "record_audio_last_index": 1, "extract_audio_last_index": 1,
                   "subtitle_sync": True, "lyrics_sync": True, "maintrack_adsorb": True},
        "materials": materials,
        "tracks": [{"id": _uid(), "type": "video", "attribute": 0, "flag": 0, "segments": segments}],
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [], "stickers": [],
                      "texts": [], "videos": []},
        "platform": {"app_id": 3704, "app_source": "lv", "app_version": "5.9.0", "os": "windows"},
        "keyframe_graph_list": [], "relationships": [], "extra_info": None, "free_render_index_mode_on": False,
    }


def meta(tl: Timeline, content: dict, folder: Path) -> dict:
    now = int(time.time() * 1_000_000)
    return {"draft_id": content["id"], "draft_name": tl.name, "draft_fold_path": str(folder),
            "draft_root_path": str(folder.parent), "tm_draft_create": now, "tm_draft_modified": now,
            "tm_duration": content["duration"], "draft_cover": "", "draft_removable_storage_device": "",
            "draft_materials": [{"type": 0, "value": []}, {"type": 1, "value": []}, {"type": 2, "value": []},
                                {"type": 3, "value": []}, {"type": 6, "value": []}, {"type": 7, "value": []},
                                {"type": 8, "value": []}]}


def chapters_text(tl: Timeline) -> str:
    fps = float(tl.fps)
    lines = [f"{timestamp(m.frame / fps)} {m.text}" for m in tl.markers()]
    return "\n".join(lines) + ("\n" if lines else "")


def write(tl: Timeline, out_dir: str) -> List[Path]:
    """Write <out_dir>/<name>/{draft_content.json, draft_meta_info.json, chapters.txt} -> paths"""
    name = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in tl.name).strip() or "project"
    folder = Path(out_dir) / name
    folder.mkdir(parents=True, exist_ok=True)
    content = build(tl)
    paths = [folder / "draft_content.json", folder / "draft_meta_info.json", folder / "chapters.txt"]
    paths[0].write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    paths[1].write_text(json.dumps(meta(tl, content, folder.resolve()), ensure_ascii=False, indent=2), encoding="utf-8")
    paths[2].write_text(chapters_text(tl), encoding="utf-8")
    return paths
