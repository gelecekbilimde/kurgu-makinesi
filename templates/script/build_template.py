"""Generate script-template.docx, the starting point of the Google Docs master template.

The master itself is assembled by hand from this file (see README.md, "Rebuild the master").
Usage: python3 templates/script/build_template.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from docx_build import build_docx  # noqa: E402

HEADER = ["GÖRÜNTÜ", "SES"]
WIDTHS = [3600, 5400]                      # 40 / 60 % of 9,000 twips
TAG_HINT = ("GÖRÜNTÜ hücresine bir etiketle başlayın: [KAMERA], [STOK], [ARŞİV], [GRAFİK], [YAZI], [KAYNAK]. "
            "Ekranda yalnızca sunucu olacaksa hücreyi boş bırakın.")
FIELDS = [["Başlık", ""], ["Sunucu", ""], ["Yazar", ""], ["Tarih", ""], ["Durum", "taslak"]]

BLOCKS = [
    ("tbl", FIELDS, [2200, 6800]),
    ("p", None, TAG_HINT),
    ("p", "Heading2", "1. Açılış (Sunucu adı)"),
    ("tbl", [HEADER,
             ["[GRAFİK] İki çubuk büyüyerek gelir: “Gereken: %55–60” ve “Vaat edilen: ~%15”. Veri: K1, s. 3",
              "Bilim insanlarına göre salımların 2035'e kadar yüzde 55–60 düşmesi gerekiyor. "
              "Vaatler ise yalnızca yüzde 15'lik bir düşüş getiriyor."],
             ["", "Merhaba, Gelecek Bilimde'ye hoş geldiniz. Bugün COP31'i konuşacağız."]],
     WIDTHS),
    ("p", "Heading3", "1.1 Alt başlık"),
    ("tbl", [HEADER, ["", ""]], WIDTHS),
    ("p", "Heading2", "Kaynakça"),
    ("li", "Yazar (Yıl). Başlık. Bağlantı"),
]

if __name__ == "__main__":
    out = os.path.join(HERE, "script-template.docx")
    build_docx(BLOCKS, out)
    print("wrote", out)
