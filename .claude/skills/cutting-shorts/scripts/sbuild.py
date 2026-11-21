"""One short's vertical timeline brought in line with its plan, through duck-typed Resolve objects (tests drive the
pure parts with fakes; shorts_resolve.py build passes the real API).

Rules (the B-roll skill's sync.py, reference.md of both skills):
- every setter runs on a timeline whose name is one of ours ("<prefix> short <rank> ..."), checked right before
  (assert_ours); long-form timelines are only read;
- remove before add; what was placed is found by diffing the uids of every video track, never trusted from a
  return value; the plan is saved after the removes and after every placement;
- camera items (V1) are appended with their audio (the chapter's audio is the camera clip's, with the recorder
  WAV linked to it); everything else video only (mediaType 1);
- transforms are set right after placing (ZoomX, ZoomY, Pan, Tilt) and read back;
- an item of ours that would land on a kept item (the editor's, or one that couldn't be deleted) is not placed.
"""
import hashlib
import os
import re
import subprocess

import build as glue
import plan
import splan
import sync

TRANSFORM = ("ZoomX", "ZoomY", "Pan", "Tilt")  # Zoom before Pan/Tilt: ZoomGang couples X and Y
TOL = 1e-3
WITH_AUDIO = ("camera",)
STILL_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
W, H = 1080, 1920


class NotOurs(Exception):
    """A setter was about to run on a timeline that is not a short of ours."""


def is_ours(name, prefix):
    return bool(re.fullmatch(rf"{re.escape(prefix)} short \d+( .*)?", name or "", flags=re.S))


def assert_ours(tl, prefix):
    name = tl.GetName()
    if not is_ours(name, prefix):
        raise NotOurs(f"'{name}' bir short zaman çizelgesi değil: dokunulmadı, durduruldu")


def rename_to(current, want, prefix):
    """The new name when rank/title changed (None when it didn't); raises NotOurs unless both names are ours."""
    for n in (current, want):
        if not is_ours(n, prefix):
            raise NotOurs(f"'{n}' bir short zaman çizelgesi adı değil: yeniden adlandırılmadı")
    return want if current != want else None


def todo(candidates, ids, eligible):
    """(candidates to build, summary lines, bad): accepted, not frozen, every chapter signed off. ids: only these
    (a named one that can't be built is reported; unnamed, not accepted ones are skipped silently)."""
    by_id = {c.get("id"): c for c in candidates}
    lines, out = [], []
    bad = [i for i in ids if i not in by_id]
    if bad:
        lines.append(f"Bilinmeyen aday: {', '.join(bad)}")
    for c in [by_id[i] for i in ids if i in by_id] if ids else candidates:
        if c.get("accepted") and not c.get("frozen") and not c.get("teaser"):
            lines.append(f"{c['id']}: teaser yok: önce check, kurulmadı")
            bad.append(c["id"])
        elif c.get("frozen"):
            lines.append(f"{c['id']}: dondurulmuş, atlandı")
        elif not c.get("accepted"):
            if ids:
                lines.append(f"{c['id']}: kabul edilmemiş (inceleme zaman çizelgesinde yeşil değil)")
                bad.append(c["id"])
        elif any(r["chapter"] not in eligible for r in c.get("pieces", []) + [c.get("teaser") or {}]):
            lines.append(f"{c['id']}: imzalı olmayan bölüm kullanıyor (A-roll ve B-roll dondurulmuş olmalı), "
                         "kurulmadı")
            bad.append(c["id"])
        else:
            out.append(c)
    return out, lines, bool(bad)


def _is_still_file(path):
    return os.path.splitext(path or "")[1].lower() in STILL_EXT


def still_range(item):
    """A still plays [0, length) whatever part of it the long-form item showed (Resolve reads a still that way)."""
    if not _is_still_file(item.get("file")) or item.get("src_in") == 0:
        return item
    return dict(item, src_in=0, src_out=item["end"] - item["start"])


def append_spec(item, mpi, s0, still, ratio=1.0):
    """AppendToTimeline clip info: the B-roll skill's (video only, absolute record frame, exclusive end); a camera
    item keeps its audio."""
    spec = glue.append_spec(item, mpi, s0, still, ratio)
    if item.get("kind") in WITH_AUDIO:
        spec.pop("mediaType")
    return spec


def transform_calls(props):
    """[(key, value)] to SetProperty, in order."""
    return [(k, props[k]) for k in TRANSFORM if k in (props or {})]


def transform_differs(want, got):
    return any(not isinstance(got.get(k), (int, float)) or abs(got[k] - v) > TOL for k, v in transform_calls(want))


