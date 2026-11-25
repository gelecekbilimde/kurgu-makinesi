"""Shotcut (.mlt MLT XML) writer and marker reader for Kurgu Makinesi.

Follows Shotcut (https://github.com/mltframework/shotcut) MLT XML conventions:
- Multi-track tractor0: background + A1 (External WAV) + V1 (A-roll) +
  V2 (B-roll) + V3 (Overlays / Graphics)
- Audio mixing via 'mix' transitions and alpha video compositing via
  'frei0r.cairoblend' transitions
- Uses 'qimage' producer for still graphics/screenshots and 'avformat-novalidate'
  chains for video/audio
- Color-coded point and range markers via shotcut:markers:{n}:text/start/end/color
- Vertical Shorts (1080x1920) with affine (Size, Position & Rotate) face-crop
  filter and sidecar .srt captions
- Round-trip marker readback (read_shotcut_markers)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.dom import minidom

from .timeline import (
    MARKER_COLORS,
    CropRect,
    Marker,
    Timeline,
    format_tc_mlt,
    frames_to_sec,
    hex_to_canonical_color,
    sec_to_frames,
    write_srt,
)

SHOTCUT_MLT_VERSION = "7.24.0"
SHOTCUT_TITLE = "Shotcut version 24.04.28"


def _prop(parent: ET.Element, name: str, value: str) -> ET.Element:
    el = ET.SubElement(parent, "property", {"name": name})
    el.text = str(value)
    return el


def _prettify_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(raw)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _parse_mlt_clock(clock: str) -> float:
    """Parse HH:MM:SS.mmm (or plain seconds) into float seconds."""
    clock = clock.strip()
    m = re.match(r"^(\d+):(\d{2}):(\d{2}(?:\.\d+)?)$", clock)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    try:
        return float(clock)
    except ValueError:
        return 0.0


def _crop_to_affine_rect(crop: CropRect, width: int, height: int) -> str:
    w = int(round(width * crop.scale))
    h = int(round(height * crop.scale))
    if crop.x != 0.0 or crop.y != 0.0:
        x = int(round(crop.x))
        y = int(round(crop.y))
    else:
        x = int(round((width / 2.0) - (w * crop.center_x)))
        y = int(round((height / 2.0) - (h * crop.center_y)))
    return f"{x} {y} {w} {h} 1"


def _add_blank(playlist: ET.Element, cursor: int, target: int, fps: float) -> int:
    if target > cursor:
        gap_sec = frames_to_sec(target - cursor, fps)
        ET.SubElement(playlist, "blank", {"length": format_tc_mlt(gap_sec)})
        return target
    return cursor


def write_shotcut(timeline: Timeline, output_dir: str | Path) -> Path:
    """Write a Shotcut-compatible multi-track .mlt project file (plus .srt if captions exist)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timeline.name}.mlt"

    placed_v1, placed_a2, placed_ov, markers, total_frames = timeline.layout()
    fps = timeline.fps
    fps_num = int(round(fps))
    fps_den = 1
    if abs(fps - 23.976) < 0.01:
        fps_num, fps_den = 24000, 1001
    elif abs(fps - 29.97) < 0.01:
        fps_num, fps_den = 30000, 1001
    elif abs(fps - 59.94) < 0.01:
        fps_num, fps_den = 60000, 1001

    mlt = ET.Element(
        "mlt",
        {
            "LC_NUMERIC": "C",
            "version": SHOTCUT_MLT_VERSION,
            "title": SHOTCUT_TITLE,
            "producer": "main_bin",
        },
    )

    ET.SubElement(
        mlt,
        "profile",
        {
            "description": f"{timeline.width}x{timeline.height} {fps:.2f}fps",
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

    main_bin = ET.SubElement(mlt, "playlist", {"id": "main_bin"})
    _prop(main_bin, "xml_retain", "1")

    # Black background producer + background playlist (Shotcut track 0 convention)
    total_out_tc = format_tc_mlt(frames_to_sec(max(0, total_frames - 1), fps))
    total_len_tc = format_tc_mlt(frames_to_sec(total_frames, fps))
    bg = ET.SubElement(mlt, "producer", {"id": "black", "in": "00:00:00.000", "out": total_out_tc})
    _prop(bg, "length", total_len_tc)
    _prop(bg, "eof", "pause")
    _prop(bg, "resource", "0")
    _prop(bg, "aspect_ratio", "1")
    _prop(bg, "mlt_service", "color")
    _prop(bg, "mlt_image_format", "rgba")
    _prop(bg, "set.test_audio", "0")

    pl_bg = ET.SubElement(mlt, "playlist", {"id": "background"})
    ET.SubElement(pl_bg, "entry", {"producer": "black", "in": "00:00:00.000", "out": total_out_tc})

    # Pre-compute full source frame lengths per unique media path so avformat-novalidate
    # loads instantaneously and allows trimming past the initial cut in Shotcut.
    file_lengths: Dict[str, int] = {}
    for pc in placed_v1:
        dur_f = int(round(pc.media.duration * fps)) if pc.media.duration > 0 else 0
        file_lengths[pc.clip.file] = max(file_lengths.get(pc.clip.file, 0), dur_f, pc.out_frame + 1)
    for ac in placed_a2:
        file_lengths[ac.file] = max(file_lengths.get(ac.file, 0), ac.out_frame + 1)
    for ov in placed_ov:
        dur_f = int(round(ov.media.duration * fps)) if ov.media.duration > 0 else 0
        file_lengths[ov.overlay.file] = max(
            file_lengths.get(ov.overlay.file, 0), dur_f, ov.out_frame + 1
        )

    chain_counter = 0
    chain_cache: Dict[Tuple[str, bool, bool, bool, Optional[str], float], str] = {}

    def create_media_node(
        src_path: str,
        in_f: int,
        out_f: int,
        is_image: bool = False,
        mute_audio: bool = False,
        audio_only: bool = False,
        crop: Optional[CropRect] = None,
        gain_db: float = 0.0,
    ) -> str:
        nonlocal chain_counter
        crop_key = _crop_to_affine_rect(crop, timeline.width, timeline.height) if crop is not None else None
        # Only cache nodes without per-cut range-scoped affine filters
        cache_key = (src_path, is_image, mute_audio, audio_only, crop_key, round(gain_db, 3))
        if crop is None and cache_key in chain_cache:
            return chain_cache[cache_key]

        chain_counter += 1
        cid = f"chain{chain_counter}" if not is_image else f"producer{chain_counter}"
        tag = "producer" if is_image else "chain"
        length_f = max(
            file_lengths.get(src_path, 0),
            out_f + 1,
            max(total_frames, int(fps * 30)) if is_image else 1,
        )
        in_tc = format_tc_mlt(frames_to_sec(in_f, fps))
        out_tc = format_tc_mlt(frames_to_sec(out_f, fps))
        full_out_tc = format_tc_mlt(frames_to_sec(max(0, length_f - 1), fps))
        full_len_tc = format_tc_mlt(frames_to_sec(length_f, fps))

        node = ET.SubElement(mlt, tag, {"id": cid, "in": "00:00:00.000", "out": full_out_tc})
        _prop(node, "length", full_len_tc)
        _prop(node, "eof", "pause")
        _prop(node, "resource", str(Path(src_path).resolve()) if Path(src_path).exists() else src_path)
        _prop(node, "mlt_service", "qimage" if is_image else "avformat-novalidate")
        _prop(node, "shotcut:caption", Path(src_path).name)
        if mute_audio:
            _prop(node, "audio_index", "-1")
        if audio_only:
            _prop(node, "video_index", "-1")
            if gain_db != 0.0:
                flt = ET.SubElement(node, "filter", {"id": f"filter_vol_{chain_counter}"})
                _prop(flt, "mlt_service", "volume")
                _prop(flt, "level", f"{gain_db:.2f}")
        if crop is not None:
            flt = ET.SubElement(node, "filter", {"id": f"filter_affine_{chain_counter}", "in": in_tc, "out": out_tc})
            _prop(flt, "mlt_service", "affine")
            _prop(flt, "shotcut:filter", "affineSizePosition")
            _prop(flt, "transition.rect", _crop_to_affine_rect(crop, timeline.width, timeline.height))
            _prop(flt, "transition.fill", "1")
            _prop(flt, "transition.distort", "0")
            _prop(flt, "background", "color:#00000000")
        if crop is None:
            chain_cache[cache_key] = cid
        return cid

    # Playlists are built detached first so all <chain>/<producer> declarations appear
    # BEFORE <playlist> elements in MLT XML document order (required by MLT's parser).
    # playlist0 = V1 (A-roll), playlist1 = V2 (B-roll), playlist2 = V3 (Overlays), playlist3 = A1 (External WAV)
    pl_v1 = ET.Element("playlist", {"id": "playlist0"})
    _prop(pl_v1, "shotcut:video", "1")
    _prop(pl_v1, "shotcut:name", "V1 A-Roll")

    pl_v2 = ET.Element("playlist", {"id": "playlist1"})
    _prop(pl_v2, "shotcut:video", "1")
    _prop(pl_v2, "shotcut:name", "V2 B-Roll")

    pl_v3 = ET.Element("playlist", {"id": "playlist2"})
    _prop(pl_v3, "shotcut:video", "1")
    _prop(pl_v3, "shotcut:name", "V3 Overlays")

    pl_a1 = ET.Element("playlist", {"id": "playlist3"})
    _prop(pl_a1, "shotcut:audio", "1")
    _prop(pl_a1, "shotcut:name", "A1 External WAV")

    # Populate V1
    v1_cursor = 0
    for pc in placed_v1:
        v1_cursor = _add_blank(pl_v1, v1_cursor, pc.timeline_start, fps)
        cid = create_media_node(
            pc.clip.file,
            pc.in_frame,
            pc.out_frame,
            is_image=pc.media.is_image,
            mute_audio=pc.clip.mute_camera_audio,
            crop=pc.clip.crop,
        )
        ET.SubElement(
            pl_v1,
            "entry",
            {
                "producer": cid,
                "in": format_tc_mlt(frames_to_sec(pc.in_frame, fps)),
                "out": format_tc_mlt(frames_to_sec(pc.out_frame, fps)),
            },
        )
        v1_cursor += pc.duration_frames

    # Populate V2 & V3
    v2_cursor = 0
    v3_cursor = 0
    for ov in placed_ov:
        if ov.overlay.track <= 2:
            v2_cursor = _add_blank(pl_v2, v2_cursor, ov.timeline_start, fps)
            target_pl = pl_v2
            v2_cursor += ov.duration_frames
        else:
            v3_cursor = _add_blank(pl_v3, v3_cursor, ov.timeline_start, fps)
            target_pl = pl_v3
            v3_cursor += ov.duration_frames

        cid = create_media_node(
            ov.overlay.file,
            ov.in_frame,
            ov.out_frame,
            is_image=ov.media.is_image,
            mute_audio=ov.overlay.mute_audio,
            crop=ov.overlay.crop,
        )
        ET.SubElement(
            target_pl,
            "entry",
            {
                "producer": cid,
                "in": format_tc_mlt(frames_to_sec(ov.in_frame, fps)),
                "out": format_tc_mlt(frames_to_sec(ov.out_frame, fps)),
            },
        )

    # Populate A1 (External WAV)
    a1_cursor = 0
    for ac in placed_a2:
        a1_cursor = _add_blank(pl_a1, a1_cursor, ac.timeline_start, fps)
        cid = create_media_node(
            ac.file,
            ac.in_frame,
            ac.out_frame,
            audio_only=True,
            gain_db=ac.gain_db,
        )
        ET.SubElement(
            pl_a1,
            "entry",
            {
                "producer": cid,
                "in": format_tc_mlt(frames_to_sec(ac.in_frame, fps)),
                "out": format_tc_mlt(frames_to_sec(ac.out_frame, fps)),
            },
        )
        a1_cursor += ac.duration_frames

    # Append track playlists AFTER all media chain/producer nodes
    for pl in (pl_v1, pl_v2, pl_v3, pl_a1):
        mlt.append(pl)

    # Main Shotcut tractor0
    tractor = ET.SubElement(
        mlt,
        "tractor",
        {"id": "tractor0", "title": SHOTCUT_TITLE, "in": "00:00:00.000", "out": total_out_tc},
    )
    _prop(tractor, "shotcut", "1")
    _prop(tractor, "shotcut:projectAudioChannels", "2")
    _prop(tractor, "shotcut:projectFolder", "0")

    # Color-coded point & range markers on tractor0 (native Shotcut nested <properties>)
    if markers:
        markers_el = ET.SubElement(tractor, "properties", {"name": "shotcut:markers"})
        for idx, m in enumerate(markers):
            hx, _, _ = MARKER_COLORS.get(m.color, MARKER_COLORS["Green"])
            start_tc = format_tc_mlt(frames_to_sec(m.frame, fps))
            end_tc = format_tc_mlt(frames_to_sec(m.end_frame, fps))
            text = m.name if not m.note else f"{m.name} — {m.note}"
            m_el = ET.SubElement(markers_el, "properties", {"name": str(idx)})
            _prop(m_el, "text", text)
            _prop(m_el, "start", start_tc)
            _prop(m_el, "end", end_tc)
            _prop(m_el, "color", hx)

    # Track stack: 0=background, 1=V1, 2=V2, 3=V3, 4=A1
    ET.SubElement(tractor, "track", {"producer": "background"})
    ET.SubElement(tractor, "track", {"producer": "playlist0"})
    ET.SubElement(tractor, "track", {"producer": "playlist1"})
    ET.SubElement(tractor, "track", {"producer": "playlist2"})
    ET.SubElement(tractor, "track", {"producer": "playlist3", "hide": "video"})

    # Audio mix transitions for tracks 1, 2, 3, 4 onto 0
    for idx, b_track in enumerate((1, 2, 3, 4), start=1):
        trn = ET.SubElement(tractor, "transition", {"id": f"transition_mix_{idx}"})
        _prop(trn, "a_track", "0")
        _prop(trn, "b_track", str(b_track))
        _prop(trn, "mlt_service", "mix")
        _prop(trn, "always_active", "1")
        _prop(trn, "sum", "1")

    # Video alpha compositing transitions (frei0r.cairoblend) for V1, V2, V3
    for idx, b_track in enumerate((1, 2, 3), start=1):
        trn = ET.SubElement(tractor, "transition", {"id": f"transition_blend_{idx}"})
        _prop(trn, "a_track", "0")
        _prop(trn, "b_track", str(b_track))
        _prop(trn, "version", "0.1")
        _prop(trn, "mlt_service", "frei0r.cairoblend")
        _prop(trn, "threads", "0")
        _prop(trn, "disable", "1" if b_track == 1 else "0")

    # Optional sidecar SRT captions
    if timeline.captions:
        write_srt(timeline.captions, out_dir / f"{timeline.name}.srt")

    out_path.write_text(_prettify_xml(mlt), encoding="utf-8")
    return out_path


def read_shotcut_markers(
    mlt_path: str | Path,
    color_filter: Optional[str] = "Yellow",
    default_fps: float = 25.0,
) -> List[Marker]:
    """Read shotcut:markers:* properties from a Shotcut .mlt project file."""
    tree = ET.parse(str(mlt_path))
    root = tree.getroot()

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

    grouped: Dict[int, Dict[str, str]] = {}
    # 1. Native Shotcut nested <properties name="shotcut:markers"><properties name="0">...
    for markers_block in root.findall(".//tractor/properties[@name='shotcut:markers']"):
        for item in markers_block.findall("properties"):
            try:
                idx = int(item.attrib.get("name", len(grouped)))
            except ValueError:
                idx = len(grouped)
            entry = grouped.setdefault(idx, {})
            for prop in item.findall("property"):
                fname = prop.attrib.get("name", "")
                if fname in ("text", "start", "end", "color"):
                    entry[fname] = (prop.text or "").strip()

    # 2. Fallback for flat shotcut:markers:{n}:{field} properties
    pat = re.compile(r"^shotcut:markers:(\d+):(text|start|end|color)$")
    for prop in root.findall(".//tractor/property"):
        name = prop.attrib.get("name", "")
        m = pat.match(name)
        if m:
            idx = int(m.group(1))
            field = m.group(2)
            grouped.setdefault(idx, {})[field] = (prop.text or "").strip()

    markers: List[Marker] = []
    for idx in sorted(grouped):
        data = grouped[idx]
        color_name = hex_to_canonical_color(data.get("color", "#00aa00"))
        if color_filter and color_name.lower() != color_filter.lower():
            continue
        start_s = _parse_mlt_clock(data.get("start", "0"))
        end_s = _parse_mlt_clock(data.get("end", data.get("start", "0")))
        start_f = sec_to_frames(start_s, fps)
        end_f = sec_to_frames(end_s, fps)
        markers.append(
            Marker(
                frame=start_f,
                duration_frames=max(0, end_f - start_f),
                name=data.get("text", f"Marker {idx}"),
                color=color_name,
            )
        )

    return markers
