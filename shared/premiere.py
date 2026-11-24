"""Adobe Premiere Pro writer: Final Cut Pro 7 XML (xmeml v4), which Premiere imports via File > Import.

(A native .prproj is an undocumented gzipped XML that changes between versions; xmeml is the supported
interchange route.) One video track + one stereo audio track pair per clip, linked as Premiere expects;
chapters become sequence markers. Times are in frames of the sequence timebase.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List
from urllib.parse import quote

from .timeline import Timeline


def _t(parent, tag, text=None, **attrs):
    e = ET.SubElement(parent, tag, **{k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def _rate(parent, tl):
    """xmeml rate: integer timebase + ntsc flag (29.97 = timebase 30, ntsc TRUE)."""
    r = _t(parent, "rate")
    ntsc = tl.fps_den == 1001
    _t(r, "timebase", round(tl.fps_num / tl.fps_den))
    _t(r, "ntsc", "TRUE" if ntsc else "FALSE")
    return r


def _pathurl(path: str) -> str:
    p = Path(path).as_posix()
    if not p.startswith("/"):          # Windows drive path
        p = "/" + p
    return "file://localhost" + quote(p, safe="/:")


def _file_el(parent, tl, fid, clip, full: bool):
    f = _t(parent, "file", id=fid)
    if not full:
        return f
    _t(f, "name", Path(clip.file).name)
    _t(f, "pathurl", _pathurl(clip.file))
    _rate(f, tl)
    dur = tl.frames(clip.src_duration) if clip.src_duration else tl.frames(clip.src_out)
    _t(f, "duration", dur)
    media = _t(f, "media")
    v = _t(media, "video")
    sc = _t(v, "samplecharacteristics")
    _rate(sc, tl)
    _t(sc, "width", tl.width)
    _t(sc, "height", tl.height)
    if clip.has_audio:
        a = _t(media, "audio")
        sca = _t(a, "samplecharacteristics")
        _t(sca, "depth", 16)
        _t(sca, "samplerate", 48000)
        _t(a, "channelcount", 2)
    return f


def build(tl: Timeline) -> ET.ElementTree:
    total = tl.total_frames
    root = ET.Element("xmeml", version="4")
    seq = _t(root, "sequence", id="sequence-1")
    _t(seq, "name", tl.name)
    _t(seq, "duration", total)
    _rate(seq, tl)
    tc = _t(seq, "timecode")
    _rate(tc, tl)
    _t(tc, "string", "00:00:00:00")
    _t(tc, "frame", 0)
    _t(tc, "displayformat", "NDF")
    media = _t(seq, "media")

    video = _t(media, "video")
    vf = _t(video, "format")
    sc = _t(vf, "samplecharacteristics")
    _rate(sc, tl)
    _t(sc, "width", tl.width)
    _t(sc, "height", tl.height)
    _t(sc, "anamorphic", "FALSE")
    _t(sc, "pixelaspectratio", "square")
    _t(sc, "fielddominance", "none")
    vtrack = _t(video, "track")

    audio = _t(media, "audio")
    _t(audio, "numOutputChannels", 2)
    af = _t(audio, "format")
    asc = _t(af, "samplecharacteristics")
    _t(asc, "depth", 16)
    _t(asc, "samplerate", 48000)
    atracks = [_t(audio, "track"), _t(audio, "track")]   # L and R of the stereo pair

    file_ids = {}
    for i, p in enumerate(tl.layout(), 1):
        c = p.clip
        first = c.file not in file_ids
        fid = file_ids.setdefault(c.file, f"file-{len(file_ids) + 1}")
        src_total = tl.frames(c.src_duration) if c.src_duration else tl.frames(c.src_out)
        # ids: video = 3i-2, audio L = 3i-1, audio R = 3i
        slots = [("video", 1, vtrack, f"clipitem-{3 * i - 2}")]
        if c.has_audio:
            slots += [("audio", 1, atracks[0], f"clipitem-{3 * i - 1}"), ("audio", 2, atracks[1], f"clipitem-{3 * i}")]
        for mediatype, tindex, track, cid in slots:
            ci = _t(track, "clipitem", id=cid)
            _t(ci, "name", c.name)
            _t(ci, "enabled", "TRUE")
            _t(ci, "duration", src_total)
            _rate(ci, tl)
            _t(ci, "start", p.start)
            _t(ci, "end", p.end)
            _t(ci, "in", p.src_in)
            _t(ci, "out", p.src_out)
            _file_el(ci, tl, fid, c, full=first and mediatype == "video")
            st = _t(ci, "sourcetrack")
            _t(st, "mediatype", mediatype)
            _t(st, "trackindex", tindex)
            if c.has_audio:   # every item of the A/V pair links to all of the pair, so Premiere keeps them together
                for rmt, rti, rtrack, rcid in slots:
                    ln = _t(ci, "link")
                    _t(ln, "linkclipref", rcid)
                    _t(ln, "mediatype", rmt)
                    _t(ln, "trackindex", rti)
                    _t(ln, "clipindex", i)

    for m in tl.markers():
        mk = _t(seq, "marker")
        _t(mk, "name", m.text)
        _t(mk, "comment", "")
        _t(mk, "in", m.frame)
        _t(mk, "out", -1)
    return ET.ElementTree(root)


def write(tl: Timeline, out_dir: str) -> List[Path]:
    """Write <out_dir>/<name>.xml (xmeml) -> [path]"""
    name = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in tl.name).strip() or "project"
    path = Path(out_dir) / f"{name}.xml"
    tree = build(tl)
    ET.indent(tree, space="  ")
    body = ET.tostring(tree.getroot(), encoding="unicode")
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body + "\n", encoding="utf-8")
    return [path]
