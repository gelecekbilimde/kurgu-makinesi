"""Minimal .docx writer (stdlib only) for the script template and the reader's test fixtures.

build_docx(blocks, path, extra_styles=None) where each block is:
  ("p", style_id | None, text)   paragraph; style ids: Title, Heading1-3, ListParagraph (+ extra_styles)
  ("li", text)                   list item (ListParagraph style + numbering)
  ("tbl", rows, widths_twips)    table; rows = [[cell text]]; "\n" in a cell = separate paragraphs;
                                 a cell starting with "\x00sdt:" is wrapped in a w:sdt content control
Output is byte-reproducible (fixed zip timestamps).
"""
import zipfile
from xml.sax.saxutils import escape

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_STYLES = {"Title": "Title", "Heading1": "heading 1", "Heading2": "heading 2", "Heading3": "heading 3",
           "ListParagraph": "List Paragraph"}

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""
_NUMBERING = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{W_NS}">
<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>
<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>"""
_HEAD_SIZE = {"Title": 40, "Heading1": 32, "Heading2": 28, "Heading3": 24}


def _styles_xml(extra):
    out = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles xmlns:w="{W_NS}">',
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>']
    for sid, name in list(_STYLES.items()) + list((extra or {}).items()):
        size = _HEAD_SIZE.get(sid, 28 if name.lower().startswith("heading") else 0)
        rpr = f'<w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr>' if size else ""
        out.append(f'<w:style w:type="paragraph" w:styleId="{escape(sid)}"><w:name w:val="{escape(name)}"/>'
                   f'<w:basedOn w:val="Normal"/>{rpr}</w:style>')
    out.append("</w:styles>")
    return "\n".join(out)


def _p(text, style=None, numbered=False):
    ppr = ""
    if style or numbered:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{escape(style)}"/>' if style else "") + \
              ('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' if numbered else "") + "</w:pPr>"
    run = f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>' if text else ""
    return f"<w:p>{ppr}{run}</w:p>"


def _cell(text, width):
    body = "".join(_p(line) for line in text.split("\n"))
    if text.startswith("\x00sdt:"):
        body = f'<w:sdt><w:sdtPr><w:dropDownList/></w:sdtPr><w:sdtContent>{_p(text[5:])}</w:sdtContent></w:sdt>'
    return f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>{body}</w:tc>'


def _tbl(rows, widths):
    border = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
                     for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    trs = "".join("<w:tr>" + "".join(_cell(c, w) for c, w in zip(r, widths)) + "</w:tr>" for r in rows)
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblBorders>{border}</w:tblBorders>'
            f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{trs}</w:tbl>')


def build_docx(blocks, path, extra_styles=None):
    body = []
    for b in blocks:
        if b[0] == "p":
            body.append(_p(b[2], b[1]))
        elif b[0] == "li":
            body.append(_p(b[1], "ListParagraph", numbered=True))
        elif b[0] == "tbl":
            body.append(_tbl(b[1], b[2]))
            body.append(_p(""))          # Word/Google need a paragraph between consecutive tables
        else:
            raise ValueError(f"unknown block {b[0]!r}")
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{W_NS}"><w:body>'
           + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>')
    parts = [("[Content_Types].xml", _CONTENT_TYPES), ("_rels/.rels", _RELS), ("word/document.xml", doc),
             ("word/_rels/document.xml.rels", _DOC_RELS), ("word/styles.xml", _styles_xml(extra_styles)),
             ("word/numbering.xml", _NUMBERING)]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts:
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data.encode("utf-8"),
                       compress_type=zipfile.ZIP_DEFLATED)
