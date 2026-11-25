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
import time
import uuid
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

KDENLIVE_DOC_VERSION = "1.1"
KDENLIVE_APP_VERSION = "26.08.0"

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

    # Collect unique media resources and assign bin IDs + known frame lengths
    file_to_bin_id: Dict[str, str] = {}
    file_lengths: Dict[str, int] = {}
    unique_files: List[Tuple[str, bool, bool]] = []  # (path, is_image, is_audio_only)

    def register_media(
        path: str, is_image: bool = False, is_audio_only: bool = False, min_frames: int = 0
    ) -> str:
        if path not in file_to_bin_id:
            bid = f"producer{len(unique_files) + 1}"
            file_to_bin_id[path] = bid
            unique_files.append((path, is_image, is_audio_only))
        if min_frames > file_lengths.get(path, 0):
            file_lengths[path] = min_frames
        return file_to_bin_id[path]

    for pc in placed_v1:
        dur_f = int(round(pc.media.duration * timeline.fps)) if pc.media.duration > 0 else 0
        register_media(
            pc.clip.file, is_image=pc.media.is_image, min_frames=max(dur_f, pc.out_frame + 1)
        )
    for ac in placed_a2:
        register_media(ac.file, is_audio_only=True, min_frames=ac.out_frame + 1)
    for ov in placed_ov:
        dur_f = int(round(ov.media.duration * timeline.fps)) if ov.media.duration > 0 else 0
        register_media(
            ov.overlay.file, is_image=ov.media.is_image, min_frames=max(dur_f, ov.out_frame + 1)
        )

    # Create main bin producers (with explicit length/out so avformat-novalidate loads fast and plays)
    # Kdenlive reserves kdenlive:id 2 for the Sequences folder and 3 for the primary sequence.
    file_uuids: Dict[str, str] = {}
    file_kdenlive_ids: Dict[str, str] = {}
    for idx, (path, is_image, is_audio_only) in enumerate(unique_files, start=1):
        bid = f"producer{idx}"
        kid = str(idx + 3)
        file_kdenlive_ids[path] = kid
        clip_uuid = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"kdenlive-bin:{idx}:{path}")) + "}"
        file_uuids[path] = clip_uuid
        length_f = max(
            file_lengths.get(path, 0),
            max(total_frames, int(timeline.fps * 30)) if is_image else 1,
        )
        prod = ET.SubElement(mlt, "producer", {"id": bid, "in": "0", "out": str(length_f - 1)})
        _prop(prod, "length", str(length_f))
        _prop(prod, "resource", str(Path(path).resolve()) if Path(path).exists() else path)
        _prop(prod, "mlt_service", "qimage" if is_image else "avformat-novalidate")
        _prop(prod, "kdenlive:id", kid)
        _prop(prod, "kdenlive:clipname", Path(path).name)
        _prop(prod, "kdenlive:control_uuid", clip_uuid)
        _prop(prod, "kdenlive:clip_type", "1" if is_audio_only else ("2" if is_image else "0"))
        if is_audio_only:
            _prop(prod, "video_index", "-1")

    # Black track producer
    black = ET.SubElement(mlt, "producer", {"id": "black_track", "in": "0", "out": str(total_frames)})
    _prop(black, "length", "2147483647")
    _prop(black, "eof", "continue")
    _prop(black, "resource", "black")
    _prop(black, "aspect_ratio", "1")
    _prop(black, "mlt_service", "color")
    _prop(black, "kdenlive:playlistid", "black_track")
    _prop(black, "mlt_image_format", "rgba")
    _prop(black, "set.test_audio", "0")

    # Track playlists are built detached first so all track producers are emitted
    # BEFORE playlists in MLT XML document order (required by MLT's single-pass XML parser).
    # Kdenlive requires TWO playlists per track tractor (primary + empty sibling for mixes).
    # track_id 0 = A2 (External WAV), 1 = A1 (Camera Audio), 2 = V1 (A-roll), 3 = V2 (B-roll), 4 = V3 (Overlays)
    pl_a2 = ET.Element("playlist", {"id": "playlist_a2"})
    _prop(pl_a2, "kdenlive:audio_track", "1")
    pl_a2_b = ET.Element("playlist", {"id": "playlist_a2_b"})
    _prop(pl_a2_b, "kdenlive:audio_track", "1")

    pl_a1 = ET.Element("playlist", {"id": "playlist_a1"})
    _prop(pl_a1, "kdenlive:audio_track", "1")
    pl_a1_b = ET.Element("playlist", {"id": "playlist_a1_b"})
    _prop(pl_a1_b, "kdenlive:audio_track", "1")

    pl_v1 = ET.Element("playlist", {"id": "playlist_v1"})
    pl_v1_b = ET.Element("playlist", {"id": "playlist_v1_b"})
    pl_v2 = ET.Element("playlist", {"id": "playlist_v2"})
    pl_v2_b = ET.Element("playlist", {"id": "playlist_v2_b"})
    pl_v3 = ET.Element("playlist", {"id": "playlist_v3"})
    pl_v3_b = ET.Element("playlist", {"id": "playlist_v3_b"})

    # Track-scoped producer clones (reused per unique file+mode to avoid opening hundreds of file handles)
    track_prod_counter = 0
    track_prod_cache: Dict[Tuple[str, bool, bool, bool, Optional[str], float], str] = {}

    def make_track_producer(
        src_path: str,
        is_image: bool,
        audio_only: bool,
        video_only: bool,
        crop: Optional[CropRect] = None,
        gain_db: float = 0.0,
    ) -> str:
        nonlocal track_prod_counter
        crop_key = _crop_to_mlt_rect(crop, timeline.width, timeline.height) if crop is not None else None
        cache_key = (src_path, is_image, audio_only, video_only, crop_key, round(gain_db, 3))
        if cache_key in track_prod_cache:
            return track_prod_cache[cache_key]

        track_prod_counter += 1
        pid = f"track_prod_{track_prod_counter}"
        length_f = max(
            file_lengths.get(src_path, 0),
            max(total_frames, int(timeline.fps * 30)) if is_image else 1,
        )
        prod = ET.SubElement(mlt, "producer", {"id": pid, "in": "0", "out": str(length_f - 1)})
        _prop(prod, "length", str(length_f))
        _prop(prod, "resource", str(Path(src_path).resolve()) if Path(src_path).exists() else src_path)
        _prop(prod, "mlt_service", "qimage" if is_image else "avformat-novalidate")
        _prop(prod, "kdenlive:id", file_kdenlive_ids[src_path])
        _prop(prod, "kdenlive:control_uuid", file_uuids[src_path])
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
        track_prod_cache[cache_key] = pid
        return pid

    # Groups JSON so V1 + A1 (+ synced A2) move together in Kdenlive
    # Kdenlive 1.1 group format: {"children": [{"data": "<track_idx>:<frame>:-1", "leaf": "clip", "type": "Leaf"}, ...], "type": "AVSplit"}
    groups: List[Dict[str, object]] = []

    def add_entry(playlist: ET.Element, prod_id: str, src_path: str, in_f: int, out_f: int) -> ET.Element:
        ent = ET.SubElement(playlist, "entry", {"producer": prod_id, "in": str(in_f), "out": str(out_f)})
        _prop(ent, "kdenlive:id", file_kdenlive_ids[src_path])
        return ent

    # Populate V1 (track index 2) and A1 (track index 1)
    v1_cursor = 0
    a1_cursor = 0
    for pc in placed_v1:
        v1_cursor = _add_blank_if_needed(pl_v1, v1_cursor, pc.timeline_start)
        v_pid = make_track_producer(
            pc.clip.file, is_image=pc.media.is_image, audio_only=False, video_only=True, crop=pc.clip.crop
        )
        add_entry(pl_v1, v_pid, pc.clip.file, pc.in_frame, pc.out_frame)
        v1_cursor += pc.duration_frames

        group_children: List[Dict[str, str]] = [
            {"data": f"2:{pc.timeline_start}:-1", "leaf": "clip", "type": "Leaf"}
        ]

        if pc.media.has_audio and not pc.clip.mute_camera_audio:
            a1_cursor = _add_blank_if_needed(pl_a1, a1_cursor, pc.timeline_start)
            a_pid = make_track_producer(
                pc.clip.file, is_image=False, audio_only=True, video_only=False
            )
            add_entry(pl_a1, a_pid, pc.clip.file, pc.in_frame, pc.out_frame)
            a1_cursor += pc.duration_frames
            group_children.append(
                {"data": f"1:{pc.timeline_start}:-1", "leaf": "clip", "type": "Leaf"}
            )

        # Link synced external WAV (on A2, track index 0) if present
        for ac in placed_a2:
            if ac.linked_v1_index == pc.index:
                group_children.append(
                    {"data": f"0:{ac.timeline_start}:-1", "leaf": "clip", "type": "Leaf"}
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
        add_entry(pl_a2, a_pid, ac.file, ac.in_frame, ac.out_frame)
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
        add_entry(target_pl, ov_pid, ov.overlay.file, ov.in_frame, ov.out_frame)

    # Append playlists AFTER all track producers so MLT resolves every producer reference
    for pl in (pl_a2, pl_a2_b, pl_a1, pl_a1_b, pl_v1, pl_v1_b, pl_v2, pl_v2_b, pl_v3, pl_v3_b):
        mlt.append(pl)

    # Track tractors (Kdenlive requires TWO subtracks per track tractor)
    track_defs = [
        ("tractor_a2", "playlist_a2", "playlist_a2_b", "A2 External WAV", True),
        ("tractor_a1", "playlist_a1", "playlist_a1_b", "A1 Camera Audio", True),
        ("tractor_v1", "playlist_v1", "playlist_v1_b", "V1 A-Roll", False),
        ("tractor_v2", "playlist_v2", "playlist_v2_b", "V2 B-Roll", False),
        ("tractor_v3", "playlist_v3", "playlist_v3_b", "V3 Overlays", False),
    ]
    flt_counter = 0
    for tid, pl_id, pl_b_id, label, is_audio in track_defs:
        tr = ET.SubElement(mlt, "tractor", {"id": tid, "in": "0", "out": str(total_frames)})
        _prop(tr, "kdenlive:track_name", label)
        _prop(tr, "kdenlive:trackheight", "67")
        _prop(tr, "kdenlive:timeline_active", "1")
        _prop(tr, "kdenlive:collapsed", "0")
        if is_audio:
            _prop(tr, "kdenlive:audio_track", "1")
        hide_mode = "video" if is_audio else "audio"
        ET.SubElement(tr, "track", {"producer": pl_id, "hide": hide_mode})
        ET.SubElement(tr, "track", {"producer": pl_b_id, "hide": hide_mode})
        if is_audio:
            flt_counter += 1
            f_vol = ET.SubElement(tr, "filter", {"id": f"trk_flt_{flt_counter}"})
            _prop(f_vol, "window", "75")
            _prop(f_vol, "max_gain", "20dB")
            _prop(f_vol, "channel_mask", "-1")
            _prop(f_vol, "mlt_service", "volume")
            _prop(f_vol, "internal_added", "237")
            _prop(f_vol, "disable", "1")
            flt_counter += 1
            f_pan = ET.SubElement(tr, "filter", {"id": f"trk_flt_{flt_counter}"})
            _prop(f_pan, "channel", "-1")
            _prop(f_pan, "mlt_service", "panner")
            _prop(f_pan, "internal_added", "237")
            _prop(f_pan, "start", "0.5")
            _prop(f_pan, "disable", "1")
            flt_counter += 1
            f_lvl = ET.SubElement(tr, "filter", {"id": f"trk_flt_{flt_counter}"})
            _prop(f_lvl, "iec_scale", "0")
            _prop(f_lvl, "mlt_service", "audiolevel")
            _prop(f_lvl, "internal_added", "237")
            _prop(f_lvl, "dbpeak", "1")
            _prop(f_lvl, "disable", "1")

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

    seq_uuid = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"kdenlive-seq:{timeline.name}")) + "}"
    seq_bin_id = "3"

    # Main sequence tractor (Kdenlive 1.1 sequence format)
    main_tractor = ET.SubElement(
        mlt, "tractor", {"id": "main_tractor", "in": "0", "out": str(total_frames)}
    )
    _prop(main_tractor, "kdenlive:duration", str(total_frames + 1))
    _prop(main_tractor, "kdenlive:maxduration", str(total_frames + 1))
    _prop(main_tractor, "kdenlive:clipname", timeline.name)
    _prop(main_tractor, "kdenlive:uuid", seq_uuid)
    _prop(main_tractor, "kdenlive:control_uuid", seq_uuid)
    _prop(main_tractor, "kdenlive:producer_type", "17")
    _prop(main_tractor, "kdenlive:id", seq_bin_id)
    _prop(main_tractor, "kdenlive:clip_type", "0")
    _prop(main_tractor, "kdenlive:folderid", "2")
    _prop(main_tractor, "kdenlive:sequenceproperties.documentuuid", seq_uuid)
    _prop(main_tractor, "kdenlive:sequenceproperties.hasAudio", "1")
    _prop(main_tractor, "kdenlive:sequenceproperties.hasVideo", "1")
    _prop(main_tractor, "kdenlive:sequenceproperties.tracksCount", str(len(track_defs)))
    _prop(main_tractor, "kdenlive:sequenceproperties.activeTrack", "2")
    _prop(main_tractor, "kdenlive:sequenceproperties.audioTarget", "0")
    _prop(main_tractor, "kdenlive:sequenceproperties.videoTarget", "2")
    _prop(main_tractor, "kdenlive:sequenceproperties.verticalzoom", "1")
    _prop(main_tractor, "kdenlive:sequenceproperties.zoom", "8")
    _prop(main_tractor, "kdenlive:sequenceproperties.position", "0")
    _prop(main_tractor, "kdenlive:sequenceproperties.scrollPos", "0")
    _prop(main_tractor, "kdenlive:sequenceproperties.zonein", "0")
    _prop(main_tractor, "kdenlive:sequenceproperties.zoneout", "75")
    _prop(main_tractor, "kdenlive:sequenceproperties.groups", json.dumps(groups))
    _prop(main_tractor, "kdenlive:sequenceproperties.guides", json.dumps(guides_json))

    ET.SubElement(main_tractor, "track", {"producer": "black_track"})
    for tid, _, _, _, _ in track_defs:
        ET.SubElement(main_tractor, "track", {"producer": tid})

    # Internal audio mix transitions (A2=1, A1=2 onto black=0)
    for idx, a_track in enumerate((1, 2), start=1):
        trn = ET.SubElement(main_tractor, "transition", {"id": f"transition_mix_{idx}"})
        _prop(trn, "a_track", "0")
        _prop(trn, "b_track", str(a_track))
        _prop(trn, "mlt_service", "mix")
        _prop(trn, "kdenlive_id", "mix")
        _prop(trn, "internal_added", "237")
        _prop(trn, "always_active", "1")
        _prop(trn, "accepts_blanks", "1")
        _prop(trn, "sum", "1")

    # Internal video compositing transitions (V1=3, V2=4, V3=5 onto black=0 via qtblend)
    for idx, v_track in enumerate((3, 4, 5), start=1):
        trn = ET.SubElement(main_tractor, "transition", {"id": f"transition_blend_{idx}"})
        _prop(trn, "a_track", "0")
        _prop(trn, "b_track", str(v_track))
        _prop(trn, "compositing", "0")
        _prop(trn, "distort", "0")
        _prop(trn, "rotate_center", "0")
        _prop(trn, "mlt_service", "qtblend")
        _prop(trn, "kdenlive_id", "qtblend")
        _prop(trn, "internal_added", "237")
        _prop(trn, "always_active", "1")

    # Master audio filters on sequence tractor
    m_vol = ET.SubElement(main_tractor, "filter", {"id": "master_vol"})
    _prop(m_vol, "window", "75")
    _prop(m_vol, "max_gain", "20dB")
    _prop(m_vol, "channel_mask", "-1")
    _prop(m_vol, "mlt_service", "volume")
    _prop(m_vol, "internal_added", "237")
    _prop(m_vol, "disable", "1")
    m_pan = ET.SubElement(main_tractor, "filter", {"id": "master_pan"})
    _prop(m_pan, "channel", "-1")
    _prop(m_pan, "mlt_service", "panner")
    _prop(m_pan, "internal_added", "237")
    _prop(m_pan, "start", "0.5")
    _prop(m_pan, "disable", "1")

    # Main bin playlist (holds document properties, bin clips, and sequence reference)
    # xml_retain=1 is REQUIRED so MLT does not garbage-collect main_bin when project_tractor is root.
    main_bin = ET.SubElement(mlt, "playlist", {"id": "main_bin"})
    _prop(main_bin, "kdenlive:folder.-1.2", "Sequences")
    _prop(main_bin, "kdenlive:sequenceFolder", "2")
    _prop(main_bin, "kdenlive:docproperties.version", KDENLIVE_DOC_VERSION)
    _prop(main_bin, "kdenlive:docproperties.kdenliveversion", KDENLIVE_APP_VERSION)
    _prop(main_bin, "kdenlive:docproperties.activetimeline", seq_uuid)
    _prop(main_bin, "kdenlive:docproperties.opensequences", seq_uuid)
    _prop(main_bin, "kdenlive:docproperties.uuid", seq_uuid)
    _prop(main_bin, "kdenlive:docproperties.documentid", str(int(time.time() * 1000)))
    _prop(main_bin, "kdenlive:docproperties.audioChannels", "2")
    _prop(main_bin, "kdenlive:docproperties.guidesCategories", json.dumps(guide_categories))
    _prop(main_bin, "kdenlive:docproperties.guides", json.dumps(guides_json))
    _prop(main_bin, "kdenlive:docproperties.groups", json.dumps(groups))
    if srt_path is not None:
        _prop(
            main_bin,
            "kdenlive:docproperties.subtitlesList",
            json.dumps([{"file": str(srt_path.name), "id": 0, "name": "Captions"}]),
        )
    _prop(main_bin, "xml_retain", "1")
    for idx, (path, is_image, _) in enumerate(unique_files, start=1):
        length_f = max(
            file_lengths.get(path, 0),
            max(total_frames, int(timeline.fps * 30)) if is_image else 1,
        )
        ET.SubElement(
            main_bin, "entry", {"producer": f"producer{idx}", "in": "0", "out": str(length_f - 1)}
        )
    ET.SubElement(main_bin, "entry", {"producer": "main_tractor", "in": "0", "out": str(total_frames)})

    # Root project tractor (MUST be the final element so both Kdenlive 1.1 and melt play main_tractor)
    proj_tractor = ET.SubElement(
        mlt, "tractor", {"id": "project_tractor", "in": "0", "out": str(total_frames)}
    )
    _prop(proj_tractor, "kdenlive:projectTractor", "1")
    ET.SubElement(
        proj_tractor, "track", {"producer": "main_tractor", "in": "0", "out": str(total_frames)}
    )

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
    for prop_name in ("kdenlive:sequenceproperties.guides", "kdenlive:docproperties.guides"):
        for prop in root.findall(f".//property[@name='{prop_name}']"):
            if prop.text:
                guides_raw = prop.text
                break
        if guides_raw:
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
