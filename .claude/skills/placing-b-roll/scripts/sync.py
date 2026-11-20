"""One chapter's B-roll timeline brought in line with the plan, through duck-typed Resolve objects (the media pool,
the timeline, folders, items): tests drive it with fakes, broll_resolve.py with the real API.

Order matters (reference.md): remove before add (an append over an item is cut to the free gap); every result
is read back from the timeline, never trusted from a return value; plan items are handed to `save` as soon as the
timeline changed, so an exit or an exception later never leaves an unrecorded clip.
"""
import build as glue
import plan


class Problem(Exception):
    """A Resolve step that failed; Turkish, fit for the summary."""


def subfolder(mp, parent, name):
    for f in parent.GetSubFolderList() or []:
        if f.GetName() == name:
            return f
    f = mp.AddSubFolder(parent, name)
    if not f:
        raise Problem(f"'{name}' klasörü oluşturulamadı")
    return f


def index_paths(folder, out=None):
    """canonical file path -> media-pool item, for every clip under folder (recursive)"""
    out = {} if out is None else out
    for c in folder.GetClipList() or []:
        fp = c.GetClipProperty("File Path")
        if fp:
            out.setdefault(glue.canon(fp), c)
    for f in folder.GetSubFolderList() or []:
        index_paths(f, out)
    return out


class Media:
    """Imports into our bins only, reusing an item already imported anywhere under '<prefix> B-roll'."""

    def __init__(self, mp, top):
        self.mp, self.root, self.paths = mp, mp.GetRootFolder(), index_paths(top)

    def get(self, path, folder):
        """the media-pool item of path; raises Problem when it can't be imported"""
        key = glue.canon(path)
        if key in self.paths:
            return self.paths[key]
        if folder is None:
            raise Problem(f"klasör yok, içe aktarılmadı: {path}")
        self.mp.SetCurrentFolder(folder)
        try:
            got = self.mp.ImportMedia([path]) or []
        finally:
            self.mp.SetCurrentFolder(self.root)
        if not got:
            raise Problem(f"içe aktarılamadı: {path}")
        mpi = got[0]
        if glue.canon(mpi.GetClipProperty("File Path")) != key:
            raise Problem(f"içe aktarılan dosya farklı: {path} -> {mpi.GetClipProperty('File Path')}")
        self.paths[key] = mpi
        return mpi


def track_items(tl, s0, fps):
    """(seen dicts, uid -> timeline item) of V2 and V3"""
    seen, by_uid = [], {}
    for k in (2, 3):
        if k > tl.GetTrackCount("video"):
            continue
        for it in tl.GetItemListInTrack("video", k) or []:
            s = glue.seen_item(it, s0, k, fps)
            seen.append(s)
            by_uid[s["uid"]] = it
    return seen, by_uid


def _overlaps(a, b):
    return a["track"] == b["track"] and a["start"] < b["end"] and b["start"] < a["end"]


def place(mp, tl, s0, fps, item, mpi):
    """Append one plan item and find what was really placed by diffing V2/V3 uids (an append's return value can
    name an item that isn't there, reference.md 1). Returns (plan item, problems); anything extra the append made
    is deleted again so no clip is left unrecorded."""
    before = set(track_items(tl, s0, fps)[1])
    still = glue.is_still(mpi)
    if still:
        mpi.SetMarkInOut(*glue.still_marks(item))
    try:
        mp.AppendToTimeline([glue.append_spec(item, mpi, s0, still, glue.clip_ratio(mpi, fps))])
    finally:
        if still:
            mpi.ClearMarkInOut()
    seen, by_uid = track_items(tl, s0, fps)
    new = [s for s in seen if s["uid"] not in before]
    mine = next((s for s in new if s["track"] == item["track"]), None)
    extra = [by_uid[s["uid"]] for s in new if s is not mine]
    probs = []
    if extra and not tl.DeleteClips(extra):
        probs.append(f"{item['id']}: fazladan yerleşen {len(extra)} öğe silinemedi")
    rec, p2 = glue.placed(item, mine)
    return rec, probs + p2


def sync_items(tl, mp, media, ch_bin, fps, last_items, desired, save):
    """Read back, remove, place, mark. save(items) is called with the full plan item list after the removes and
    after every placement. Returns (items, counts, problems)."""
    problems = []
    s0 = tl.GetStartFrame()
    seen, by_uid = track_items(tl, s0, fps)
    current = plan.readback(last_items, seen)
    keep, remove, add = plan.actions(current, desired)

    dead = [by_uid[i["uid"]] for i in remove if i.get("uid") in by_uid]
    if dead and not tl.DeleteClips(dead):
        problems.append(f"silme başarısız oldu ({len(dead)} öğe)")
    alive = set(track_items(tl, s0, fps)[1])
    survivors = [i for i in remove if i.get("uid") in alive]
    if survivors:
        problems.append("silinemeyen öğeler planda kaldı: " + ", ".join(i["id"] for i in survivors))
    for i in remove:
        if i not in survivors:
            tl.DeleteMarkerByCustomData(glue.CUSTOM + i["id"])

    kept = []
    for i, old_id in glue.rebind(keep, desired):
        if i.get("kind") == "placeholder" and not i.get("editor") and i.get("row") is not None:
            tl.DeleteMarkerByCustomData(glue.CUSTOM + old_id)  # added again below with the current text
        kept.append(i)
    kept += survivors
    ids = {i["id"] for i in kept}

    def items():
        return sorted(kept + added, key=lambda i: (i["start"], i["track"], i["id"]))

    added = []
    save(items())
    for i in add:
        if i["id"] in ids or any(_overlaps(i, s) for s in survivors):
            problems.append(f"{i['id']}: yer dolu (silinemeyen öğe), yerleştirilmedi")
            continue
        try:
            mpi = media.get(i["file"], ch_bin)
        except Problem as err:
            problems.append(f"{i['id']}: {err}")
            continue
        rec, probs = place(mp, tl, s0, fps, i, mpi)
        problems += probs
        if rec.get("uid") is not None:
            added.append(rec)
            save(items())

    used = {int(f) for f in (tl.GetMarkers() or {})}
    for i in kept + added:
        if i.get("editor") or i.get("uid") is None:
            continue
        m = glue.marker_args(i, used)
        if m and tl.GetMarkerByCustomData(m["customData"]) in (None, {}):
            if tl.AddMarker(m["frameId"], m["color"], m["name"], m["note"], m["duration"], m["customData"]):
                used.add(m["frameId"])
            else:
                problems.append(f"{i['id']}: işaretçi eklenemedi")
    out = items()
    counts = {"added": len(added), "removed": len(remove) - len(survivors), "kept": len(kept),
              "editor": sum(1 for i in out if i.get("editor"))}
    return out, counts, problems


def file_candidates(mp, media, ch_bin, chapter_rows, fetched, items):
    """Unused candidates of each row -> bin <ch_bin>/<row id>. Never raises; returns problems."""
    problems = []
    for key, row in chapter_rows.items():
        if row is None:
            continue
        files = plan.unused_candidates(fetched.get("rows", {}).get(key, []), [i for i in items if i.get("row") == key])
        if not files:
            continue
        try:
            row_bin = subfolder(mp, ch_bin, row["id"]) if ch_bin is not None else None
            for f in files:
                media.get(f, row_bin)
        except Exception as err:  # noqa: BLE001  (bins are a convenience; the timeline and plan are done)
            problems.append(f"{row['id']} adayları: {err}")
    return problems
