"""Read a script .docx (stdlib only).

A/V template scripts (per-heading tables GÖRÜNTÜ | SES; the visual type leads GÖRÜNTÜ as "[STOK] …") become:
  script.json   header, speaker, headings, rows (tags, visual, links, refs, SES, est_s, warnings), notes,
                Kaynakça, total_s ("as written": SES words at the speaker's pace from speakers.json)
  script.txt    the shape the rough cutter's sections.py reads ([HeadingN] lines, SES lines, [EKRAN: …] lines)
  prompter.txt  (--prompter) headings and SES only, for the teleprompter
The script ends at the Kaynakça (or at a Heading 1): anything after it, such as the Kılavuz tab that
Google's export appends, is ignored. Old-style scripts (no A/V table) give script.txt exactly as docx_to_text.py did: every paragraph,
tables included, prefixed with "[<styleId>] " when styled.

Speaker (for the pace), strongest first: "speaker" in <outdir>/episode.json, --speaker, the script
header's "Sunucu:", else unknown (speakers.json default pace).

Usage: python3 templates/script/script_doc.py <script.docx> <outdir> [--prompter] [--speaker "Name"]
"""
import hashlib, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
STOP = ("Kaynakça", "Kaynaklar")
COLS = {"GORUNTU": "visual", "SES": "ses"}     # other columns are ignored
HEADER_ROW = ["GÖRÜNTÜ", "SES"]
SPEAKERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speakers.json")


def load_speakers(path=SPEAKERS):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_speaker(name, source, speakers):
    """{"name", "rate", "source", "known"}; names match case- and Turkish-letter-insensitively."""
    by_fold = {rules.fold(k): k for k in speakers["speakers"]}
    canon = by_fold.get(rules.fold(name or ""))
    return {"name": canon or name or None, "rate": speakers["speakers"][canon] if canon else speakers["default"],
            "source": source if name else "default", "known": canon is not None}


def _xml(path, part):
    with zipfile.ZipFile(path) as z:
        return ET.fromstring(z.read(part)) if part in z.namelist() else None


def _style_names(path):
    root = _xml(path, "word/styles.xml")
    if root is None:
        return {}
    return {s.get(W + "styleId"): (s.find(W + "name").get(W + "val") if s.find(W + "name") is not None else "")
            for s in root.iter(W + "style")}


R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _links(path):
    """Hyperlink relationship id -> URL (Google exports titled links with the URL only here)."""
    root = _xml(path, "word/_rels/document.xml.rels")
    if root is None:
        return {}
    return {r.get("Id"): r.get("Target") for r in root if (r.get("Type") or "").endswith("/hyperlink")}


def _para_text(p, links=None):
    out = []

    def walk(el):
        for ch in el:
            if ch.tag == W + "t":
                out.append(ch.text or "")
            elif ch.tag in (W + "br", W + "cr"):
                out.append("\n")
            elif ch.tag == W + "tab":
                out.append(" ")
            else:
                walk(ch)
                url = (links or {}).get(ch.get(R + "id")) if ch.tag == W + "hyperlink" else None
                if url and url not in "".join(out):
                    out.append(" " + url)      # keep the target of a titled link next to its title
    walk(p)
    return "".join(out)


def _style(p, names):
    ps = p.find(W + "pPr/" + W + "pStyle")
    if ps is None:
        return None
    sid = ps.get(W + "val")
    m = re.fullmatch(r"heading (\d)", (names.get(sid) or "").strip(), re.I)
    return f"Heading{m.group(1)}" if m else sid


def _is_list(p, style):
    return p.find(W + "pPr/" + W + "numPr") is not None or style == "ListParagraph"


def _blocks(parent, names, links):
    for el in parent:
        if el.tag == W + "p":
            style = _style(el, names)
            yield ("p", style, _para_text(el, links), _is_list(el, style))
        elif el.tag == W + "tbl":
            rows = []
            for tr in el.findall(W + "tr"):
                rows.append(["\n".join(_para_text(p, links) for p in tc.iter(W + "p")) for tc in tr.findall(W + "tc")])
            yield ("tbl", rows)
        elif el.tag == W + "sdt":
            content = el.find(W + "sdtContent")
            if content is not None:
                yield from _blocks(content, names, links)


def read_blocks(path):
    body = _xml(path, "word/document.xml").find(W + "body")
    return list(_blocks(body, _style_names(path), _links(path)))


def legacy_text(path):
    """Byte-identical to the old docx_to_text.py output."""
    paras = []
    for p in _xml(path, "word/document.xml").iter(W + "p"):
        txt = "".join((t.text or "") for t in p.iter(W + "t"))
        style = p.find(W + "pPr/" + W + "pStyle")
        paras.append(("[%s] " % style.get(W + "val") if style is not None else "") + txt)
    return "\n".join(paras)


