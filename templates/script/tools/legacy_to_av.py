"""Convert an old-style script .docx (loose [EKRAN: …] lines, no A/V tables) into the A/V template.

- front matter (everything before the first chapter heading) is copied as-is: paragraphs, headings,
  lists and tables keep their structure
- chapter Heading2/Heading3 stay headings; each heading gets one GÖRÜNTÜ | SES table
- an "[EKRAN: x]" paragraph starts a row with GÖRÜNTÜ "[TAG] x", tags from `tags` by EKRAN number
  (1-based) or GRAFİK; its SES is the next paragraph, or the whole next table flattened (the table is what it shows)
- other consecutive paragraphs (and flattened tables) merge into one KAMERA row (empty GÖRÜNTÜ)
- the Kaynakça section becomes a heading plus list items

Usage: python3 templates/script/tools/legacy_to_av.py old.docx out.docx ['{"5": ["STOK", "YAZI"]}']
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from build_template import HEADER, WIDTHS  # noqa: E402
from docx_build import build_docx  # noqa: E402
from script_doc import _chapter_start, read_blocks  # noqa: E402

STOP = ("Kaynakça", "Kaynaklar")
PAGE = sum(WIDTHS)


def _lines(rows):
    """A table flattened the way the old docx_to_text did: every cell paragraph, row by row."""
    return [line for row in rows for cell in row for line in cell.split("\n")]


def _visual_cell(row):
    return "" if row["tags"] == ["KAMERA"] else f"[{', '.join(row['tags'])}] {row['visual']}"


def legacy_to_av(src_docx, docx_out, tags=None):
    tags = {int(k): v for k, v in (tags or {}).items()}
    blocks = read_blocks(src_docx)
    start = _chapter_start(blocks)
    out = []
    for b in blocks[:start]:
        if b[0] == "tbl":
            n = max(len(r) for r in b[1])
            out.append(("tbl", [r + [""] * (n - len(r)) for r in b[1]], [PAGE // n] * n))
        elif b[1] == "Heading1":
            out.append(("p", "Title", b[2]))
        elif b[3]:
            out.append(("li", b[2]))
        else:
            out.append(("p", b[1] if b[1] in ("Title", "Heading2", "Heading3") else None, b[2]))

    rows, in_refs, ekran = [], False, 0

    def flush():
        if rows:
            out.append(("tbl", [HEADER] + [[_visual_cell(r), "\n".join(r["ses"])] for r in rows], WIDTHS))
            rows.clear()

    def add_ses(lines):
        last = rows[-1] if rows else None
        if last and last["open"]:
            last["ses"].extend(lines)
            last["open"] = False
        elif last and last["tags"] == ["KAMERA"]:
            last["ses"].extend(lines)
        else:
            rows.append({"tags": ["KAMERA"], "visual": "", "ses": list(lines), "open": False})

    for b in blocks[start:]:
        if b[0] == "tbl":
            if not in_refs:
                add_ses([line for line in _lines(b[1]) if line.strip()])
            continue
        _, style, text, is_list = b
        if style in ("Heading2", "Heading3"):
            flush()
            in_refs = text.strip().startswith(STOP)
            out.append(("p", style, text))
        elif not text.strip():
            continue
        elif in_refs:
            out.append(("li", text) if is_list else ("p", None, text))
        elif text.startswith("[EKRAN"):
            ekran += 1
            visual = re.sub(r"^\[EKRAN:?\s*", "", text).rstrip()
            rows.append({"tags": tags.get(ekran, ["GRAFİK"]), "visual": visual[:-1] if visual.endswith("]") else visual,
                         "ses": [], "open": True})
        else:
            add_ses([text])
    flush()
    build_docx(out, docx_out)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    legacy_to_av(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) == 4 else None)
    print("wrote", sys.argv[2])
