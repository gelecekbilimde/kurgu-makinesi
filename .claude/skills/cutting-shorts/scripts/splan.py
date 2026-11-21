"""What goes on a short's vertical timeline (pure: no Resolve calls), and how the editor's changes are kept.

shorts/plan.json is the truth:
  {"units": "frames", "shorts": {"<id>": {"timeline": uid|null, "timeline_name": str, "items": [Item, ...],
                                          "subtitles": [Cue, ...], "segments": [...]}}}
  Item = the B-roll skill's plan item (placing-b-roll/scripts/plan.py: id, row, track, start, end, file, src_in,
         src_out, kind, code, editor, deleted, uid, props, marker) plus
         "anchor": {"chapter", "ch_start", "ch_end"} | {"pieces": [...]} | null  (the chapter words the item
                   sits on; "pieces" when it crosses a join or reaches into the end card, see anchor()),
         "flag": str | null  (why the editor should look at it; a Fuchsia marker),
         "background": "black" | null  (a 16:9 full-screen picture fitted to the width: black above and below).
  Cue  = {"start", "end", "text" ("\n" between lines), "uid", "editor", "deleted", "anchor"} (+ "was": the cue
         as we placed it, on an editor-changed cue of ours).
  segments = the short_layout segments the timeline was last built with (anchors of the editor's moves).

Tracks: V1 camera, V2 full-screen B-roll + end card, V3 overlays, V4 teaser caption, V5 teaser cut-out, V6
watermark, V7 header; a chapter's editor tracks above V3 go above ours (V4 -> V8, ...).
props is what build sets right after placing (Resolve transform keys); a placed item's props are replaced by what
Resolve reads back, as in the B-roll skill. Ids are "<row>#<n>" with rows named after the role or the chapter
words, so the same desired item keeps its id from build to build.
All frames, half-open [start, end) of the short timeline."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "placing-b-roll", "scripts"))

import crop  # noqa: E402
import mapping  # noqa: E402
import plan  # noqa: E402

FIT = {"ZoomX": 1.0, "ZoomY": 1.0, "Pan": 0.0, "Tilt": 0.0}  # a 16:9 picture fits the 1080 width by default
CENTRE = crop.transform(None, 1920, 1080)  # a 16:9 picture filling the height, centred
DEFAULTS = {"ZoomX": 1.0, "ZoomY": 1.0, "Pan": 0.0, "Tilt": 0.0, "RotationAngle": 0.0, "CropLeft": 0.0,
            "CropRight": 0.0, "CropTop": 0.0, "CropBottom": 0.0, "FlipX": False, "FlipY": False}
OWN_TRACKS = {"end-card": 2, "teaser-caption": 4, "teaser-cutout": 5, "watermark": 6, "header": 7}
FULL_SCREEN = ("end-card",)
NO_MARKER = ("watermark",)  # Ruling 7: flagged by a summary line only (a marker over the whole passage is noise)
COLOR = "Fuchsia"

F_SCREENSHOT = "KAYNAK ekran görüntüsü genişliğe sığdırıldı, kontrol edin"
F_FULL = "dikey sürümü olmayan grafik genişliğe sığdırıldı (arkası siyah)"
F_OVERLAY = "dikey sürümü olmayan bindirme genişliğe sığdırıldı"
F_EDITOR_FILE = "düzenleyicinin eklediği dosya genişliğe sığdırıldı"
F_NO_SIZE = "kaynak boyutu bilinmiyor: 16:9 varsayılıp ortadan kırpıldı"
F_TRANSFORMED = "düzenleyicinin 16:9 çerçevesi taşınamaz: ortadan kırpıldı"
F_SPEED = "uzun videoda hız %{}: %100 hızla kopyalandı, kontrol edin"
F_BLEND = "uzun videodaki opaklık/karışım modu kopyalanmadı, kontrol edin"
NO_FILE = "dosyasız öğe (Text+, jeneratör, bileşik klip)"
STALE = "düzenleyici öğesinin sözleri kaydı: yerinde bırakıldı, kontrol edin"
SUBTITLES_STALE = "altyazılar değişti: eski altyazıları silip captions.srt'yi yeniden içe aktarın"


def _track(long_form_track):
    return long_form_track if long_form_track <= 3 else long_form_track + 4


def _item(row, n, track, start, end, file, src_in, kind, props, anchor, flag=None, background=None):
    return {"id": f"{row}#{n}", "row": row, "track": track, "start": start, "end": end, "file": file,
            "src_in": src_in, "src_out": src_in + end - start, "kind": kind, "code": None, "editor": False,
            "deleted": False, "uid": None, "props": dict(props), "marker": None, "anchor": anchor, "flag": flag,
            "background": background}


def _transformed(props):
    return any(props.get(k, v) != v for k, v in DEFAULTS.items())


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _lost(props):
    """Flags for what a copy can't carry from the long-form item: a speed other than 100 % (copied at 100 %),
    an opacity below 100 or a composite mode (not copied)."""
    out = []
    speed = _num(props.get("Speed"), 100.0)
    if abs(speed - 100.0) > 1e-6:
        out.append(F_SPEED.format(f"{speed:g}"))
    if _num(props.get("Opacity"), 100.0) < 100.0 - 1e-6 or _num(props.get("CompositeMode"), 0) != 0:
        out.append(F_BLEND)
    return out


def _framing(it, replace):
    """(file, kind, props, flag, background) of a copied long-form B-roll item on the vertical timeline."""
    kind, file, track = it["kind"], it["file"], _track(it["track"])
    if kind == "kaynak":
        kind = "screenshot"
    full = track == 2
    vertical = file in replace
    if vertical:
        file = replace[file]
    if _transformed(it.get("props") or {}):  # only the full-screen track fills the frame
        return file, kind, CENTRE if full and not vertical else FIT, F_TRANSFORMED, None
    if vertical:
        return file, kind, FIT, None, None
    if kind == "stock" and full:
        size = it.get("src_size")
        if size:
            return file, kind, crop.transform(None, *size), None, None
        return file, kind, CENTRE, F_NO_SIZE, None
    flag = {"screenshot": F_SCREENSHOT, "editor": F_EDITOR_FILE}.get(kind, F_FULL if full else F_OVERLAY)
    return file, kind, FIT, flag, "black" if full else None


def _camera(short_layout, crops):
    by_key = {(c["rec"], c["clip"], c["src_in"], c["src_out"]): c for c in crops.get("items", [])}
    out, count = [], {}
    for v in short_layout["v1"]:
        c = by_key.get((v["rec"], v["clip"], v["src_in"], v["src_out"]))
        if c is None:
            raise ValueError(f"crop.json'da kamera parçası yok ({v['clip']}, kare {v['rec']}): "
                             "shorts.py prepare'i yeniden çalıştırın")
        g = short_layout["segments"][v["segment"]]
        row = f"V1:{'teaser' if g['part'] == 'teaser' else 'parça'}:ch{g['chapter']}:{g['ch_start']}"
        count[row] = count.get(row, 0) + 1
        end = v["rec"] + v["src_out"] - v["src_in"]
        out.append(_item(row, count[row], 1, v["rec"], end, c["camera"], v["src_in"], "camera", c["transform"],
                         mapping.anchor_of(short_layout, v["rec"], end)))
    return out


def _broll(short_layout, replace):
    out = []
    for it in short_layout["broll"]:
        file, kind, props, flag, background = _framing(it, replace)
        flag = "; ".join([f for f in [flag] if f] + _lost(it.get("props") or {})) or None
        a = it["anchor"]
        row = f"V{_track(it['track'])}:ch{a['chapter']}:{a['ch_start']}"
        out.append(_item(row, 1, _track(it["track"]), it["rec"], it["end"], file, it["src_in"], kind, props,
                         dict(a), flag, background))
    return out


def _own(assets):
    out = []
    for n, c in enumerate(assets.get("teaser_cutout") or [], 1):
        out.append(_item("teaser-cutout", n, OWN_TRACKS["teaser-cutout"], c["rec"], c["end"], c["file"], 0,
                         "teaser-cutout", FIT, None))
    for g in assets.get("graphics") or []:
        role, (start, end) = g["role"], g["range"]
        flag = background = None
        if not g.get("vertical"):
            full = role in FULL_SCREEN
            flag, background = (F_FULL, "black") if full else (F_OVERLAY, None)
        out.append(_item(role, 1, OWN_TRACKS[role], start, end, g["file"], 0, role, FIT, None, flag, background))
    return out


def desired(short_layout, assets, crops):
    """The items the skill would place on one short. short_layout: mapping.short_layout; assets: the short's
    assets.json; crops: its crop.json. Long-form placeholders and file-less items (short_layout["skipped"]) are
    not copied."""
    return _camera(short_layout, crops) + _broll(short_layout, assets.get("replace") or {}) + _own(assets)


def marker(short_id, kind, n, start, end, name, note):
    """A Fuchsia ranged marker dict (Timeline.AddMarker(frame, color, name, note, duration, customData))."""
    data = f"short:{short_id}:{kind}" + (f":{n}" if n is not None else "")
    return {"frame": start, "color": COLOR, "name": name, "note": note, "duration": max(1, end - start),
            "customData": data}


def _rec(short_layout, chapter, s, e):
    """Short frames of chapter range [s, e) in a passage segment, or None."""
    for g in short_layout["segments"]:
        if g["part"] == "passage" and g["chapter"] == chapter and g["ch_start"] <= s and e <= g["ch_end"]:
            return g["rec"] + s - g["ch_start"], g["rec"] + e - g["ch_start"]
    return None


def merge(markers):
    """One marker per frame (Resolve refuses a second one): notes joined, the longest range and its customData."""
    by_frame = {}
    for m in markers:
        old = by_frame.get(m["frame"])
        if old is None:
            by_frame[m["frame"]] = dict(m)
            continue
        longer = m if m["duration"] > old["duration"] else old
        by_frame[m["frame"]] = dict(longer, name=f"{old['name']} + {m['name']}", note=f"{old['note']}\n{m['note']}")
    return [by_frame[f] for f in sorted(by_frame)]


def _flagged(it):
    return bool(it.get("flag")) and not it.get("editor") and not it.get("deleted")


def flag_lines(short_id, items):
    """Summary lines for every flagged item of ours (markers too, except NO_MARKER kinds: a line only)."""
    return [f"{short_id}: {it['id']} ({it['start']}-{it['end']}): {it['flag']}" for it in items if _flagged(it)]


def flags(items, short_layout, cand):
    """Fuchsia markers of one short: the teaser (ranged, with the candidate's reason: frame 0), a 1-frame marker
    at every join between pieces, every flagged item of ours (ranged over it; not the watermark, see flag_lines) and every placeholder or
    file-less item left in the chapter that was not copied (the speaker shows there)."""
    sid = cand["id"]
    t0, t1 = short_layout["teaser"]
    out = [marker(sid, "reason", None, 0, 1, "Neden", cand.get("reason") or ""),
           marker(sid, "teaser", None, t0, t1, "Teaser", "teaser: kancayı ve kesimi kontrol edin")]
    for i, g in enumerate(short_layout["segments"][1:], 1):
        out.append(marker(sid, "join", i, g["rec"], g["rec"] + 1, "Ek yeri", "ek yeri: kesimi kontrol edin"))
    n = 0
    for it in items:
        if _flagged(it) and it["kind"] not in NO_MARKER:
            n += 1
            out.append(marker(sid, "flag", n, it["start"], it["end"], "Kontrol", f"{it['id']}: {it['flag']}"))
    for n, p in enumerate(short_layout.get("skipped") or [], 1):
        rng = _rec(short_layout, p["chapter"], p["start"], p["end"])
        if rng:
            what = (f"yer tutucu vardı ({os.path.basename(p['file'])})" if p.get("file")
                    else f"{NO_FILE} vardı")
            out.append(marker(sid, "placeholder", n, *rng, "Yer tutucu" if p.get("file") else "Dosyasız öğe",
                              f"bölümde {what}: kopyalanmadı, konuşmacı görünüyor"))
    return merge(out)


def skipped_lines(short_id, short_layout):
    """'Kopyalanmayan öğeler' summary lines: the long-form placeholders and file-less items not copied."""
    return [f"{short_id}: bölüm {s['chapter']} [{s['start']}, {s['end']}) V{s['track']} "
            f"{os.path.basename(s['file']) if s.get('file') else NO_FILE}" for s in short_layout.get("skipped") or []]


def _maps(anchor, short_layout, start, end):
    """True when the anchor's words still cover exactly [start, end) of short_layout, piece after piece."""
    pos = start
    for p in anchor.get("pieces") or [anchor]:
        if "end_card" in p:
            if short_layout["end_card"][0] + p["end_card"] != pos:
                return False
            pos += p["frames"]
            continue
        for g in short_layout["segments"]:
            if (g["chapter"] == p["chapter"] and g["ch_start"] <= p["ch_start"] and p["ch_end"] <= g["ch_end"]
                    and g["rec"] + p["ch_start"] - g["ch_start"] == pos):
                pos += p["ch_end"] - p["ch_start"]
                break
        else:
            return False
    return pos == end


def stale_anchors(editor_items, new_layout):
    """Editor items (and cues) whose anchor no longer maps to their own short frames in new_layout: their words
    moved or left the short. They are reported, never moved. Deleted entries and items without anchor are not
    checked."""
    return [i for i in editor_items
            if not i.get("deleted") and i.get("anchor") and not _maps(i["anchor"], new_layout, i["start"], i["end"])]


def stale_notes(short_id, stale):
    """(markers, summary lines) for stale_anchors' result."""
    ms, lines = [], []
    for n, i in enumerate(stale, 1):
        what = i.get("id") or f"altyazı {i.get('text', '')!r}"
        ms.append(marker(short_id, "stale", n, i["start"], i["end"], "Kaydı", f"{what}: {STALE}"))
        lines.append(f"{short_id}: {what} ({i['start']}-{i['end']}): {STALE}")
    return ms, lines


def anchor(segments, start, end):
    """The words under short range [start, end): {"chapter", "ch_start", "ch_end"} inside one segment, else
    {"pieces": [...]} with one such dict per segment it crosses and {"end_card": offset, "frames": n} for a part
    over the end card (which follows the last segment). None when it covers no segment and no end card."""
    pieces, card = [], 0
    for g in segments:
        n = g["ch_end"] - g["ch_start"]
        card = max(card, g["rec"] + n)
        lo, hi = max(start, g["rec"]), min(end, g["rec"] + n)
        if lo < hi:
            pieces.append({"chapter": g["chapter"], "ch_start": g["ch_start"] + lo - g["rec"],
                           "ch_end": g["ch_start"] + hi - g["rec"]})
    if segments and end > card:
        lo = max(start, card)
        pieces.append({"end_card": lo - card, "frames": end - lo})
    if not pieces:
        return None
    return pieces[0] if len(pieces) == 1 and "chapter" in pieces[0] else {"pieces": pieces}


def readback(last, seen, segments):
    """plan.readback for a short, then anchors: an item the editor changed or added in this read-back is anchored
    to the words it now sits on under `segments` (the layout the timeline was last built with); every other item
    keeps its anchor, so an editor item whose words later move is caught by stale_anchors."""
    before = {i["id"]: i for i in last}
    out = []
    for it in plan.readback(last, seen):
        old = before.get(it["id"])
        changed = old is None or any(old.get(k) != it.get(k) for k in plan.SEEN + ("editor",))
        if it.get("editor") and not it.get("deleted") and changed:
            it = dict(it, anchor=anchor(segments, it["start"], it["end"]))
        it.setdefault("anchor", None)
        out.append(it)
    return out


def cues(assets, short_layout):
    """The short's captions as plan.json subtitle records (assets.json cues are already spelled and already
    avoid the teaser and the end card)."""
    return [{"start": c["start"], "end": c["end"], "text": c["text"], "uid": None, "editor": False,
             "deleted": False, "anchor": anchor(short_layout["segments"], c["start"], c["end"])}
            for c in assets.get("cues") or []]


def _cue_key(c):
    return c["start"], c["end"], c["text"]


def subtitle_readback(last, seen, segments, desired):
    """(keep_editor, ours). last: the plan's subtitle records; seen: the subtitle track now,
    [{uid, start, end, text}] with U+2028 between lines (GetName()); segments: the layout the timeline was last
    built with (anchors of the editor's cues); desired: this build's cues. Same rules as items:
    - a cue of ours that changed text or frames -> editor: true with the seen values ("was": as we placed it);
    - a cue of ours that is gone -> editor: true, deleted: true, uid null (never placed again);
    - a cue we didn't place -> ours when it equals a desired cue no cue of ours stands for (the editor re-imported
      captions.srt), else editor: true.
    A cue placed without a uid is matched by frames and text (and learns the uid). Editor cues are never
    rewritten; an editor-added cue that is gone again is dropped."""
    seen = [dict(s, text=s["text"].replace("\u2028", "\n")) for s in seen]
    by_uid = {s["uid"]: s for s in seen if s.get("uid") is not None}
    used, keep, ours = set(), [], []

    def take(s):
        used.add(id(s))
        return {"start": s["start"], "end": s["end"], "text": s["text"]}

    def where(c, now):
        return anchor(segments, now["start"], now["end"]) if _cue_key(now) != _cue_key(c) else c.get("anchor")

    for c in last:
        if c.get("deleted"):
            keep.append(c)
            continue
        s = by_uid.get(c["uid"]) if c.get("uid") is not None else next(
            (s for s in seen if id(s) not in used and _cue_key(s) == _cue_key(c)), None)
        if s is None or id(s) in used:
            if not c.get("editor") or "was" in c:  # ours (or ours edited earlier): remember the deletion
                was = c.get("was") or {k: c[k] for k in ("start", "end", "text")}
                keep.append(dict(c, editor=True, deleted=True, uid=None, was=was))
            continue
        now = take(s)
        if c.get("editor"):
            keep.append(dict(c, **now, uid=s["uid"], anchor=where(c, now)))
        elif _cue_key(now) != _cue_key(c):
            keep.append(dict(c, **now, uid=s["uid"], editor=True, was={k: c[k] for k in ("start", "end", "text")},
                             anchor=where(c, now)))
        else:
            ours.append(dict(c, uid=s["uid"]))
    free = [_cue_key(d) for d in desired]
    for c in ours:
        if _cue_key(c) in free:
            free.remove(_cue_key(c))
    for s in seen:
        if id(s) in used:
            continue
        rec = {"start": s["start"], "end": s["end"], "text": s["text"], "uid": s.get("uid"), "deleted": False,
               "anchor": anchor(segments, s["start"], s["end"])}
        if _cue_key(s) in free:
            free.remove(_cue_key(s))
            ours.append(dict(rec, editor=False))
        else:
            keep.append(dict(rec, editor=True))
    return keep, ours


def subtitles_stale(placed, desired):
    """True when the track no longer stands for the desired cues: a desired cue that is neither one of our
    untouched cues nor the original ("was") of a cue the editor changed or deleted, or an untouched cue of ours
    that is no longer desired. The build then asks the editor to re-import captions.srt (Resolve places cues only
    on an empty timeline and can't edit one). Editor-added cues, and editor cues whose original is no longer
    desired, don't count: they are the editor's."""
    ours = {_cue_key(c) for c in placed if not c.get("editor")}
    covered = ours | {_cue_key(c["was"]) for c in placed if c.get("editor") and c.get("was")}
    want = {_cue_key(d) for d in desired}
    return not want <= covered or not ours <= want


def subtitles_stale_note(short_id, frame=0):
    """(marker, summary line) for subtitles_stale."""
    return (marker(short_id, "subtitles", None, frame, frame + 1, "Altyazı", SUBTITLES_STALE),
            f"{short_id}: {SUBTITLES_STALE}")


def load(path):
    if not os.path.exists(path):
        return {"units": "frames", "shorts": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    plan.save(path, data)
