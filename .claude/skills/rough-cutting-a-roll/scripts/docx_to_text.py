# Extract paragraphs from a .docx (no dependencies). Usage: python3 docx_to_text.py in.docx out.txt
import re, sys, zipfile, xml.etree.ElementTree as ET
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
root = ET.fromstring(zipfile.ZipFile(sys.argv[1]).read("word/document.xml"))
paras = []
for p in root.iter("{%s}p" % NS["w"]):
    txt = "".join((t.text or "") for t in p.iter("{%s}t" % NS["w"]))
    style = p.find("w:pPr/w:pStyle", NS)
    paras.append(("[%s] " % style.get("{%s}val" % NS["w"]) if style is not None else "") + txt)
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(paras))
print(len(paras), "paragraphs,", sum(len(p.split()) for p in paras), "words")
