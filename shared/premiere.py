"""Adobe Premiere Pro (FCP7 XML / xmeml v4) writer and marker reader for Kurgu Makinesi.

Features:
- Multi-track sequence: V1 (A-roll), V2 (B-roll), V3 (Overlays / Graphics),
  A1/A2 (Camera Audio, linked to V1 via <link>), A3/A4 (External Synced WAV)
- Color-coded point and range <marker> elements with Premiere <pproColor> tags
- Vertical Shorts (1080x1920) with Basic Motion scale/center filter for face crop
  and sidecar .srt captions
- Round-trip marker readback (read_premiere_markers)
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
from xml.dom import minidom

from .timeline import (
    MARKER_COLORS,
    CropRect,
    Marker,
    Timeline,
    write_srt,
)

# Reverse map Premiere pproColor ARGB int -> canonical color name
_PPRO_TO_COLOR: Dict[int, str] = {
    4282339765: "Yellow",
    4281740498: "Green",
    4281049552: "Red",
    4289825711: "Purple",
    4294741314: "Sky",
}


def _sub(parent: ET.Element, tag: str, text: Optional[str] = None, attrib: Optional[Dict[str, str]] = None) -> ET.Element:
    el = ET.SubElement(parent, tag, attrib or {})
    if text is not None:
        el.text = str(text)
    return el


def _file_url(path: str) -> str:
    resolved = str(Path(path).resolve()) if Path(path).exists() else path
    if not resolved.startswith("/"):
        resolved = "/" + resolved
    return "file://localhost" + urllib.parse.quote(resolved, safe="/:")


def _add_rate(parent: ET.Element, timebase: int, ntsc: bool = False) -> ET.Element:
    rate = _sub(parent, "rate")
    _sub(rate, "timebase", str(timebase))
    _sub(rate, "ntsc", "TRUE" if ntsc else "FALSE")
    return rate


def _add_motion_filter(clipitem: ET.Element, crop: CropRect) -> None:
    """Attach FCP7 Basic Motion filter for Premiere Pro vertical face cropping."""
    flt = _sub(clipitem, "filter")
    eff = _sub(flt, "effect")
    _sub(eff, "name", "Basic Motion")
    _sub(eff, "effectid", "basic")
    _sub(eff, "effectcategory", "motion")
    _sub(eff, "effecttype", "motion")
    _sub(eff, "mediatype", "video")

    p_scale = _sub(eff, "parameter")
    _sub(p_scale, "parameterid", "scale")
    _sub(p_scale, "name", "Scale")
    _sub(p_scale, "value", f"{crop.scale * 100.0:.2f}")

    # FCP7 center parameter is normalized offset from center (-0.5 .. +0.5)
    horiz = -(crop.center_x - 0.5)
    vert = -(crop.center_y - 0.5)
    p_center = _sub(eff, "parameter")
    _sub(p_center, "parameterid", "center")
    _sub(p_center, "name", "Center")
    val = _sub(p_center, "value")
    _sub(val, "horiz", f"{horiz:.4f}")
    _sub(val, "vert", f"{vert:.4f}")


def _prettify_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(raw)
    return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def write_premiere(timeline: Timeline, output_dir: str | Path) -> Path:
    """Write a Premiere Pro-compatible FCP7 XML (.xml) sequence (plus .srt if captions exist)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timeline.name}.xml"

    placed_v1, placed_a2, placed_ov, markers, total_frames = timeline.layout()
    timebase = int(round(timeline.fps))
    ntsc = any(abs(timeline.fps - rate) < 0.05 for rate in (23.976, 29.97, 59.94))

    xmeml = ET.Element("xmeml", {"version": "4"})
    seq = _sub(xmeml, "sequence", attrib={"id": "sequence-1"})
    _sub(seq, "name", timeline.name)
    _sub(seq, "duration", str(total_frames))
    _add_rate(seq, timebase, ntsc)

    tc = _sub(seq, "timecode")
    _add_rate(tc, timebase, ntsc)
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "frame", "0")
    _sub(tc, "displayformat", "NDF")

    media = _sub(seq, "media")
    video = _sub(media, "video")
    v_fmt = _sub(video, "format")
    v_sc = _sub(v_fmt, "samplecharacteristics")
    _add_rate(v_sc, timebase, ntsc)
    _sub(v_sc, "width", str(timeline.width))
    _sub(v_sc, "height", str(timeline.height))
    _sub(v_sc, "anamorphic", "FALSE")
    _sub(v_sc, "pixelaspectratio", "square")
    _sub(v_sc, "fielddominance", "none")

    audio = _sub(media, "audio")
    a_fmt = _sub(audio, "format")
    a_sc = _sub(a_fmt, "samplecharacteristics")
    _sub(a_sc, "depth", "16")
    _sub(a_sc, "samplerate", "48000")

    # Video tracks: V1 (A-roll), V2 (B-roll), V3 (Overlays)
    vtrack1 = _sub(video, "track")
    vtrack2 = _sub(video, "track")
    vtrack3 = _sub(video, "track")

    # Audio tracks: A1/A2 (Camera L/R), A3/A4 (External WAV L/R)
    atrack1 = _sub(audio, "track")
    atrack2 = _sub(audio, "track")
    atrack3 = _sub(audio, "track")
    atrack4 = _sub(audio, "track")

    file_ids: Dict[str, str] = {}
    defined_files: set[str] = set()

    def attach_file_element(parent: ET.Element, src_path: str, duration_f: int, has_video: bool, has_audio: bool, sample_rate: int = 48000) -> str:
        if src_path not in file_ids:
            file_ids[src_path] = f"file-{len(file_ids) + 1}"
        fid = file_ids[src_path]
        if fid in defined_files:
            _sub(parent, "file", attrib={"id": fid})
            return fid

        defined_files.add(fid)
        fel = _sub(parent, "file", attrib={"id": fid})
        _sub(fel, "name", Path(src_path).name)
        _sub(fel, "pathurl", _file_url(src_path))
        _add_rate(fel, timebase, ntsc)
        _sub(fel, "duration", str(max(duration_f, 1)))
        f_media = _sub(fel, "media")
        if has_video:
            fv = _sub(f_media, "video")
            fsc = _sub(fv, "samplecharacteristics")
            _add_rate(fsc, timebase, ntsc)
            _sub(fsc, "width", str(timeline.width))
            _sub(fsc, "height", str(timeline.height))
        if has_audio:
            fa = _sub(f_media, "audio")
            asc = _sub(fa, "samplecharacteristics")
            _sub(asc, "depth", "16")
            _sub(asc, "samplerate", str(sample_rate))
            _sub(fa, "channelcount", "2")
        return fid

    clip_counter = 0

    # Populate V1 + linked A1/A2 (Camera Audio)
    for pc in placed_v1:
        clip_counter += 1
        v_id = f"clipitem-v1-{clip_counter}"
        a1_id = f"clipitem-a1-{clip_counter}"
        a2_id = f"clipitem-a2-{clip_counter}"
        has_cam_audio = pc.media.has_audio and not pc.clip.mute_camera_audio

        vci = _sub(vtrack1, "clipitem", attrib={"id": v_id})
        _sub(vci, "name", pc.clip.label or Path(pc.clip.file).name)
        _sub(vci, "enabled", "TRUE")
        _sub(vci, "duration", str(pc.duration_frames))
        _add_rate(vci, timebase, ntsc)
        _sub(vci, "start", str(pc.timeline_start))
        _sub(vci, "end", str(pc.timeline_end))
        _sub(vci, "in", str(pc.in_frame))
        _sub(vci, "out", str(pc.in_frame + pc.duration_frames))
        attach_file_element(
            vci,
            pc.clip.file,
            pc.in_frame + pc.duration_frames,
            has_video=True,
            has_audio=pc.media.has_audio,
            sample_rate=pc.media.audio_sample_rate,
        )
        if pc.clip.crop is not None:
            _add_motion_filter(vci, pc.clip.crop)

        if has_cam_audio:
            # Link V1 -> A1 & A2
            for link_ref, mtype, tidx, gidx in (
                (v_id, "video", 1, 1),
                (a1_id, "audio", 1, 1),
                (a2_id, "audio", 2, 1),
            ):
                lnk = _sub(vci, "link")
                _sub(lnk, "linkclipref", link_ref)
                _sub(lnk, "mediatype", mtype)
                _sub(lnk, "trackindex", str(tidx))
                _sub(lnk, "clipindex", str(pc.index + 1))
                _sub(lnk, "groupindex", str(gidx))

            for ch_idx, (atrack, aid) in enumerate(((atrack1, a1_id), (atrack2, a2_id)), start=1):
                aci = _sub(atrack, "clipitem", attrib={"id": aid})
                _sub(aci, "name", pc.clip.label or Path(pc.clip.file).name)
                _sub(aci, "enabled", "TRUE")
                _sub(aci, "duration", str(pc.duration_frames))
                _add_rate(aci, timebase, ntsc)
                _sub(aci, "start", str(pc.timeline_start))
                _sub(aci, "end", str(pc.timeline_end))
                _sub(aci, "in", str(pc.in_frame))
                _sub(aci, "out", str(pc.in_frame + pc.duration_frames))
                attach_file_element(
                    aci,
                    pc.clip.file,
                    pc.in_frame + pc.duration_frames,
                    has_video=True,
                    has_audio=True,
                    sample_rate=pc.media.audio_sample_rate,
                )
                st = _sub(aci, "sourcetrack")
                _sub(st, "mediatype", "audio")
                _sub(st, "trackindex", str(ch_idx))
                for link_ref, mtype, tidx in ((v_id, "video", 1), (a1_id, "audio", 1), (a2_id, "audio", 2)):
                    lnk = _sub(aci, "link")
                    _sub(lnk, "linkclipref", link_ref)
                    _sub(lnk, "mediatype", mtype)
                    _sub(lnk, "trackindex", str(tidx))
                    _sub(lnk, "clipindex", str(pc.index + 1))

    # Populate A3/A4 (External Synced WAV)
    for idx, ac in enumerate(placed_a2, start=1):
        for ch_idx, atrack in enumerate((atrack3, atrack4), start=1):
            aci = _sub(atrack, "clipitem", attrib={"id": f"clipitem-wav-{idx}-ch{ch_idx}"})
            _sub(aci, "name", ac.label or Path(ac.file).name)
            _sub(aci, "enabled", "TRUE")
            _sub(aci, "duration", str(ac.duration_frames))
            _add_rate(aci, timebase, ntsc)
            _sub(aci, "start", str(ac.timeline_start))
            _sub(aci, "end", str(ac.timeline_end))
            _sub(aci, "in", str(ac.in_frame))
            _sub(aci, "out", str(ac.in_frame + ac.duration_frames))
            attach_file_element(
                aci, ac.file, ac.in_frame + ac.duration_frames, has_video=False, has_audio=True
            )
            st = _sub(aci, "sourcetrack")
            _sub(st, "mediatype", "audio")
            _sub(st, "trackindex", str(ch_idx))

    # Populate V2 (B-roll) and V3 (Overlays/Graphics)
    for idx, ov in enumerate(placed_ov, start=1):
        target_track = vtrack2 if ov.overlay.track <= 2 else vtrack3
        vci = _sub(target_track, "clipitem", attrib={"id": f"clipitem-ov-{idx}"})
        _sub(vci, "name", ov.overlay.label or f"[{ov.overlay.kind}] {Path(ov.overlay.file).name}")
        _sub(vci, "enabled", "TRUE")
        _sub(vci, "duration", str(ov.duration_frames))
        _add_rate(vci, timebase, ntsc)
        _sub(vci, "start", str(ov.timeline_start))
        _sub(vci, "end", str(ov.timeline_end))
        _sub(vci, "in", str(ov.in_frame))
        _sub(vci, "out", str(ov.in_frame + ov.duration_frames))
        attach_file_element(
            vci,
            ov.overlay.file,
            ov.in_frame + ov.duration_frames,
            has_video=True,
            has_audio=not ov.overlay.mute_audio,
        )
        if ov.overlay.crop is not None:
            _add_motion_filter(vci, ov.overlay.crop)

    # Sequence-level color-coded point & range markers
    for m in markers:
        _, _, ppro_color = MARKER_COLORS.get(m.color, MARKER_COLORS["Green"])
        mel = _sub(seq, "marker")
        _sub(mel, "name", m.name)
        comment_text = f"[{m.color}] {m.note}".strip() if m.note else f"[{m.color}]"
        _sub(mel, "comment", comment_text)
        _sub(mel, "in", str(m.frame))
        _sub(mel, "out", str(m.end_frame) if m.duration_frames > 0 else "-1")
        _sub(mel, "pproColor", str(ppro_color))

    # Optional sidecar SRT captions
    if timeline.captions:
        write_srt(timeline.captions, out_dir / f"{timeline.name}.srt")

    out_path.write_text(_prettify_xml(xmeml), encoding="utf-8")
    return out_path


