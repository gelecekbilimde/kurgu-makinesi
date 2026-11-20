import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import rules  # noqa: E402

P31 = ("İşte zirvenin en çarpıcı rakamı. Bilim insanlarına göre 1,5 dereceye yakın kalmak için küresel salımların "
       "2035'e kadar 2019'a göre yüzde 55–60 düşmesi gerekiyor. Ülkelerin şu ana kadarki bütün vaatleri tam "
       "uygulansa bile düşüş yalnızca yüzde 15 civarında kalıyor.")                       # 38 words
P20 = ("Uluslararası uçuşlar ve deniz taşımacılığı hiçbir ülkenin sınırına tam sığmıyor. Bu yüzden kuralları "
       "COP'ta değil, BM'nin iki ayrı kuruluşunda yazılıyor.")                             # 20 words
P10 = "Masada 198 taraf var: 197 ülke ve Avrupa Birliği. Peki."                               # 10 words
P6 = "Türkçesi: Taraflar Konferansı. Bunu hatırlayın lütfen."                                 # 6 words


class Rules(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((rules.MIN_S, rules.SHOT_S, rules.LONG_S, rules.YAZI_WPS), (2, 7, 15, 3))
        self.assertEqual(rules.TAGS, ("KAMERA", "STOK", "ARŞİV", "GRAFİK", "YAZI", "KAYNAK"))
        self.assertEqual(list(rules.WARN), ["too_short", "many_shots", "long", "yazi_short", "source_missing", "no_tag"])
        self.assertEqual(rules.WARN["too_short"], "çok kısa: komşu satırla birleştir")
        self.assertEqual(rules.WARN["source_missing"], "kaynak eksik")

    def test_fold(self):
        for raw, want in [("Görüntü", "GORUNTU"), ("  EKRAN   süresi ", "EKRAN SURESI"), ("ı i İ I", "I I I I")]:
            with self.subTest(raw):
                self.assertEqual(rules.fold(raw), want)

    def test_normalize_tag(self):
        for raw, want in [("stok", "STOK"), ("Stok ", "STOK"), ("STOCK", "STOK"), ("arşiv", "ARŞİV"),
                          ("ARSIV", "ARŞİV"), ("Grafik", "GRAFİK"), ("GRAFIK", "GRAFİK"), ("film", None)]:
            with self.subTest(raw):
                self.assertEqual(rules.normalize_tag(raw), want)

    def test_yz_is_unknown(self):
        self.assertEqual(rules.split_visual("[YZ] bir galaksi"), ([], ["YZ"], "bir galaksi"))

    def test_split_visual(self):
        for cell, want in [
            ("[STOK] uzakta kalkan roket", (["STOK"], [], "uzakta kalkan roket")),
            ("[STOK, YAZI] uçak, üstünde “ICAO”", (["STOK", "YAZI"], [], "uçak, üstünde “ICAO”")),
            ("[stok + yazı] uçak", (["STOK", "YAZI"], [], "uçak")),
            ("[GRAFIK][YAZI] çubuklar", (["GRAFİK", "YAZI"], [], "çubuklar")),
            ("  [grafik]   çubuklar", (["GRAFİK"], [], "çubuklar")),
            ("[KAMERA]", (["KAMERA"], [], "")),
            ("", (["KAMERA"], [], "")),
            ("uzakta kalkan roket", ([], [], "uzakta kalkan roket")),
            ("[film] sahne", ([], ["film"], "sahne")),
            ("roket [STOK]", ([], [], "roket [STOK]")),
        ]:
            with self.subTest(cell):
                self.assertEqual(rules.split_visual(cell), want)

    def test_count_words(self):
        for ses, want in [("COP (kap), \"Conference of the Parties\" demek.", 6),
                          ("yüzde 55–60 düşmesi — gerekiyor", 4), (P31, 38), (P20, 20), (P10, 10), (P6, 6), ("", 0)]:
            with self.subTest(ses[:20]):
                self.assertEqual(rules.count_words(ses), want)

    def test_estimate_s(self):
        for words, rate, want in [(38, 2.2, 17), (1, 2.2, 0), (11, 2.2, 5), (12, 2.2, 5), (13, 2.2, 6), (10, 1.0, 10)]:
            with self.subTest(words=words, rate=rate):
                self.assertEqual(rules.estimate_s(words, rate), want)

    def test_check_row(self):
        q10 = "“Taraflar Konferansı: 197 ülke ve Avrupa Birliği, 1995'ten beri toplanıyor”"
        q8 = "“Taraflar Konferansı: 197 ülke ve Avrupa Birliği toplanıyor”"
        for tags, visual, ses, rate, want in [
            (["GRAFİK"], "İki çubuk", P31, 2.2, (17, ["long", "source_missing"])),
            (["GRAFİK"], "İki çubuk: %55–60 ve ~%15", P31, 2.2, (17, ["long"])),
            (["GRAFİK"], "Zaman çizelgesi, K3 s. 12", P10, 2.2, (5, [])),
            (["STOK"], "roket", P20, 2.2, (9, ["many_shots"])),
            (["KAMERA"], "", "Peki.", 2.2, (0, ["too_short"])),
            (["KAMERA"], "", P31, 1.0, (38, [])),
            (["YAZI"], q10, P6, 2.2, (3, ["yazi_short"])),
            (["YAZI"], q8, P6, 2.2, (3, [])),
            (["KAYNAK"], "makale ekran görüntüsü", P10, 2.2, (5, ["source_missing"])),
            (["KAYNAK"], "makale https://unfccc.int/cop31", P10, 2.2, (5, [])),
            ([], "", P10, 2.2, (5, ["no_tag"])),
            (["GRAFİK"], "başlık kartı", "", 2.2, (None, ["source_missing"])),
            (["KAMERA"], "", "", 2.2, (None, [])),
        ]:
            with self.subTest(tags=tags, visual=visual[:20], rate=rate):
                self.assertEqual(rules.check_row(tags, visual, ses, rate), {"seconds": want[0], "warnings": want[1]})


if __name__ == "__main__":
    unittest.main()