def apply_transform(it, props, item_id):
    """SetProperty each transform key, then read them back -> problems."""
    probs = []
    for k, v in transform_calls(props):
        if not it.SetProperty(k, v):
            probs.append(f"{item_id}: {k} = {v} ayarlanamadı")
    got = it.GetProperty() or {}
    bad = [k for k, v in transform_calls(props) if not isinstance(got.get(k), (int, float)) or abs(got[k] - v) > TOL]
    if bad:
        probs.append(f"{item_id}: dönüşüm okunduğunda farklı ({', '.join(f'{k} {props[k]} -> {got.get(k)}' for k in bad)})")
    return probs


def collides(item, items):
    """The first kept item (on the timeline: has a uid) item would land on, or None."""
    return next((i for i in items if i.get("uid") is not None and not i.get("deleted") and i["track"] == item["track"]
                 and i["start"] < item["end"] and item["start"] < i["end"]), None)


def _pad_cmd(src, out):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"
    if _is_still_file(src):
        return ["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf, "-frames:v", "1", out]
    return ["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf, "-an", "-c:v", "libx264", "-crf", "14",
            "-preset", "fast", "-pix_fmt", "yuv420p", out]


def _pad_name(src):
    """'<stem>-<hash>-siyah.<png|mp4>': the hash covers the canonical source path, its size and mtime, so a
    re-rendered source (same path) or a same-named file elsewhere gets its own copy. None when src is missing."""
    try:
        st = os.stat(src)
    except OSError:
        return None
    key = f"{glue.canon(src)}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")
    stem = os.path.splitext(os.path.basename(src))[0]
    return f"{stem}-{hashlib.sha1(key).hexdigest()[:8]}-siyah{'.png' if _is_still_file(src) else '.mp4'}"


def black_backgrounds(items, out_dir, runner=subprocess.run):
    """Items with background "black" -> (items, problems): the picture padded to 1080x1920 with black (FFmpeg,
    made once per source version in out_dir, written to a temp file and moved in place only on success) replaces
    the file; frames, props and flag stay. The track below a V2 item is the camera, so the black is part of the
    picture instead of an item of its own."""
    out, probs = [], []
    for it in items:
        if it.get("background") != "black" or not it.get("file"):
            out.append(it)
            continue
        name = _pad_name(it["file"])
        if name is None:
            probs.append(f"{it['id']}: kaynak dosya yok ({it['file']}); siyahsız yerleştirildi")
            out.append(it)
            continue
        dst = os.path.join(out_dir, name)
        if not os.path.exists(dst):
            os.makedirs(out_dir, exist_ok=True)
            stem, ext = os.path.splitext(dst)
            tmp = f"{stem}.part{ext}"  # FFmpeg picks the format from the extension
            p = runner(_pad_cmd(it["file"], tmp), capture_output=True, text=True)
            if p.returncode != 0 or not os.path.exists(tmp):
                if os.path.exists(tmp):
                    os.remove(tmp)
                probs.append(f"{it['id']}: siyah arka plan yapılamadı ({(p.stderr or '').strip()[-200:]}); "
                             "siyahsız yerleştirildi")
                out.append(it)
                continue
            os.replace(tmp, dst)
        out.append(dict(it, file=glue.canon(dst)))
    return out, probs


def set_markers(tl, short_id, markers, frames, prefix):
    """Delete every marker of ours on the short (customData "short:<id>:..."; numbering can change between
    builds), then add `markers` (splan.marker dicts). A frame that holds a marker (the editor's) moves the
    marker on and shortens it; a range past the timeline end is cut. -> problems."""
    assert_ours(tl, prefix)
    mine = f"short:{short_id}:"
    for f, m in (tl.GetMarkers() or {}).items():
        if str(m.get("customData") or "").startswith(mine):
            tl.DeleteMarkerAtFrame(f)
    used = {int(f) for f in (tl.GetMarkers() or {})}
    probs = []
    for m in markers:
        f, end = m["frame"], min(m["frame"] + m["duration"], frames)
        while f in used and f < end - 1:
            f += 1
        if f >= end or f in used or not tl.AddMarker(f, m["color"], m["name"], m["note"], end - f, m["customData"]):
            probs.append(f"{m['customData']}: işaretçi eklenemedi (kare {m['frame']})")
            continue
        used.add(f)
    return probs


# ---- Resolve side (duck-typed; exercised live) ----

def video_tracks(tl):
    return list(range(1, tl.GetTrackCount("video") + 1))


def ensure_tracks(tl, n, prefix):
    assert_ours(tl, prefix)
    while tl.GetTrackCount("video") < n:
        if not tl.AddTrack("video"):
            raise sync.Problem(f"'{tl.GetName()}': video izi eklenemedi")


