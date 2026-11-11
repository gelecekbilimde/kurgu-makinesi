import json, os, subprocess, sys, tempfile, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PKG))
sys.path.insert(0, PKG)
from docx_build import build_docx  # noqa: E402
import script_doc  # noqa: E402

HDR = ["GÖRÜNTÜ", "SES"]
WID = [3600, 5400]
COP_DOCX = os.path.join(REPO, "demo/cop/raw/COP31_YouTube_Senaryosu.docx")
COP_TXT = os.path.join(REPO, "episodes/cop31/script.txt")


def template_blocks():
    return [
        ("tbl", [["Başlık", "COP31 deneme"], ["Sunucu", "Begüm Dursun"], ["Durum", "taslak"]], [2200, 6800]),
        ("p", "Heading2", "1. Açılış (Begüm Dursun)"),
        ("p", "Heading3", "COP nedir?"),
        ("tbl", [HDR,
                 ["[GRAFİK] Zaman çizelgesi, K2 s. 4", "Masada 198 taraf var: 197 ülke ve Avrupa Birliği."],
                 ["", "Peki bu zirveler neden bu kadar önemli?"],
                 ["[STOK, YAZI] Uzakta kalkan uçak, üstünde “ICAO” https://example.org/a",
                  "Uluslararası uçuşlar hiçbir ülkenin sınırına tam sığmıyor."]], WID),
        ("p", "Heading2", "Kaynakça"),
        ("li", "UNFCCC (2026). The road to Antalya."),
        ("li", "IPCC (2023). AR6 Synthesis Report."),
    ]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def with_br(path, marker="⏎"):
    """Rewrite document.xml so that `marker` becomes a real <w:br/> inside the run."""
    z = zipfile.ZipFile(path)
    parts = {n: z.read(n) for n in z.namelist()}
    z.close()
    parts["word/document.xml"] = parts["word/document.xml"].decode().replace(
        marker, '</w:t><w:br/><w:t xml:space="preserve">').encode()
    with zipfile.ZipFile(path, "w") as out:
        for n, data in parts.items():
            out.writestr(n, data)


def with_hyperlink(path, marker, text, url):
    """Replace `marker` with a Google-style titled hyperlink (w:hyperlink r:id; URL only in the rels)."""
    z = zipfile.ZipFile(path)
    parts = {n: z.read(n) for n in z.namelist()}
    z.close()
    doc = parts["word/document.xml"].decode()
    doc = doc.replace('<w:document xmlns:w=', '<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
                      '2006/relationships" xmlns:w=', 1)
    doc = doc.replace(marker + "</w:t></w:r>", '</w:t></w:r><w:hyperlink r:id="rIdL1"><w:r><w:t>' + text +
                      "</w:t></w:r></w:hyperlink>")
    parts["word/document.xml"] = doc.encode()
    rels = parts["word/_rels/document.xml.rels"].decode()
    parts["word/_rels/document.xml.rels"] = rels.replace("</Relationships>", '<Relationship Id="rIdL1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="' + url +
        '" TargetMode="External"/></Relationships>').encode()
    with zipfile.ZipFile(path, "w") as out:
        for n, data in parts.items():
            out.writestr(n, data)