def read_premiere_markers(
    xml_path: str | Path,
    color_filter: Optional[str] = "Yellow",
) -> List[Marker]:
    """Read sequence <marker> elements from an exported Premiere Pro FCP7 XML file."""
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    markers: List[Marker] = []
    for mel in root.findall(".//sequence/marker"):
        name = (mel.findtext("name") or "").strip()
        comment = (mel.findtext("comment") or "").strip()
        in_f = int(mel.findtext("in") or 0)
        out_raw = int(mel.findtext("out") or -1)
        ppro_raw = mel.findtext("pproColor")

        color_name = "Green"
        if ppro_raw is not None:
            try:
                color_name = _PPRO_TO_COLOR.get(int(ppro_raw), "Green")
            except ValueError:
                pass
        # Allow explicit [Color] tag in comment to refine color name
        for cname in MARKER_COLORS:
            if f"[{cname}]".lower() in comment.lower():
                color_name = cname
                break

        if color_filter and color_name.lower() != color_filter.lower():
            continue

        dur_f = max(0, out_raw - in_f) if out_raw > in_f else 0
        markers.append(
            Marker(
                frame=in_f,
                duration_frames=dur_f,
                name=name or "Premiere Marker",
                color=color_name,
                note=comment,
            )
        )

    return markers
