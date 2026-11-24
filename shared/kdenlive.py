"""Kdenlive writer (.kdenlive = MLT XML + kdenlive:* properties).

Written in Kdenlive's document version 1.04 layout (the one of Kdenlive's own tests/dataset/av.kdenlive), which
current Kdenlive upgrades when it opens the file: bin clips in `main_bin`, four track tractors (A2, A1, V1, V2)
under one main tractor, an A/V clip = a video entry on V1 + an audio entry on A1 sharing the bin id.
Chapter markers are guides: JSON in kdenlive:docproperties.guides ([{pos (frames), comment, type}]).
A/V pairs are not grouped (no `groups` property), so audio and video move independently until grouped in Kdenlive.
"""
import json
import time
import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path
from typing import List

from .timeline import Timeline

_PROFILES = {  # (w, h, fps_num, fps_den) -> Kdenlive profile file name
    (1920, 1080, 24, 1): "atsc_1080p_24", (1920, 1080, 25, 1): "atsc_1080p_25", (1920, 1080, 30, 1): "atsc_1080p_30",
    (1920, 1080, 50, 1): "atsc_1080p_50", (1920, 1080, 60, 1): "atsc_1080p_60",
    (1920, 1080, 30000, 1001): "atsc_1080p_2997", (1920, 1080, 24000, 1001): "atsc_1080p_2398",
    (1280, 720, 25, 1): "atsc_720p_25", (1280, 720, 30, 1): "atsc_720p_30", (1280, 720, 50, 1): "atsc_720p_50",
    (1280, 720, 60, 1): "atsc_720p_60",
}


def _prop(parent, name, value=None):
    e = ET.SubElement(parent, "property", name=name)
    if value is not None:
        e.text = str(value)
    return e


class _Ids:
    def __init__(self):
        self.n = {"producer": 0, "playlist": 0, "tractor": 0, "filter": 0, "transition": 0}

    def next(self, kind):
        i = self.n[kind]
        self.n[kind] += 1
        return f"{kind}{i}"


def _source_props(e, tl, f, bin_id, length, has_audio):
    for k, v in (("length", length), ("eof", "pause"), ("resource", f), ("mlt_service", "avformat-novalidate"),
                 ("seekable", 1), ("audio_index", 1 if has_audio else -1), ("video_index", 0),
                 ("mute_on_pause", 0), ("kdenlive:clip_type", 0), ("kdenlive:folderid", -1),
                 ("kdenlive:id", bin_id)):
        _prop(e, k, v)


def _audio_filters(tractor, ids):
    for svc, extra in (("volume", [("window", 75), ("max_gain", "20dB")]),
                       ("panner", [("channel", -1), ("start", 0.5)]),
                       ("audiolevel", [("iec_scale", 0), ("peak", 1)])):
        f = ET.SubElement(tractor, "filter", id=ids.next("filter"))
        for k, v in extra:
            _prop(f, k, v)
        _prop(f, "mlt_service", svc)
        if svc != "audiolevel":
            _prop(f, "internal_added", 237)
        _prop(f, "disable", 1)


def _track(root, ids, kind, entries, tl, last, mark_audio):
    """A track = two playlists in a tractor. entries: [(producer id, in frame, out frame (incl.), bin id)]."""
    p0 = ET.SubElement(root, "playlist", id=ids.next("playlist"))
    if mark_audio:
        _prop(p0, "kdenlive:audio_track", 1)
    for pid, a, b, bid in entries:
        e = ET.SubElement(p0, "entry", {"producer": pid, "in": tl.clock(a), "out": tl.clock(b)})
        _prop(e, "kdenlive:id", bid)
    p1 = ET.SubElement(root, "playlist", id=ids.next("playlist"))
    if mark_audio:
        _prop(p1, "kdenlive:audio_track", 1)
    tr = ET.SubElement(root, "tractor", {"id": ids.next("tractor"), "in": "00:00:00.000", "out": last})
    if mark_audio:
        _prop(tr, "kdenlive:audio_track", 1)
    for k, v in (("kdenlive:trackheight", 67), ("kdenlive:timeline_active", 1), ("kdenlive:collapsed", 0),
                 ("kdenlive:thumbs_format", None), ("kdenlive:audio_rec", None)):
        _prop(tr, k, v)
    hide = "video" if mark_audio else "audio"
    ET.SubElement(tr, "track", hide=hide, producer=p0.get("id"))
    ET.SubElement(tr, "track", hide=hide, producer=p1.get("id"))
    if mark_audio:
        _audio_filters(tr, ids)
    return tr.get("id")


