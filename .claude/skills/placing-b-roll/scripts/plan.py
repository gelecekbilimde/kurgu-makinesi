"""What goes on a chapter's B-roll timeline (pure: no Resolve calls). broll/plan.json is the truth:

  {"units": "frames", "chapters": {"<N>": {"timeline": str, "items": [Item, ...]}}}
  Item = {"id": "<row id>#<n>" | "E<n>", "row": key|null, "track": 2|3, "start", "end", "file": str|null,
          "src_in", "src_out", "kind", "code": str|null, "editor": bool, "deleted": bool, "uid": str|null,
          "props": dict, "marker": str|null}

All frames, half-open: the item covers [start, end) of the B-roll timeline and plays [src_in, src_out) of its
file. A still has src_in 0, src_out = its length. editor: the editor changed (or added) the item in Resolve,
so build never touches it; deleted: the editor deleted our item ("nothing here", never rebuilt, file null).
seen (optional): {start, end, src_in, src_out} as Resolve placed the item when that differs from the plan only by
clip-rate rounding (a clip slower or faster than the timeline); read-back compares against it, the identity
stays the planned one.
An item's identity is (track, start, end, file, src_in, src_out); props and uid are not part of it.
"""
import json
import os

IDENTITY = ("track", "start", "end", "file", "src_in", "src_out")
SEEN = IDENTITY + ("props",)
NO_STOCK = "stok yetmedi"
ROW_LOST = "satırı kayboldu"


def _item(row_id, key, n, asset, track, start, end, file, src_in, code, marker=None):
    return {"id": f"{row_id}#{n}", "row": key, "track": track, "start": start, "end": end, "file": file,
            "src_in": src_in, "src_out": src_in + (end - start), "kind": asset["kind"], "code": code,
            "editor": False, "deleted": False, "uid": None, "props": {}, "marker": marker}


def _marker(row, asset, visual):
    text = f"{row['id']} {asset.get('tag') or '?'}: {visual or ''}"
    return text + (f" ({asset['note']})" if asset.get("note") else "")


def _row(key, row, assets, visual):
    """(items, frames the stock of this row left empty)"""
    items, short = [], 0
    start, end = row["start"], row["end"]

    def add(asset, s, e, file, src_in=0, code=None, marker=None):
        items.append(_item(row["id"], key, len(items) + 1, asset, asset["track"], s, e, file, src_in, code, marker))

    for a in assets:
        files = a.get("files") or []
        if not files:
            continue
        kind, first = a["kind"], files[0]
        if kind == "stock":
            pos = start
            for c in files:
                if pos >= end:
                    break
                n = end - pos if c.get("frames") is None else min(c["frames"], end - pos)
                if n > 0:
                    add(a, pos, pos + n, c["file"], code=c.get("code"))
                    pos += n
            short += end - pos
        elif kind == "graphic":
            if a.get("hold") and a.get("hold_from"):
                cut = min(start + a["hold_from"], end)
                add(a, start, cut, first["file"], code=first.get("code"))
                if cut < end:
                    add(a, cut, end, a["hold"], code=first.get("code"))
            else:
                n = end - start if first.get("frames") is None else min(first["frames"], end - start)
                add(a, start, start + n, first["file"], code=first.get("code"))
        else:  # kaynak, placeholder: one still over the whole row
            marker = _marker(row, a, visual) if kind == "placeholder" else None
            add(a, start, end, first["file"], code=first.get("code"), marker=marker)
    return items, short


def _rows(chapter_rows, fetched, visuals=None):
    visuals = visuals or {}
    for key, row in chapter_rows.items():
        assets = fetched.get("rows", {}).get(key)
        if row is None or not assets:
            continue
        yield (row,) + _row(key, row, assets, visuals.get(key, ""))


def desired(chapter_rows, fetched, visuals=None):
    """The items the skill would place for one chapter. chapter_rows: rows.json chapters[N]["rows"]
    (key -> {"id", "start", "end"} | null); fetched: fetched.json; visuals: key -> the script row's visual
    (placeholder marker text). Rows not found in the chapter or not fetched yet get nothing."""
    return [i for _, items, _ in _rows(chapter_rows, fetched, visuals) for i in items]