class ScriptDoc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def build(self, blocks, name="s.docx", **kw):
        path = os.path.join(self.tmp.name, name)
        build_docx(blocks, path, **kw)
        return path

    def test_template_rows(self):
        s = script_doc.parse(self.build(template_blocks()))
        self.assertEqual(s["format"], "av-1")
        self.assertEqual(s["title"], "COP31 deneme")
        self.assertEqual(s["header"], {"Başlık": "COP31 deneme", "Sunucu": "Begüm Dursun", "Durum": "taslak"})
        self.assertEqual(s["front"], [])
        self.assertEqual(s["headings"], [{"level": 2, "title": "1. Açılış (Begüm Dursun)"},
                                         {"level": 3, "title": "COP nedir?"}])
        self.assertEqual([r["id"] for r in s["rows"]], ["R001", "R002", "R003"])
        self.assertEqual([r["heading"] for r in s["rows"]], [1, 1, 1])
        r1, r2, r3 = s["rows"]
        self.assertEqual(r1["tags"], ["GRAFİK"])
        self.assertEqual(r1["visual"], "Zaman çizelgesi, K2 s. 4")
        self.assertEqual(r2["tags"], ["KAMERA"])
        self.assertEqual(r2["visual"], "")
        self.assertEqual(r1["refs"], ["K2"])
        self.assertEqual(r3["tags"], ["STOK", "YAZI"])
        self.assertEqual(r3["links"], ["https://example.org/a"])
        self.assertEqual(len(r1["key"]), 8)
        self.assertNotEqual(r1["key"], r2["key"])
        self.assertEqual([k["k"] for k in s["kaynakca"]], [1, 2])
        self.assertEqual(s["kaynakca"][1]["text"], "IPCC (2023). AR6 Synthesis Report.")
        self.assertEqual([r["warnings"] for r in s["rows"]], [[], [], []])
        self.assertEqual(s["speaker"], {"name": "Begüm Dursun", "rate": 2.2, "source": "script", "known": False})
        self.assertEqual([r["est_s"] for r in s["rows"]], [4, 3, 3])     # 9, 7, 7 words at 2.2 w/s
        self.assertEqual(s["total_s"], 10)
        self.assertEqual(s["notes"], [])

    def test_speaker_resolution(self):
        path = self.build(template_blocks())
        speakers = {"default": 2.0, "speakers": {"Burak Cankaya": 1.0, "Begüm Dursun": 3.0}}
        s = script_doc.parse(path, speakers=speakers)                       # from the header's Sunucu
        self.assertEqual(s["speaker"], {"name": "Begüm Dursun", "rate": 3.0, "source": "script", "known": True})
        s = script_doc.parse(path, speaker="burak cankaya", speaker_source="episode", speakers=speakers)
        self.assertEqual(s["speaker"], {"name": "Burak Cankaya", "rate": 1.0, "source": "episode", "known": True})
        self.assertEqual(s["rows"][0]["est_s"], 9)                          # 9 words at 1.0 w/s
        s = script_doc.parse(path, speaker="Yeni Kişi", speaker_source="cli", speakers=speakers)
        self.assertEqual(s["speaker"], {"name": "Yeni Kişi", "rate": 2.0, "source": "cli", "known": False})

    def test_front_matter(self):
        s = script_doc.parse(self.build([
            ("tbl", [["Başlık", "Bölüm"], ["Sunucu", "Burak Cankaya"]], [2200, 6800]),
            ("p", None, "Etiketler: [STOK] [GRAFİK]"),
            ("p", None, "Oct 25, 2026 · yazar"),
            ("p", "Heading2", "Düzeltme notları"),
            ("p", None, "Paris: 1,5°C hedefi netleştirildi"),
            ("tbl", [["Orijinal ifade", "Sorun"], ["11 günlük", "12 gün eder"]], [4500, 4500]),
            ("p", None, "Senaryo notu: görsel öneriler"),
            ("p", "Heading2", "1. Giriş"),
            ("tbl", [HDR, ["", "Merhaba, bugün iklim zirvesini birlikte konuşacağız."]], WID)]))
        self.assertEqual(s["header"], {"Başlık": "Bölüm", "Sunucu": "Burak Cankaya"})
        self.assertEqual(s["title"], "Bölüm")
        self.assertEqual(s["headings"], [{"level": 2, "title": "1. Giriş"}])
        self.assertEqual(s["notes"], [])
        self.assertEqual(s["front"], ["Etiketler: [STOK] [GRAFİK]", "Oct 25, 2026 · yazar", "Düzeltme notları", "Paris: 1,5°C hedefi netleştirildi",
                                      "Orijinal ifade | Sorun", "11 günlük | 12 gün eder", "Senaryo notu: görsel öneriler"])
        self.assertEqual(len(s["rows"]), 1)

    def test_guide_tab_after_kaynakca_ignored(self):
        """Google's .docx export appends every tab, so the Kılavuz tab follows the Kaynakça."""
        blocks = template_blocks() + [
            ("p", "Heading1", "Senaryo şablonu kılavuzu"),
            ("p", "Heading2", "Sütunlar"),
            ("p", None, "GÖRÜNTÜ: köşeli parantez içinde bir etiketle başlar."),
            ("li", "SES: sunucunun okuyacağı metin."),
            ("tbl", [["Etiket", "Anlamı", "Olmalı"], ["[STOK]", "dış görüntü", "tarif"]], [3000, 3000, 3000]),
            ("tbl", [HDR, ["[STOK] örnek", "Bu bir kılavuz örneğidir, senaryo değildir."]], WID)]
        s = script_doc.parse(self.build(blocks))
        self.assertEqual(s["title"], "COP31 deneme")
        self.assertEqual([h["title"] for h in s["headings"]], ["1. Açılış (Begüm Dursun)", "COP nedir?"])
        self.assertEqual(len(s["rows"]), 3)
        self.assertEqual(len(s["kaynakca"]), 2)
        self.assertEqual(s["notes"], [])

    def test_heading1_ends_script_without_kaynakca(self):
        s = script_doc.parse(self.build([
            ("p", "Heading2", "1. Giriş"),
            ("tbl", [HDR, ["", "Merhaba, bugün iklim zirvesini birlikte konuşacağız."]], WID),
            ("p", "Heading1", "Senaryo şablonu kılavuzu"),
            ("p", "Heading2", "Sütunlar"),
            ("tbl", [HDR, ["[STOK] örnek", "Bu bir kılavuz örneğidir."]], WID)]))
        self.assertEqual([h["title"] for h in s["headings"]], ["1. Giriş"])
        self.assertEqual(len(s["rows"]), 1)

    def test_cli_prints_notes(self):
        path, out = self.build([("p", "Heading2", "1. Giriş"),
                                ("tbl", [HDR, ["[ANİMASYON] dönen dünya", "Merhaba, bugün iklim zirvesini konuşacağız."]], WID),
                                ("p", None, "Bu cümle tablonun dışında kaldı.")]), self.tmp.name
        res = subprocess.run([sys.executable, os.path.join(PKG, "script_doc.py"), path, out], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("bilinmeyen TÜR: ANİMASYON", res.stdout)
        self.assertIn("Bu cümle tablonun dışında kaldı.", res.stdout)

    def test_headerless_table_read_with_warning(self):
        s = script_doc.parse(self.build([
            ("p", "Heading2", "1. Giriş"),
            ("tbl", [HDR, ["", "Merhaba, bugün iklim zirvesini konuşacağız."]], WID),
            ("p", "Heading2", "2. Zirve"),
            ("tbl", [["[STOK] roket", "Birinci cümle burada okunuyor."], ["", "İkinci cümle de burada okunuyor."]], WID)]))
        self.assertEqual([(r["heading"], r["tags"]) for r in s["rows"]], [(0, ["KAMERA"]), (1, ["STOK"]), (1, ["KAMERA"])])
        self.assertEqual(len(s["notes"]), 1)
        self.assertIn("başlık satırı yok", s["notes"][0]["text"])

    def test_heading1_stop_is_reported(self):
        s = script_doc.parse(self.build([
            ("p", "Heading2", "1. Giriş"),
            ("tbl", [HDR, ["", "Merhaba, bugün iklim zirvesini konuşacağız."]], WID),
            ("p", "Heading1", "2. Zirve"),
            ("tbl", [HDR, ["", "Bu bölüm okunmaz çünkü yanlış başlık stili."]], WID)]))
        self.assertEqual(len(s["rows"]), 1)
        self.assertEqual(len(s["notes"]), 1)
        self.assertIn("2. Zirve", s["notes"][0]["text"])
        self.assertIn("Başlık 1", s["notes"][0]["text"])

    def test_hyperlink_target_is_read(self):
        path = self.build([("p", "Heading2", "1. Giriş"),
                           ("tbl", [HDR, ["[KAYNAK] LINKMARK", "Merhaba, bugün iklim zirvesini konuşacağız."]], WID)])
        with_hyperlink(path, "LINKMARK", "Nature makalesi", "https://www.nature.com/articles/x")
        r = script_doc.parse(path)["rows"][0]
        self.assertEqual(r["links"], ["https://www.nature.com/articles/x"])
        self.assertEqual(r["warnings"], [])
        self.assertIn("Nature makalesi", r["visual"])

    def test_heading_by_style_name(self):
        path = self.build([("p", "Balk2", "1. Giriş"), ("tbl", [HDR, ["", "Merhaba dünya bugün."]], WID)],
                          extra_styles={"Balk2": "heading 2"})
        s = script_doc.parse(path)
        self.assertEqual(s["headings"], [{"level": 2, "title": "1. Giriş"}])
        self.assertEqual(s["rows"][0]["heading"], 0)

    def test_multi_paragraph_br_sdt(self):
        path = self.build([("p", "Heading2", "1. Giriş"),
                           ("tbl", [HDR, ["\x00sdt:[STOK] roket", "Birinci paragraf iki.\nİkinci⏎paragraf"]], WID)])
        with_br(path)
        r = script_doc.parse(path)["rows"][0]
        self.assertEqual((r["tags"], r["visual"]), (["STOK"], "roket"))
        self.assertEqual(r["ses"], "Birinci paragraf iki.\nİkinci\nparagraf")

    def test_empty_rows_skipped(self):
        s = script_doc.parse(self.build([("p", "Heading2", "1. Giriş"),
                                         ("tbl", [HDR, ["", "Merhaba, bugün iklim zirvesini birlikte konuşacağız."], ["", ""]], WID)]))
        self.assertEqual(len(s["rows"]), 1)
        self.assertEqual(s["rows"][0]["warnings"], [])

    def test_notes_and_h2_table(self):
        s = script_doc.parse(self.build([
            ("p", "Heading2", "1. Giriş"),
            ("tbl", [HDR, ["", "Merhaba dünya bugün."]], WID),
            ("p", None, "Not: bu kısım kısaltılabilir."),
            ("tbl", [HDR, ["", "Devam ediyoruz şimdi."]], WID)]))
        self.assertEqual(s["notes"], [{"heading": 0, "text": "Not: bu kısım kısaltılabilir."}])
        self.assertEqual([r["heading"] for r in s["rows"]], [0, 0])
        self.assertFalse(any("Not:" in r["ses"] for r in s["rows"]))

    def test_unknown_tag_becomes_note(self):
        s = script_doc.parse(self.build([("p", "Heading2", "1. Giriş"),
                                         ("tbl", [HDR, ["[film, STOK] roket", "Merhaba dünya bugün."]], WID)]))
        self.assertEqual(s["rows"][0]["tags"], ["STOK"])
        self.assertEqual(len(s["notes"]), 1)
        self.assertIn("film", s["notes"][0]["text"])

    def test_unknown_column_ignored(self):
        s = script_doc.parse(self.build([("p", "Heading2", "1. Giriş"),
                                         ("tbl", [["TÜR"] + HDR + ["EKRAN SÜRESİ"], ["STOK", "", "Merhaba dünya bugün.", "4 sn"]],
                                          [900] + WID + [900])]))
        self.assertEqual(s["rows"][0]["ses"], "Merhaba dünya bugün.")
        self.assertEqual(s["rows"][0]["tags"], ["KAMERA"])        # a TÜR column is ignored, not read

    def test_visual_tags(self):
        s = script_doc.parse(self.build([("p", "Heading2", "1. Giriş"), ("tbl", [HDR,
            ["[YAZI][stok] uçak, üstünde “ICAO”", "Merhaba, bugün iklim zirvesini birlikte konuşacağız."],
            ["[KAMERA]", "Devam ediyoruz ve şimdi asıl konuya geçiyoruz."],
            ["uzakta kalkan bir roket", "Peki bu zirveler neden bu kadar önemli sizce?"]], WID)]))
        r1, r2, r3 = s["rows"]
        self.assertEqual((r1["tags"], r1["visual"]), (["YAZI", "STOK"], "uçak, üstünde “ICAO”"))
        self.assertEqual((r2["tags"], r2["visual"], r2["warnings"]), (["KAMERA"], "", []))
        self.assertEqual((r3["tags"], r3["visual"], r3["warnings"]), ([], "uzakta kalkan bir roket", ["no_tag"]))

    def test_legacy_table_not_template(self):
        path = self.build([("p", "Heading2", "1. Giriş"), ("p", None, "metin"),
                           ("tbl", [["Yıl", "Zirve"], ["1997", "Kyoto"]], [4000, 4000])])
        self.assertIsNone(script_doc.parse(path))
        txt = script_doc.legacy_text(path)
        self.assertTrue(txt.startswith("[Heading2] 1. Giriş\nmetin\nYıl\nZirve\n1997\nKyoto"))

    @unittest.skipUnless(os.path.exists(COP_DOCX) and os.path.exists(COP_TXT), "COP31 files not present")
    def test_legacy_identical_cop31(self):
        self.assertEqual(script_doc.legacy_text(COP_DOCX), read(COP_TXT))

    def test_legacy_txt_shape(self):
        lines = script_doc.to_legacy_txt(script_doc.parse(self.build(template_blocks()))).splitlines()
        i = lines.index("[EKRAN: GRAFİK: Zaman çizelgesi, K2 s. 4]")
        self.assertEqual(lines[i + 1], "Masada 198 taraf var: 197 ülke ve Avrupa Birliği.")
        self.assertEqual(lines[:2], ["[Heading2] 1. Açılış (Begüm Dursun)", "[Heading3] COP nedir?"])
        self.assertIn("[EKRAN: STOK+YAZI: Uzakta kalkan uçak, üstünde “ICAO” https://example.org/a]", lines)
        self.assertNotIn("[EKRAN: KAMERA", "\n".join(lines))
        self.assertEqual(lines[-3:], ["[Heading2] Kaynakça", "[ListParagraph] UNFCCC (2026). The road to Antalya.",
                                      "[ListParagraph] IPCC (2023). AR6 Synthesis Report."])

    def test_cli_writes_files(self):
        blocks = template_blocks()
        next(b for b in blocks if b[0] == "tbl" and b[1][0] == HDR)[1].append(["roket fırlatma", "Peki."])
        path, out = self.build(blocks), os.path.join(self.tmp.name, "ep")
        os.makedirs(out)
        with open(os.path.join(out, "episode.json"), "w", encoding="utf-8") as f:
            json.dump({"speaker": "Burak Cankaya"}, f)
        res = subprocess.run([sys.executable, os.path.join(PKG, "script_doc.py"), path, out, "--prompter"],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Tahmini toplam (yazıldığı gibi): 0:10", res.stdout)
        self.assertIn("Sunucu: Burak Cankaya (episode.json", res.stdout)
        self.assertIn("R004", res.stdout)                      # only warned rows are listed
        self.assertIn("TÜR seçilmedi", res.stdout)
        self.assertNotIn("R002", res.stdout)
        data = json.loads(read(os.path.join(out, "script.json")))
        self.assertEqual(len(data["rows"]), 4)
        self.assertTrue(read(os.path.join(out, "script.txt")).startswith("[Heading2]"))
        prompter = read(os.path.join(out, "prompter.txt"))
        self.assertNotIn("[", prompter)
        self.assertIn("COP nedir?\n\nMasada 198 taraf", prompter)

    def test_cli_legacy(self):
        path, out = self.build([("p", "Heading2", "1. Giriş"), ("p", None, "metin")]), self.tmp.name
        res = subprocess.run([sys.executable, os.path.join(PKG, "script_doc.py"), path, out],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("legacy script (no A/V tables)", res.stdout)
        self.assertEqual(read(os.path.join(out, "script.txt")), "[Heading2] 1. Giriş\nmetin")
        res = subprocess.run([sys.executable, os.path.join(PKG, "script_doc.py"), path, out, "--prompter"],
                             capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