def build(tl: Timeline) -> ET.ElementTree:
    ids = _Ids()
    total = tl.total_frames
    last = tl.clock(max(total - 1, 0))
    files = tl.unique_files()
    bin_id = {f: str(2 + i) for i, f in enumerate(files)}

    root = ET.Element("mlt", {"LC_NUMERIC": "C", "producer": "main_bin", "version": "7.7.0"})
    g = gcd(tl.width, tl.height) or 1
    ET.SubElement(root, "profile", {
        "frame_rate_num": str(tl.fps_num), "frame_rate_den": str(tl.fps_den), "width": str(tl.width),
        "height": str(tl.height), "progressive": "1", "sample_aspect_num": "1", "sample_aspect_den": "1",
        "display_aspect_num": str(tl.width // g), "display_aspect_den": str(tl.height // g), "colorspace": "709",
        "description": f"{tl.width}x{tl.height} {float(tl.fps):g} fps"})

    # bin clips
    bin_producers = []
    for f in files:
        c0 = next(c for c in tl.clips if c.file == f)
        length = tl.frames(c0.src_duration) if c0.src_duration else max(
            tl.frames(c.src_out) for c in tl.clips if c.file == f)
        pid = ids.next("producer")
        e = ET.SubElement(root, "producer", {"id": pid, "in": "00:00:00.000", "out": tl.clock(max(length - 1, 0))})
        _source_props(e, tl, f, bin_id[f], length, c0.has_audio)
        _prop(e, "kdenlive:clipname", c0.name)
        bin_producers.append((pid, length))

    main = ET.SubElement(root, "playlist", id="main_bin")
    doc = {"activeTrack": 2, "audioChannels": 2, "audioTarget": 1, "disablepreview": 0,
           "documentid": int(time.time() * 1000), "enableTimelineZone": 0, "enableexternalproxy": 0,
           "enableproxy": 0, "generateimageproxy": 0, "generateproxy": 0, "kdenliveversion": "23.04.3",
           "position": 0, "profile": _PROFILES.get((tl.width, tl.height, tl.fps_num, tl.fps_den), ""),
           "scrollPos": 0, "version": "1.04", "verticalzoom": 1, "videoTarget": 2, "zonein": 0,
           "zoneout": min(75, max(total - 1, 0)), "zoom": 8}
    for k, v in doc.items():
        _prop(main, f"kdenlive:docproperties.{k}", v)
    _prop(main, "kdenlive:expandedFolders")
    _prop(main, "kdenlive:documentnotes")
    guides = [{"pos": m.frame, "comment": m.text, "type": 0} for m in tl.markers()]
    if guides:
        _prop(main, "kdenlive:docproperties.guides", json.dumps(guides, indent=4, ensure_ascii=False) + "\n")
    _prop(main, "xml_retain", 1)
    for pid, length in bin_producers:
        ET.SubElement(main, "entry", {"producer": pid, "in": "00:00:00.000", "out": tl.clock(max(length - 1, 0))})

    black = ET.SubElement(root, "producer", {"id": "black_track", "in": "00:00:00.000", "out": last})
    for k, v in (("length", 2147483647), ("eof", "continue"), ("resource", "black"), ("aspect_ratio", 1),
                 ("mlt_service", "color"), ("mlt_image_format", "rgba"), ("set.test_audio", 0)):
        _prop(black, k, v)

    # per-clip producers (one for the video entry, one for the audio entry)
    lay = tl.layout()
    video_entries, audio_entries = [], []
    for p in lay:
        c = p.clip
        length = tl.frames(c.src_duration) if c.src_duration else tl.frames(c.src_out)
        bid = bin_id[c.file]
        for kind, store in (("video", video_entries), ("audio", audio_entries)):
            if kind == "audio" and not c.has_audio:
                continue
            pid = ids.next("producer")
            e = ET.Element("producer", {"id": pid, "in": "00:00:00.000", "out": tl.clock(max(length - 1, 0))})
            _source_props(e, tl, c.file, bid, length, c.has_audio)
            _prop(e, "set.test_audio", 1 if kind == "video" else 0)
            _prop(e, "set.test_image", 1 if kind == "audio" else 0)
            root.insert(list(root).index(black) + 1 + len(video_entries) + len(audio_entries), e)
            store.append((pid, p.src_in, p.src_out - 1, bid))

    # tracks bottom -> top: A2, A1, V1, V2
    t_a2 = _track(root, ids, "audio", [], tl, last, True)
    t_a1 = _track(root, ids, "audio", audio_entries, tl, last, True)
    t_v1 = _track(root, ids, "video", video_entries, tl, last, False)
    t_v2 = _track(root, ids, "video", [], tl, last, False)

    main_tr = ET.SubElement(root, "tractor", {"id": ids.next("tractor"), "in": "00:00:00.000", "out": last})
    ET.SubElement(main_tr, "track", producer="black_track")
    for t in (t_a2, t_a1, t_v1, t_v2):
        ET.SubElement(main_tr, "track", producer=t)
    for b in (1, 2):
        t = ET.SubElement(main_tr, "transition", id=ids.next("transition"))
        for k, v in (("a_track", 0), ("b_track", b), ("mlt_service", "mix"), ("kdenlive_id", "mix"),
                     ("internal_added", 237), ("always_active", 1), ("accepts_blanks", 1), ("sum", 1)):
            _prop(t, k, v)
    for b in (3, 4):
        t = ET.SubElement(main_tr, "transition", id=ids.next("transition"))
        for k, v in (("a_track", 0), ("b_track", b), ("version", "0.1"), ("mlt_service", "frei0r.cairoblend"),
                     ("kdenlive_id", "frei0r.cairoblend"), ("internal_added", 237), ("always_active", 1)):
            _prop(t, k, v)
    _audio_filters(main_tr, ids)
    return ET.ElementTree(root)


def write(tl: Timeline, out_dir: str) -> List[Path]:
    """Write <out_dir>/<name>.kdenlive -> [path]"""
    name = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in tl.name).strip() or "project"
    path = Path(out_dir) / f"{name}.kdenlive"
    tree = build(tl)
    ET.indent(tree, space=" ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return [path]
