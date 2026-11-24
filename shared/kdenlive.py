"""Kdenlive (.kdenlive MLT XML) writer and marker reader for Kurgu Makinesi.

Features:
- Multi-track timeline: A2 (External WAV), A1 (Camera Audio), V1 (A-roll),
  V2 (B-roll), V3 (Overlays / Graphics)
- Proper A/V clip grouping via kdenlive:docproperties.groups JSON so V1 + A1
  (and synced A2) move together when dragged in Kdenlive
- Color-coded guide categories (kdenlive:docproperties.guidesCategories) and
  guides JSON (point and range markers)
- Vertical Shorts (1080x1920) with affine/qtblend crop filter and sidecar .srt
- Round-trip marker readback (read_kdenlive_markers) for Yellow edit ranges
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.dom import minidom

from .timeline import (
    MARKER_COLORS,
    CropRect,
    Marker,
    PlacedAudioClip,
    PlacedClip,
    PlacedOverlayClip,
    Timeline,
    format_tc_mlt,
    frames_to_sec,
    write_srt,
)

KDENLIVE_DOC_VERSION = "1.04"
KDENLIVE_APP_VERSION = "24.05.0"

# Reverse map from Kdenlive guide category ID -> canonical Kurgu Makinesi color
_CAT_TO_COLOR: Dict[int, str] = {cat: name for name, (_, cat, _) in MARKER_COLORS.items()}


def _prop(parent: ET.Element, name: str, value: str) -> ET.Element:
    el = ET.SubElement(parent, "property", {"name": name})
    el.text = str(value)
    return el


def _prettify_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(raw)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _crop_to_mlt_rect(crop: CropRect, width: int, height: int) -> str:
    """Convert CropRect to MLT affine rect string 'x y w h opacity'."""
    w = int(round(width * crop.scale))
    h = int(round(height * crop.scale))
    if crop.x != 0.0 or crop.y != 0.0:
        x = int(round(crop.x))
        y = int(round(crop.y))
    else:
        x = int(round((width / 2.0) - (w * crop.center_x)))
        y = int(round((height / 2.0) - (h * crop.center_y)))
    return f"{x} {y} {w} {h} 1"


def _add_blank_if_needed(playlist: ET.Element, cursor: int, target: int) -> int:
    if target > cursor:
        gap = target - cursor
        ET.SubElement(playlist, "blank", {"length": str(gap)})
        return target
    return cursor


def write_kdenlive(timeline: Timeline, output_dir: str | Path) -> Path:
    """Write a complete multi-track .kdenlive project file (plus .srt if captions exist)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timeline.name}.kdenlive"

    placed_v1, placed_a2, placed_ov, markers, total_frames = timeline.layout()
    fps_num = int(round(timeline.fps))
    fps_den = 1
    if abs(timeline.fps - 23.976) < 0.01:
        fps_num, fps_den = 24000, 1001
    elif abs(timeline.fps - 29.97) < 0.01:
        fps_num, fps_den = 30000, 1001
    elif abs(timeline.fps - 59.94) < 0.01:
        fps_num, fps_den = 60000, 1001

    mlt = ET.Element(
        "mlt",
        {
            "LC_NUMERIC": "C",
            "producer": "main_bin",
            "version": "7.24.0",
            "root": str(out_dir.resolve()),
        },
    )

    ET.SubElement(
        mlt,
        "profile",
        {
            "description": f"{timeline.width}x{timeline.height} {timeline.fps:.2f}fps",
            "width": str(timeline.width),
            "height": str(timeline.height),
            "progressive": "1",
            "sample_aspect_num": "1",
            "sample_aspect_den": "1",
            "display_aspect_num": str(timeline.width),
            "display_aspect_den": str(timeline.height),
            "frame_rate_num": str(fps_num),
            "frame_rate_den": str(fps_den),
            "colorspace": "709",
        },
    )

    # Collect unique media resources and assign bin IDs
    file_to_bin_id: Dict[str, str] = {}
    unique_files: List[Tuple[str, bool, bool]] = []  # (path, is_image, is_audio_only)

    def register_media(path: str, is_image: bool = False, is_audio_only: bool = False) -> str:
        if path not in file_to_bin_id:
            bid = f"producer{len(unique_files) + 1}"
            file_to_bin_id[path] = bid
            unique_files.append((path, is_image, is_audio_only))
        return file_to_bin_id[path]

    for pc in placed_v1:
        register_media(pc.clip.file, is_image=pc.media.is_image)
    for ac in placed_a2:
        register_media(ac.file, is_audio_only=True)
    for ov in placed_ov:
        register_media(ov.overlay.file, is_image=ov.media.is_image)

    # Create main bin producers
    for idx, (path, is_image, is_audio_only) in enumerate(unique_files, start=1):
        bid = f"producer{idx}"
        prod = ET.SubElement(mlt, "producer", {"id": bid})
        _prop(prod, "resource", str(Path(path).resolve()) if Path(path).exists() else path)
        _prop(prod, "mlt_service", "qimage" if is_image else "avformat-novalidate")
        _prop(prod, "kdenlive:id", str(idx))
        _prop(prod, "kdenlive:clipname", Path(path).name)
        if is_image:
            _prop(prod, "length", str(max(total_frames, int(timeline.fps * 30))))
        if is_audio_only:
            _prop(prod, "video_index", "-1")

    # Black track producer
    black = ET.SubElement(mlt, "producer", {"id": "black_track", "in": "0", "out": str(total_frames)})
    _prop(black, "length", str(total_frames + 1))
    _prop(black, "resource", "black")
    _prop(black, "mlt_service", "color")
    _prop(black, "set.test_audio", "0")

    # Track playlists:
    # track_id 0 = A2 (External WAV), 1 = A1 (Camera Audio), 2 = V1 (A-roll), 3 = V2 (B-roll), 4 = V3 (Overlays)
    pl_a2 = ET.SubElement(mlt, "playlist", {"id": "playlist_a2"})
    _prop(pl_a2, "kdenlive:audio_track", "1")
    pl_a1 = ET.SubElement(mlt, "playlist", {"id": "playlist_a1"})
    _prop(pl_a1, "kdenlive:audio_track", "1")
    pl_v1 = ET.SubElement(mlt, "playlist", {"id": "playlist_v1"})
    pl_v2 = ET.SubElement(mlt, "playlist", {"id": "playlist_v2"})
    pl_v3 = ET.SubElement(mlt, "playlist", {"id": "playlist_v3"})

    # Track-scoped producer clones (Kdenlive expects separate video/audio producers per track)
    track_prod_counter = 0

    def make_track_producer(
        src_path: str,
        is_image: bool,
        audio_only: bool,
        video_only: bool,
        crop: Optional[CropRect] = None,
        gain_db: float = 0.0,
    ) -> str:
        nonlocal track_prod_counter
        track_prod_counter += 1
        pid = f"track_prod_{track_prod_counter}"
        prod = ET.SubElement(mlt, "producer", {"id": pid})
        _prop(prod, "resource", str(Path(src_path).resolve()) if Path(src_path).exists() else src_path)
        _prop(prod, "mlt_service", "qimage" if is_image else "avformat-novalidate")
        _prop(prod, "kdenlive:id", file_to_bin_id[src_path].replace("producer", ""))
        if audio_only:
            _prop(prod, "set.test_image", "1")
            _prop(prod, "set.test_audio", "0")
            _prop(prod, "video_index", "-1")
            if gain_db != 0.0:
                flt = ET.SubElement(prod, "filter", {"id": f"flt_vol_{track_prod_counter}"})
                _prop(flt, "mlt_service", "volume")
                _prop(flt, "gain", f"{gain_db:.2f}dB")
        elif video_only:
            _prop(prod, "set.test_audio", "1")
            _prop(prod, "set.test_image", "0")
            _prop(prod, "audio_index", "-1")
            if crop is not None:
                flt = ET.SubElement(prod, "filter", {"id": f"flt_crop_{track_prod_counter}"})
                _prop(flt, "mlt_service", "qtblend")
                _prop(flt, "rect", _crop_to_mlt_rect(crop, timeline.width, timeline.height))
                _prop(flt, "compositing", "0")
                _prop(flt, "distort", "0")
        return pid

    # Groups JSON so V1 + A1 (+ synced A2) move together in Kdenlive
    # Kdenlive group format: {"children": [{"data": "<track_idx>:<frame>", "leaf": "clip", "type": "Leaf"}, ...], "type": "AVSplit"}
    groups: List[Dict[str, object]] = []

    # Populate V1 (track index 2) and A1 (track index 1)
    v1_cursor = 0
    a1_cursor = 0
    for pc in placed_v1:
        v1_cursor = _add_blank_if_needed(pl_v1, v1_cursor, pc.timeline_start)
        v_pid = make_track_producer(
            pc.clip.file, is_image=pc.media.is_image, audio_only=False, video_only=True, crop=pc.clip.crop
        )
        ET.SubElement(
            pl_v1,
            "entry",
            {"producer": v_pid, "in": str(pc.in_frame), "out": str(pc.out_frame)},
        )
        v1_cursor += pc.duration_frames

        group_children: List[Dict[str, str]] = [
            {"data": f"2:{pc.timeline_start}", "leaf": "clip", "type": "Leaf"}
        ]

        if pc.media.has_audio and not pc.clip.mute_camera_audio:
            a1_cursor = _add_blank_if_needed(pl_a1, a1_cursor, pc.timeline_start)
            a_pid = make_track_producer(
                pc.clip.file, is_image=False, audio_only=True, video_only=False
            )
            ET.SubElement(
                pl_a1,
                "entry",
                {"producer": a_pid, "in": str(pc.in_frame), "out": str(pc.out_frame)},
            )
            a1_cursor += pc.duration_frames
            group_children.append(
                {"data": f"1:{pc.timeline_start}", "leaf": "clip", "type": "Leaf"}
            )

        # Link synced external WAV (on A2, track index 0) if present
        for ac in placed_a2:
            if ac.linked_v1_index == pc.index:
                group_children.append(
                    {"data": f"0:{ac.timeline_start}", "leaf": "clip", "type": "Leaf"}
                )

        if len(group_children) > 1:
            groups.append({"children": group_children, "type": "AVSplit"})

    # Populate A2 (External WAV audio, track index 0)
    a2_cursor = 0
    for ac in placed_a2:
        a2_cursor = _add_blank_if_needed(pl_a2, a2_cursor, ac.timeline_start)
        a_pid = make_track_producer(
            ac.file, is_image=False, audio_only=True, video_only=False, gain_db=ac.gain_db
        )
        ET.SubElement(
            pl_a2,
            "entry",
            {"producer": a_pid, "in": str(ac.in_frame), "out": str(ac.out_frame)},
        )
        a2_cursor += ac.duration_frames

    # Populate V2 (B-roll, track index 3) and V3 (Overlays/Graphics, track index 4)
    v2_cursor = 0
    v3_cursor = 0
    for ov in placed_ov:
        target_pl = pl_v2 if ov.overlay.track <= 2 else pl_v3
        if ov.overlay.track <= 2:
            v2_cursor = _add_blank_if_needed(target_pl, v2_cursor, ov.timeline_start)
            v2_cursor += ov.duration_frames
        else:
            v3_cursor = _add_blank_if_needed(target_pl, v3_cursor, ov.timeline_start)
            v3_cursor += ov.duration_frames

        ov_pid = make_track_producer(
            ov.overlay.file,
            is_image=ov.media.is_image,
            audio_only=False,
            video_only=ov.overlay.mute_audio,
            crop=ov.overlay.crop,
        )
        ET.SubElement(
            target_pl,
            "entry",
            {"producer": ov_pid, "in": str(ov.in_frame), "out": str(ov.out_frame)},
        )

    # Track tractors (Kdenlive wraps each playlist in a track tractor)
    track_defs = [
        ("tractor_a2", "playlist_a2", "A2 External WAV", True),
        ("tractor_a1", "playlist_a1", "A1 Camera Audio", True),
        ("tractor_v1", "playlist_v1", "V1 A-Roll", False),
        ("tractor_v2", "playlist_v2", "V2 B-Roll", False),
        ("tractor_v3", "playlist_v3", "V3 Overlays", False),
    ]
    for tid, pl_id, label, is_audio in track_defs:
        tr = ET.SubElement(mlt, "tractor", {"id": tid, "in": "0", "out": str(total_frames)})
        _prop(tr, "kdenlive:track_name", label)
        if is_audio:
            _prop(tr, "kdenlive:audio_track", "1")
            _prop(tr, "kdenlive:trackheight", "67")
        else:
            _prop(tr, "kdenlive:trackheight", "67")
        ET.SubElement(tr, "track", {"producer": pl_id, "hide": "video" if is_audio else "audio"})

    # Main sequence tractor
    main_tractor = ET.SubElement(
        mlt, "tractor", {"id": "main_tractor", "in": "0", "out": str(total_frames)}
    )
    _prop(main_tractor, "kdenlive:sequenceproperties.hasAudio", "1")
    _prop(main_tractor, "kdenlive:sequenceproperties.hasVideo", "1")
    ET.SubElement(main_tractor, "track", {"producer": "black_track"})
    for tid, _, _, _ in track_defs:
        ET.SubElement(main_tractor, "track", {"producer": tid})

    # Audio mix transitions (A2=1, A1=2 onto black=0)
    for idx, a_track in enumerate((1, 2), start=1):
        trn = ET.SubElement(main_tractor, "transition", {"id": f"transition_mix_{idx}"})
        _prop(trn, "a_track", "0")
        _prop(trn, "b_track", str(a_track))
        _prop(trn, "mlt_service", "mix")
        _prop(trn, "always_active", "1")
        _prop(trn, "sum", "1")

    # Video compositing transitions (V1=3, V2=4, V3=5 onto black=0 via qtblend)
    for idx, v_track in enumerate((3, 4, 5), start=1):
        trn = ET.SubElement(main_tractor, "transition", {"id": f"transition_blend_{idx}"})
        _prop(trn, "a_track", "0")
        _prop(trn, "b_track", str(v_track))
        _prop(trn, "compositing", "0")
        _prop(trn, "distort", "0")
        _prop(trn, "rotate_center", "1")
        _prop(trn, "mlt_service", "qtblend")
        _prop(trn, "always_active", "1")

    # Build Kdenlive guide categories & guides JSON
    guide_categories = [
        {"color": hx, "comment": name, "index": cat_id}
        for name, (hx, cat_id, _) in MARKER_COLORS.items()
    ]
    guides_json: List[Dict[str, object]] = []
    for m in markers:
        _, cat_id, _ = MARKER_COLORS.get(m.color, MARKER_COLORS["Green"])
        comment = m.name if not m.note else f"{m.name} — {m.note}"
        if m.duration_frames > 0:
            dur_s = frames_to_sec(m.duration_frames, timeline.fps)
            guides_json.append(
                {
                    "comment": f"[START +{dur_s:.2f}s] {comment}",
                    "pos": m.frame,
                    "type": cat_id,
                }
            )
            guides_json.append(
                {
                    "comment": f"[END] {m.name}",
                    "pos": m.end_frame,
                    "type": cat_id,
                }
            )
        else:
            guides_json.append({"comment": comment, "pos": m.frame, "type": cat_id})

    # Optional sidecar SRT captions
    srt_path: Optional[Path] = None
    if timeline.captions:
        srt_path = write_srt(timeline.captions, out_dir / f"{timeline.name}.srt")

    # Main bin playlist (holds document properties)
    main_bin = ET.SubElement(mlt, "playlist", {"id": "main_bin"})
    _prop(main_bin, "kdenlive:docproperties.version", KDENLIVE_DOC_VERSION)
    _prop(main_bin, "kdenlive:docproperties.kdenliveversion", KDENLIVE_APP_VERSION)
    _prop(main_bin, "kdenlive:docproperties.guidesCategories", json.dumps(guide_categories))
    _prop(main_bin, "kdenlive:docproperties.guides", json.dumps(guides_json))
    _prop(main_bin, "kdenlive:docproperties.groups", json.dumps(groups))
    if srt_path is not None:
        _prop(
            main_bin,
            "kdenlive:docproperties.subtitlesList",
            json.dumps([{"file": str(srt_path.name), "id": 0, "name": "Captions"}]),
        )
    for idx in range(1, len(unique_files) + 1):
        ET.SubElement(main_bin, "entry", {"producer": f"producer{idx}"})

    out_path.write_text(_prettify_xml(mlt), encoding="utf-8")
    return out_path