def delete_items(tl, its, prefix):
    """DeleteClips the items and the audio linked to them (a camera item's). -> ok"""
    assert_ours(tl, prefix)
    dead = list(its)
    for it in its:
        try:
            dead += [x for x in (it.GetLinkedItems() or []) if (x.GetTrackTypeAndIndex() or [""])[0] == "audio"]
        except Exception:  # noqa: BLE001  (no linked items: nothing more to delete)
            pass
    return bool(tl.DeleteClips(dead)) if dead else True


def audio_items(tl):
    """uid -> item of every audio track."""
    out = {}
    for k in range(1, (tl.GetTrackCount("audio") or 0) + 1):
        for it in tl.GetItemListInTrack("audio", k) or []:
            out[it.GetUniqueId()] = it
    return out


def assert_current(project, tl):
    """AppendToTimeline appends to the project's current timeline: it must still be tl (same uid)."""
    if project is None:
        return
    cur = project.GetCurrentTimeline()
    if cur is None or cur.GetUniqueId() != tl.GetUniqueId():
        raise NotOurs(f"geçerli zaman çizelgesi '{cur.GetName() if cur is not None else '-'}', "
                      f"'{tl.GetName()}' değil (Resolve'da başka zaman çizelgesi açıldı): eklenmedi, durduruldu")


def place(mp, tl, s0, fps, item, mpi, prefix, project=None):
    """Append one item, find it by uid diff on every video track, set its transform -> (plan item, problems).
    Anything else the append put on a video track is deleted again, and when the item itself didn't land, the
    audio the append made too (a camera clip's). project: the current timeline is checked to be tl first."""
    assert_ours(tl, prefix)
    assert_current(project, tl)
    before = set(sync.track_items(tl, s0, fps, video_tracks(tl))[1])
    before_audio = set(audio_items(tl))
    still = glue.is_still(mpi)
    ratio = glue.clip_ratio(mpi, fps)
    if still:
        mpi.SetMarkInOut(*glue.still_marks(item))
    try:
        mp.AppendToTimeline([append_spec(item, mpi, s0, still, ratio)])
    finally:
        if still:
            mpi.ClearMarkInOut()
    seen, by_uid = sync.track_items(tl, s0, fps, video_tracks(tl))
    new = [s for s in seen if s["uid"] not in before]
    mine = next((s for s in new if s["track"] == item["track"]), None)
    extra = [by_uid[s["uid"]] for s in new if s is not mine]
    probs = []
    if extra and not delete_items(tl, extra, prefix):
        probs.append(f"{item['id']}: fazladan yerleşen {len(extra)} öğe silinemedi")
    if mine is None:
        stray = [a for uid, a in audio_items(tl).items() if uid not in before_audio]
        if stray and not (assert_ours(tl, prefix) or tl.DeleteClips(stray)):
            probs.append(f"{item['id']}: görüntüsü yerleşmeyen {len(stray)} ses öğesi silinemedi")
    rec, p2 = glue.placed(item, mine, ratio)
    probs += p2
    if mine is not None:
        it = by_uid[mine["uid"]]
        probs += apply_transform(it, item.get("props") or {}, item["id"])
        rec["props"] = glue.seen_item(it, s0, item["track"], fps)["props"]
    return rec, probs


def _sort(items):
    return sorted(items, key=lambda i: (i["start"], i["track"], i["id"]))


def sync_short(ctx, tl, last_items, desired, segments, save):
    """Read back, remove, place. ctx: mp, media, bin (import folder), fps, prefix, project (optional: the current
    timeline is checked before every append). save(items) after the removes
    and after every placement. -> (items, counts, problems)"""
    mp, media, fps, prefix = ctx["mp"], ctx["media"], ctx["fps"], ctx["prefix"]
    assert_ours(tl, prefix)
    problems = []
    s0 = tl.GetStartFrame()
    ensure_tracks(tl, max([i["track"] for i in desired + last_items] or [1]), prefix)
    seen, by_uid = sync.track_items(tl, s0, fps, video_tracks(tl))
    current = splan.readback(last_items, seen, segments)
    keep, remove, add = plan.actions(current, desired)

    dead = [by_uid[i["uid"]] for i in remove if i.get("uid") in by_uid]
    if dead and not delete_items(tl, dead, prefix):
        problems.append(f"silme başarısız oldu ({len(dead)} öğe)")
    alive = set(sync.track_items(tl, s0, fps, video_tracks(tl))[1])
    survivors = [i for i in remove if i.get("uid") in alive]
    if survivors:
        problems.append("silinemeyen öğeler planda kaldı: " + ", ".join(i["id"] for i in survivors))
    save(_sort(keep + survivors))

    want = {d["id"]: d for d in desired}
    kept = []
    for i, _ in glue.rebind(keep, desired):
        d = want.get(i["id"]) if not i.get("editor") else None
        if d is not None:  # ours, untouched: follow the plan's flag/anchor, and its transform if that changed
            i = dict(i, flag=d.get("flag"), anchor=d.get("anchor"), background=d.get("background"))
            it = by_uid.get(i.get("uid"))
            if it is not None and transform_differs(d["props"], i.get("props") or {}):
                problems += apply_transform(it, d["props"], i["id"])
                i["props"] = glue.seen_item(it, s0, i["track"], fps)["props"]
        kept.append(i)
    kept += survivors
    added = []
    save(_sort(kept + added))
    for i in add:
        hit = collides(i, kept + added)
        if hit is not None:
            who = "düzenleyici öğesi" if hit.get("editor") else "silinemeyen öğe"
            problems.append(f"{i['id']}: yer dolu ({who} {hit['id']}), yerleştirilmedi")
            continue
        try:
            mpi = media.get(i["file"], ctx["bin"])
        except sync.Problem as err:
            if not err.reported:
                problems.append(f"{i['id']}: {err}")
            continue
        rec, probs = place(mp, tl, s0, fps, i, mpi, prefix, ctx.get("project"))
        problems += probs
        if rec.get("uid") is not None:
            added.append(rec)
            save(_sort(kept + added))
    out = _sort(kept + added)
    counts = {"added": len(added), "removed": len(remove) - len(survivors), "kept": len(kept),
              "editor": sum(1 for i in out if i.get("editor"))}
    return out, counts, problems