def _columns(row):
    cols = {}
    for i, cell in enumerate(row):
        key = COLS.get(rules.fold(cell))
        if key:
            cols[key] = i
    return cols if {"visual", "ses"} <= cols.keys() else None


def _cell(row, cols, key):
    i = cols.get(key)
    return row[i].strip() if i is not None and i < len(row) else ""


def _chapter_start(blocks):
    """Index of the first chapter heading: the first Heading2 starting with "1." (as sections.py), else
    the first Heading2, else 0. Everything before it is front matter."""
    h2 = [i for i, b in enumerate(blocks) if b[0] == "p" and b[1] == "Heading2"]
    first = [i for i in h2 if blocks[i][2].strip().startswith("1.")]
    return (first or h2 or [0])[0]


def _front(blocks, s):
    """Front matter. The header fields come from the first two-column table before any heading
    (Başlık | …, Sunucu | …); the title is a Title/Heading1 paragraph or the "Başlık" field. Everything
    else is kept verbatim as text in s["front"] (tables as "a | b" rows)."""
    seen_heading = False
    for b in blocks:
        if b[0] == "tbl":
            rows = [r for r in b[1] if any(c.strip() for c in r)]
            fields = (not seen_heading and not s["header"] and rows and all(len(r) == 2 for r in rows)
                      and all(0 < len(r[0].strip()) <= 40 for r in rows))
            if fields:
                s["header"] = {r[0].strip(): r[1].strip() for r in rows}
            else:
                s["front"].extend(" | ".join(c.strip() for c in row) for row in rows)
            continue
        _, style, text, _ = b
        text = text.strip()
        if not text:
            continue
        if style in ("Title", "Heading1") and not s["title"]:
            s["title"] = text
            continue
        seen_heading = seen_heading or (style or "").startswith("Heading")
        s["front"].append(text)
    if not s["title"]:
        s["title"] = s["header"].get("Başlık", "")


def parse(path, stop=STOP, speaker=None, speaker_source="cli", speakers=None):
    blocks = read_blocks(path)
    if not any(b[0] == "tbl" and b[1] and _columns(b[1][0]) for b in blocks):
        return None
    stop_f = tuple(rules.fold(s) for s in stop)
    s = {"format": "av-1", "title": "", "header": {}, "front": [], "headings": [], "rows": [], "notes": [],
         "kaynakca": []}
    start = _chapter_start(blocks)
    _front(blocks[:start], s)
    head, in_refs = None, False
    for b in blocks[start:]:
        if b[0] == "p":
            _, style, text, is_list = b
            text = text.strip()
            # The script ends at a Heading1, or at the next Heading1/2 after the Kaynakça: Google's .docx
            # export appends every tab, so the Kılavuz tab follows the script.
            if text and (style == "Heading1" or (in_refs and style == "Heading2")):
                if not in_refs:
                    s["notes"].append({"heading": head, "text": f'senaryo "{text}" başlığında bitti: Başlık 1 '
                                       "stili kullanılmış; bölümler Başlık 2, alt başlıklar Başlık 3 olmalı"})
                break
            if style == "Title" and not s["title"]:
                s["title"] = text
            elif style in ("Heading2", "Heading3"):
                in_refs = rules.fold(text).startswith(stop_f)
                if not in_refs:
                    s["headings"].append({"level": int(style[-1]), "title": text})
                    head = len(s["headings"]) - 1
            elif not text:
                continue
            elif in_refs:
                if is_list:
                    s["kaynakca"].append({"k": len(s["kaynakca"]) + 1, "text": text})
            else:
                s["notes"].append({"heading": head, "text": text})
            continue
        rows = b[1]
        cols = _columns(rows[0]) if rows else None
        if cols is None and not in_refs and head is not None and rows and all(len(r) == 2 for r in rows):
            # a GÖRÜNTÜ | SES table whose header row was not copied: read it, but say so
            s["notes"].append({"heading": head, "text": "tabloda GÖRÜNTÜ | SES başlık satırı yok; "
                               "sütunlar GÖRÜNTÜ, SES olarak okundu"})
            cols, rows = {"visual": 0, "ses": 1}, [HEADER_ROW] + rows
        if cols is None:
            if rows and not in_refs:
                s["notes"].append({"heading": head, "text": "A/V olmayan tablo: " + " | ".join(rows[0])})
            continue
        for row in rows[1:]:
            if not any(c.strip() for c in row) or _columns(row):
                continue
            tags, unknown, visual = rules.split_visual(_cell(row, cols, "visual"))
            if unknown:
                s["notes"].append({"heading": head, "text": "bilinmeyen TÜR: " + ", ".join(unknown)})
            ses = _cell(row, cols, "ses")
            s["rows"].append({
                "id": "R%03d" % (len(s["rows"]) + 1),
                "key": hashlib.sha1((rules.fold(ses) or rules.fold(visual)).encode()).hexdigest()[:8],
                "heading": head, "tags": tags, "visual": visual,
                "links": re.findall(r"https?://\S+", visual), "refs": re.findall(r"\bK\d+\b", visual),
                "ses": ses})
    if not speaker:
        speaker, speaker_source = s["header"].get("Sunucu", "").strip() or None, "script"
    s["speaker"] = resolve_speaker(speaker, speaker_source, speakers or load_speakers())
    for r in s["rows"]:
        res = rules.check_row(r["tags"], r["visual"], r["ses"], s["speaker"]["rate"])
        r["est_s"], r["warnings"] = res["seconds"], res["warnings"]
    s["total_s"] = sum(r["est_s"] for r in s["rows"] if r["est_s"] is not None)
    return s