def read_kdenlive_markers(
    kdenlive_path: str | Path,
    color_filter: Optional[str] = "Yellow",
    default_fps: float = 25.0,
) -> List[Marker]:
    """Read guides/markers from a .kdenlive project file for feedback readback.

    Pairs [START ...]/[END] guides (or consecutive same-color Yellow guides)
    into range Markers so editors can mark cuts in Kdenlive and feed them back
    into Kurgu Makinesi's edits JSON.
    """
    tree = ET.parse(str(kdenlive_path))
    root = tree.getroot()

    # Determine FPS from profile
    fps = default_fps
    prof = root.find("profile")
    if prof is not None:
        try:
            num = float(prof.attrib.get("frame_rate_num", fps))
            den = float(prof.attrib.get("frame_rate_den", 1))
            if den > 0:
                fps = num / den
        except ValueError:
            pass

    guides_raw: Optional[str] = None
    for prop in root.findall(".//property[@name='kdenlive:docproperties.guides']"):
        if prop.text:
            guides_raw = prop.text
            break

    if not guides_raw:
        return []

    raw_items = json.loads(guides_raw)
    raw_items.sort(key=lambda g: int(g.get("pos", 0)))

    # Filter by color category if requested
    filtered: List[Tuple[int, str, str]] = []
    for item in raw_items:
        pos = int(item.get("pos", 0))
        cat_id = int(item.get("type", 0))
        color_name = _CAT_TO_COLOR.get(cat_id, "Green")
        comment = str(item.get("comment", ""))
        if color_filter and color_name.lower() != color_filter.lower():
            continue
        filtered.append((pos, color_name, comment))

    # Pair [START]/[END] or consecutive point markers into ranges
    markers: List[Marker] = []
    i = 0
    while i < len(filtered):
        pos, color_name, comment = filtered[i]
        if i + 1 < len(filtered) and (
            comment.startswith("[START") or filtered[i + 1][2].startswith("[END")
        ):
            end_pos = filtered[i + 1][0]
            clean_name = comment.split("]", 1)[-1].strip() if "]" in comment else comment
            markers.append(
                Marker(
                    frame=pos,
                    duration_frames=max(0, end_pos - pos),
                    name=clean_name or "Edit range",
                    color=color_name,
                    note=f"Read from Kdenlive ({format_tc_mlt(pos / fps)})",
                )
            )
            i += 2
        else:
            markers.append(
                Marker(
                    frame=pos,
                    duration_frames=0,
                    name=comment or "Marker",
                    color=color_name,
                )
            )
            i += 1

    return markers