def read_cues(tl):
    """[{uid, start, end, text}] of every subtitle track, frames from the timeline start."""
    s0, out = tl.GetStartFrame(), []
    for k in range(1, (tl.GetTrackCount("subtitle") or 0) + 1):
        for c in tl.GetItemListInTrack("subtitle", k) or []:
            out.append({"uid": c.GetUniqueId(), "start": c.GetStart() - s0, "end": c.GetEnd() - s0,
                        "text": c.GetName() or ""})
    return out


def import_subtitles(mp, tl, folder, srt, prefix):
    """Append captions.srt to the (fresh, empty) timeline: the old media-pool clip of that path is deleted first
    (a re-import of a changed file at the same path returns the old clip). -> problems"""
    assert_ours(tl, prefix)
    key = glue.canon(srt)
    old = [c for c in folder.GetClipList() or [] if glue.canon(c.GetClipProperty("File Path")) == key]
    if old:
        mp.DeleteClips(old)
    mp.SetCurrentFolder(folder)
    try:
        got = mp.ImportMedia([srt]) or []
    finally:
        mp.SetCurrentFolder(mp.GetRootFolder())
    if not got:
        return [f"altyazı içe aktarılamadı: {srt}"]
    if not mp.AppendToTimeline([got[0]]):
        return [f"altyazı zaman çizelgesine eklenemedi: {srt}"]
    return []


def create_timeline(mp, folder, name, fps, prefix):
    """A new empty 1080x1920 timeline at fps in folder -> timeline; raises sync.Problem (the half-made timeline
    is deleted again)."""
    if not is_ours(name, prefix):
        raise NotOurs(f"'{name}' bir short zaman çizelgesi adı değil: oluşturulmadı")
    mp.SetCurrentFolder(folder)
    try:
        tl = mp.CreateEmptyTimeline(name)
    finally:
        mp.SetCurrentFolder(mp.GetRootFolder())
    if not tl:
        raise sync.Problem(f"'{name}' oluşturulamadı")
    assert_ours(tl, prefix)
    want = (("useCustomSettings", "1"), ("timelineResolutionWidth", str(W)), ("timelineResolutionHeight", str(H)),
            ("timelineFrameRate", str(fps)))
    bad = [k for k, v in want if not tl.SetSetting(k, v)]
    got = (tl.GetSetting("timelineResolutionWidth"), tl.GetSetting("timelineResolutionHeight"),
           tl.GetSetting("timelineFrameRate"))
    try:
        rate_ok = float(got[2]) == float(fps)
    except (TypeError, ValueError):
        rate_ok = False
    if bad or got[:2] != (str(W), str(H)) or not rate_ok:
        mp.DeleteTimelines([tl])  # ours and empty: the next build starts clean
        raise sync.Problem(f"'{name}' dikey ayarlanamadı ({', '.join(bad) or got}); silindi")
    return tl


def mute_scratch(tl, prefix):
    """Disable the camera's stereo scratch-audio tracks, as the rough cutter does on chapter timelines (the mono
    track is the recorder WAV linked to the camera clip). -> number disabled"""
    assert_ours(tl, prefix)
    n = 0
    for k in range(1, (tl.GetTrackCount("audio") or 0) + 1):
        if tl.GetTrackSubType("audio", k) == "stereo" and tl.GetIsTrackEnabled("audio", k):
            n += bool(tl.SetTrackEnable("audio", k, False))
    return n