def to_legacy_txt(s):
    out = []

    def rows_under(h):
        for r in s["rows"]:
            if r["heading"] != h:
                continue
            if r["tags"] != ["KAMERA"]:
                out.append(f"[EKRAN: {'+'.join(r['tags']) or '?'}: {' '.join(r['visual'].split())}]")
            out.extend(line for line in r["ses"].split("\n") if line.strip())

    rows_under(None)
    for i, h in enumerate(s["headings"]):
        out.append(f"[Heading{h['level']}] {h['title']}")
        rows_under(i)
    if s["kaynakca"]:
        out.append("[Heading2] Kaynakça")
        out.extend(f"[ListParagraph] {k['text']}" for k in s["kaynakca"])
    return "\n".join(out)


def prompter_txt(s):
    parts = []
    for i, h in enumerate(s["headings"]):
        parts.append(h["title"])
        for r in s["rows"]:
            if r["heading"] == i:
                parts.extend(line.strip() for line in r["ses"].split("\n") if line.strip())
    return "\n\n".join(parts) + "\n"


def main(argv):
    args, speaker, source = [], None, "cli"
    it = iter(argv)
    for a in it:
        if a == "--speaker":
            speaker = next(it, None)
        elif a != "--prompter":
            args.append(a)
    if len(args) != 2 or ("--speaker" in argv and not speaker):
        sys.exit(__doc__)
    src, outdir = args
    os.makedirs(outdir, exist_ok=True)
    manifest = os.path.join(outdir, "episode.json")
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            ep_speaker = json.load(f).get("speaker")
        if ep_speaker:
            if speaker and rules.fold(speaker) != rules.fold(ep_speaker):
                print(f"note: --speaker {speaker!r} ignored, episode.json says {ep_speaker!r}")
            speaker, source = ep_speaker, "episode"
    s = parse(src, speaker=speaker, speaker_source=source)

    def write(name, text):
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
            f.write(text)

    if s is None:
        write("script.txt", legacy_text(src))
        print("legacy script (no A/V tables)")
        if "--prompter" in argv:
            sys.exit("--prompter needs an A/V script")
        return
    write("script.json", json.dumps(s, ensure_ascii=False, indent=1))
    write("script.txt", to_legacy_txt(s))
    if "--prompter" in argv:
        write("prompter.txt", prompter_txt(s))
    sp = s["speaker"]
    where = {"episode": "episode.json", "cli": "--speaker", "script": "senaryo", "default": "bilinmiyor"}[sp["source"]]
    print(f"Sunucu: {sp['name'] or '?'} ({where}, {sp['rate']} kelime/sn"
          + ("" if sp["known"] else ", speakers.json'da yok: varsayılan hız") + ")")
    for r in s["rows"]:
        if r["warnings"]:
            title = s["headings"][r["heading"]]["title"][:30] if r["heading"] is not None else ""
            dur = f" ({r['est_s']} sn)" if r["est_s"] is not None else ""
            print(f"{r['id']} {title}: " + "; ".join(rules.WARN[w] for w in r["warnings"]) + dur)
    for n in s["notes"]:
        title = s["headings"][n["heading"]]["title"][:30] if n["heading"] is not None else ""
        print(f"NOT {title}: {n['text']}")
    print(f"{len(s['rows'])} rows, {len(s['notes'])} notes")
    print(f"Tahmini toplam (yazıldığı gibi): {rules.format_total(s['total_s'])}")


if __name__ == "__main__":
    main(sys.argv[1:])
