"""broll/requests.json: what B-roll each script row asks for."""
import json
import os

import rows as rows_mod


def load(path):
    if not os.path.exists(path):
        return {"units": "frames", "rows": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def autofill(row):
    out = []
    if not row.tags and row.visual.strip():
        # untagged or unknown tag (e.g. a dropped [YZ]): never a silent gap
        return [{"tag": "?", "kind": "placeholder", "reason": "tür yok"}]
    for tag in row.tags:
        if tag == "ARŞİV":
            out.append({"tag": tag, "kind": "placeholder", "reason": "arşiv"})
        elif tag == "KAYNAK":
            if row.links:
                out.append({"tag": tag, "kind": "kaynak", "url": row.links[0]})
            else:
                out.append({"tag": tag, "kind": "placeholder", "reason": "link yok"})
    return out


def needed_tags(row):
    """the tags a row needs one request each for: its B-roll tags, "?" for an untagged row with a visual"""
    return rows_mod.broll_tags(row) or (["?"] if not row.tags and row.visual.strip() else [])


def missing_tags(row, row_requests):
    """needed tags with no request in row_requests (the row's requests.json list)"""
    have = {q.get("tag") for q in row_requests or []}
    return [t for t in needed_tags(row) if t not in have]


def pending(rows, data):
    have = data.get("rows", {})
    return [r for r in rows if missing_tags(r, have.get(r.key, []))]


def validate(req, templates):
    """Problems of a request (empty list = fine). templates: name -> make_graphic.py --list --json entry."""
    kind = req.get("kind")
    if kind == "stock":
        return [] if str(req.get("query", "")).strip() else ["query boş"]
    if kind == "graphic":
        t = templates.get(req.get("template"))
        if t is None:
            return [f"bilinmeyen şablon: {req.get('template')!r}"]
        fields = req.get("fields") or {}
        return [f"eksik alan: {f['name']}" for f in t.get("fields", [])
                if f.get("required") and fields.get(f["name"]) in (None, "")]
    if kind == "kaynak":
        return [] if str(req.get("url", "")).strip() else ["url boş"]
    if kind == "placeholder":
        return [] if req.get("reason") else ["reason yok"]
    return [f"bilinmeyen kind: {kind!r}"]