def shortfalls(chapter_rows, fetched):
    """Summary lines for rows whose stock candidates together are shorter than the row."""
    return [f"{row['id']}: {NO_STOCK} ({short} kare boş)"
            for row, _, short in _rows(chapter_rows, fetched) if short > 0]


def unused_candidates(fetched_row_assets, items):
    """Files of a row's fetched assets that no item uses (stock candidates beyond the coverage)."""
    used = {i["file"] for i in items}
    out = []
    for a in fetched_row_assets:
        for c in a.get("files") or []:
            if c["file"] not in used and c["file"] not in out:
                out.append(c["file"])
    return out


def _e_number(id_):
    return int(id_[1:]) if id_.startswith("E") and id_[1:].isdigit() else 0


def readback(last, seen):
    """Merge what the editor did in Resolve into the last plan. seen: the V2/V3 items now on the B-roll timeline,
    {uid, track, start, end, file, src_in, src_out, props}.
    - an item that changed in any seen field -> editor: true with the seen values;
    - our item whose uid is gone -> editor: true, deleted: true, file null (never rebuilt);
    - a uid we didn't place -> a new "E<n>" entry, row null, editor: true.
    An editor-added entry that is gone again is dropped; an item of ours with no uid (never placed) is dropped,
    so build places it again."""
    by_uid = {s["uid"]: s for s in seen}
    out, known = [], set()
    for it in last:
        if it.get("deleted"):
            out.append(it)
            continue
        s = by_uid.get(it.get("uid")) if it.get("uid") is not None else None
        if s is None:
            if it.get("uid") is None or it.get("row") is None:
                continue
            out.append(dict(it, editor=True, deleted=True, file=None, uid=None))
            continue
        known.add(it["uid"])
        ref = dict(it, **(it.get("seen") or {}))  # a rate-rounded placement is compared with what Resolve made
        if any(s.get(k) != ref.get(k) for k in SEEN):
            it = dict(it, editor=True, **{k: s.get(k) for k in SEEN})
            it.pop("seen", None)
        out.append(it)
    n = max((_e_number(i["id"]) for i in last), default=0)
    for s in seen:
        if s["uid"] in known:
            continue
        n += 1
        known.add(s["uid"])
        out.append({"id": f"E{n}", "row": None, **{k: s.get(k) for k in SEEN}, "kind": None, "code": None,
                    "editor": True, "deleted": False, "uid": s["uid"], "marker": None})
    return out


def _key(i):
    return tuple(i.get(k) for k in IDENTITY)


def actions(current, desired):
    """(keep, remove, add): the new plan is keep + add. Editor-added entries (row null) and every item of a row
    with any editor entry are kept as they are (deleted editor entries included: they are plan entries, not
    timeline items). For other rows an item equal in identity to a desired one is kept; every other current
    item is removed (this covers rows no longer in rows.json) and every other desired item is added."""
    locked = {i["row"] for i in current if i.get("editor")}
    keep, add, free = [], [], {}
    for i in current:
        if i.get("row") is None or i["row"] in locked:
            keep.append(i)
        else:
            free.setdefault(_key(i), []).append(i)
    for d in desired:
        if d["row"] in locked:
            continue
        match = free.get(_key(d))
        if match:
            keep.append(match.pop(0))
        else:
            add.append(d)
    kept = {id(i) for i in keep}
    remove = [i for i in current if id(i) not in kept]
    return keep, remove, add


def lost(items, chapter_rows):
    """Summary lines for rows that left rows.json while they still have editor entries."""
    count = {}
    for i in items:
        if i.get("editor") and i.get("row") is not None and i["row"] not in chapter_rows:
            row_id = i["id"].split("#", 1)[0]
            count[row_id] = count.get(row_id, 0) + 1
    return [f"{r}: {ROW_LOST} ({n} düzenleyici öğesi)" for r, n in count.items()]


def load(path):
    if not os.path.exists(path):
        return {"units": "frames", "chapters": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
