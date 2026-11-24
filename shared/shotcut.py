"""Shotcut writer: a Shotcut project is an MLT XML file (.mlt).

Layout follows what Shotcut itself saves: black background track + one video playlist (V1) in a tractor with
mix/cairoblend transitions. Chapter markers go on the tractor as shotcut:markers:N:{text,start,end,color}
(see Shotcut src/models/markersmodel.cpp). Clips with audio carry it on the same playlist entry.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from .timeline import Timeline

MARKER_COLOR = "#00aa00"


def _prop(parent, name, value):
    e = ET.SubElement(parent, "property", name=name)
    e.text = str(value)
    return e


def _dar(w, h):
    from math import gcd
    g = gcd(w, h) or 1
    return w // g, h // g


def build(tl: Timeline) -> ET.ElementTree:
    total = tl.total_frames
    last = tl.clock(max(total - 1, 0))
    root = ET.Element("mlt", {"LC_NUMERIC": "C", "version": "7.22.0", "title": "Shotcut version 24.04.28",
                              "producer": "main_bin"})
    dn, dd = _dar(tl.width, tl.height)
    ET.SubElement(root, "profile", {
        "description": "automatic", "width": str(tl.width), "height": str(tl.height), "progressive": "1",
        "sample_aspect_num": "1", "sample_aspect_den": "1", "display_aspect_num": str(dn),
        "display_aspect_den": str(dd), "frame_rate_num": str(tl.fps_num), "frame_rate_den": str(tl.fps_den),
        "colorspace": "709"})
    main = ET.SubElement(root, "playlist", id="main_bin")
    _prop(main, "xml_retain", 1)

    black = ET.SubElement(root, "producer", {"id": "black", "in": "00:00:00.000", "out": last})
    for k, v in (("length", total), ("eof", "pause"), ("resource", "0"), ("aspect_ratio", "1"),
                 ("mlt_service", "color"), ("mlt_image_format", "yuv422"), ("set.test_audio", "0")):
        _prop(black, k, v)
    bg = ET.SubElement(root, "playlist", id="background")
    ET.SubElement(bg, "entry", {"producer": "black", "in": "00:00:00.000", "out": last})

    # one chain per source file, one playlist entry per clip
    chain_ids = {}
    for i, f in enumerate(tl.unique_files()):
        cid = f"chain{i}"
        chain_ids[f] = cid
        c0 = next(c for c in tl.clips if c.file == f)
        length = tl.frames(c0.src_duration) if c0.src_duration else max(
            tl.frames(c.src_out) for c in tl.clips if c.file == f)
        ch = ET.SubElement(root, "chain", {"id": cid, "out": tl.clock(max(length - 1, 0))})
        for k, v in (("length", length), ("eof", "pause"), ("resource", f), ("mlt_service", "avformat-novalidate"),
                     ("seekable", 1), ("audio_index", 1 if c0.has_audio else -1), ("video_index", 0),
                     ("mute_on_pause", 0), ("shotcut:caption", Path(f).name), ("xml", "was here")):
            _prop(ch, k, v)

    pl = ET.SubElement(root, "playlist", id="playlist0")
    _prop(pl, "shotcut:video", 1)
    _prop(pl, "shotcut:name", "V1")
    for p in tl.layout():
        e = ET.SubElement(pl, "entry", {"producer": chain_ids[p.clip.file], "in": tl.clock(p.src_in),
                                        "out": tl.clock(p.src_out - 1)})
        if p.clip.name:
            _prop(e, "shotcut:caption", p.clip.name)

    tr = ET.SubElement(root, "tractor", {"id": "tractor0", "title": tl.name, "in": "00:00:00.000", "out": last})
    for k, v in (("shotcut", 1), ("shotcut:projectAudioChannels", 2), ("shotcut:projectFolder", 0)):
        _prop(tr, k, v)
    for n, m in enumerate(tl.markers()):
        _prop(tr, f"shotcut:markers:{n}:text", m.text)
        _prop(tr, f"shotcut:markers:{n}:start", tl.clock(m.frame))
        _prop(tr, f"shotcut:markers:{n}:end", tl.clock(m.frame))
        _prop(tr, f"shotcut:markers:{n}:color", MARKER_COLOR)
    ET.SubElement(tr, "track", producer="background")
    ET.SubElement(tr, "track", producer="playlist0")
    ET.SubElement(tr, "transition", {"id": "transition0", "mlt_service": "mix", "a_track": "0", "b_track": "1",
                                     "always_active": "1", "sum": "1"})
    ET.SubElement(tr, "transition", {"id": "transition1", "mlt_service": "frei0r.cairoblend", "a_track": "0",
                                     "b_track": "1", "version": "0.1", "threads": "0"})
    return ET.ElementTree(root)


def write(tl: Timeline, out_dir: str) -> List[Path]:
    """Write <out_dir>/<name>.mlt -> [path]"""
    path = Path(out_dir) / f"{_safe(tl.name)}.mlt"
    tree = build(tl)
    ET.indent(tree, space=" ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return [path]


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in name).strip() or "project"
