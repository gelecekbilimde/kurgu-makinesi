"""broll/requests.json: what B-roll each script row asks for."""
import json
import os


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


def pending(rows, data):
    have = data.get("rows", {})
    res = []
    for r in rows:
        tags = {q.get("tag") for q in have.get(r.key, [])}
        need = r.tags or (["?"] if r.visual.strip() else [])
        if any(t not in tags for t in need):
            res.append(r)
    return res


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
