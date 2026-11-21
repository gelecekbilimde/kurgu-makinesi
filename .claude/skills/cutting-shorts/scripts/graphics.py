"""Graphics of one short (pure): vertical re-render requests for the B-roll graphics it copies, and the teaser
caption, end card, header and watermark requests, or a placeholder + "Gereken şablonlar" line per missing template.

`templates`: make_graphic.py --list --json; `archive`: the B-roll skill's broll/grafik/results.json."""
import os

import captions

END_CARD_S = 3

# template name -> (role, overlay, the "Gereken şablonlar" line when it is missing)
NEEDS = {
    "teaser-caption": ("teaser-caption", True,
                       "teaser-caption: teaser'ın sözlerini kelime kelime, konuşmaya zamanlı gösteren dikey altyazı "
                       "(words alanı; şeffaf, konuşmacının başının arkasında durur)"),
    "end-card": ("end-card", False,
                 "end-card: dikey bitiş kartı (title alanı): logo, \"YENİ VİDEO\", bölümün başlığı, "
                 "\"Videonun tamamı YouTube kanalımızda\""),
    "short-header": ("header", True, "short-header: shortun üstünde duran başlık (title alanı; dikey, şeffaf)"),
    "watermark": ("watermark", True, "watermark: filigran (state alanı, static)"),
}


def end_card_frames(fps):
    return round(END_CARD_S * fps)


def _graphic_rows(short_layout, templates, archive):
    by_file = {r["file"]: r for r in archive.get("renders", [])}
    rows, seen = [], set()
    for it in short_layout["broll"]:
        if it["kind"] != "graphic":
            continue
        rec = by_file.get(os.path.basename(it["file"]))
        t = templates.get(rec["template"]) if rec else None
        if not t or not t.get("vertical") or rec["code"] in seen:
            continue  # no vertical version (or a hand-added graphic): fitted to the width and flagged later
        seen.add(rec["code"])
        row = {"template": rec["template"], "code": rec["code"], "fields": rec.get("values") or {},
               "replaces": it["file"]}
        if rec.get("variant"):
            row["variant"] = rec["variant"]
        row.update(background=bool(rec.get("background")), vertical=True, frames=rec["frames"])
        rows.append(row)
    return rows


def requests(ep, cand, short_layout, templates, archive, words=()):
    """(batch_rows, placeholders, needed). words: the short's words in short frames (captions shape), for the
    teaser caption's `words` field. A re-render row carries "replaces" (the B-roll file it stands in for); each
    own-graphic row and placeholder carries "role" and "range" ([start, end) on the short); placeholders also
    "template", "overlay" and "text". Drop "replaces", "role" and "range" before handing rows to make_graphic."""
    templates = {t["name"]: t for t in templates}
    rows = _graphic_rows(short_layout, templates, archive)
    teaser, end_card = short_layout["teaser"], short_layout["end_card"]
    passage = [teaser[1], end_card[0]]
    wanted = [("teaser-caption", teaser, {"words": captions.teaser_words(list(words), teaser)},
               " ".join(w["text"] for w in captions.teaser_words(list(words), teaser))),
              ("end-card", end_card, {"title": ep.m["title"]}, ep.m["title"])]
    if cand.get("header"):
        wanted.append(("short-header", passage, {"title": cand.get("title", "")}, cand.get("title", "")))
    wanted.append(("watermark", passage, {"state": "static"}, "filigran"))
    placeholders, needed = [], []
    for name, rng, fields, text in wanted:
        role, overlay, need = NEEDS[name]
        t = templates.get(name)
        if t is None:
            placeholders.append({"template": name, "role": role, "range": list(rng), "overlay": overlay,
                                 "text": text})
            needed.append(need)
            continue
        row = {"template": name, "code": role, "fields": fields, "role": role, "range": list(rng)}
        if name != "watermark":
            row["frames"] = rng[1] - rng[0]
        if name == "end-card":
            row["background"] = True
        if t.get("vertical"):
            row["vertical"] = True
        rows.append(row)
    return rows, placeholders, needed
