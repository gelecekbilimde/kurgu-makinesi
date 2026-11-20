import json, shutil, tempfile, unittest
import helpers
from helpers import FIXTURES, make_episode
import align, episode
from rows import Row


def words_of(text, step=10):
    """one word every `step` frames, each 8 frames long"""
    return [(i * step, i * step + 8, align.norm(w)) for i, w in enumerate(text.split())]


def row(key, ses, tags=("STOK",)):
    return Row(id=key.upper(), key=key, chapter=1, tags=list(tags), visual="", ses=ses)


A = "karadelikler yıldızların çöküşüyle oluşur ve ışığı bile yutar"
B = "olay ufkunun ötesinden hiçbir bilgi bize ulaşamaz derler"
C = "hawking ise bu deliklerin yavaşça buharlaştığını gösterdi sonunda"


class LayoutTest(unittest.TestCase):
    def test_layout_from_items(self):
        class Item:
            def __init__(self, s, lo, d, n):
                self.s, self.lo, self.d, self.n = s, lo, d, n
            def GetStart(self): return self.s
            def GetLeftOffset(self): return self.lo
            def GetDuration(self): return self.d
            def GetMediaPoolItem(self):
                n = self.n
                class M:
                    def GetName(self): return n
                return M()
        import broll_resolve
        got = broll_resolve.layout_from_items(
            "TEST ch2 X", 86400, [Item(86500, 300, 130, "P1.MOV"), Item(86400, 100, 100, "P1.MOV")])
        self.assertEqual(got, {"units": "frames", "timeline": "TEST ch2 X", "frames": 230,
                               "pieces": [[0, "P1.MOV", 100, 200], [100, "P1.MOV", 300, 430]]})


class ChapterWordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = make_episode(self.tmp, clips=[{"clip": "P1.MOV", "offset_f": 10}, {"clip": "P2.MOV", "offset_f": -5}])
        shutil.copytree(FIXTURES / "transcripts", d / "transcripts")
        self.ep = episode.Episode(d)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_word_mapping_through_pieces(self):
        layout = json.loads((FIXTURES / "layout-ch2.json").read_text(encoding="utf-8"))
        got = align.chapter_words(self.ep, layout)
        # "kesik" lies in the cut-out part; "—" normalises to nothing; "Önce" starts before the piece (clamped)
        self.assertEqual(got, [(0, 7, "önce"), (10, 20, "merhaba"), (110, 116, "dünya"), (205, 211, "son")])

    def test_missing_offset_raises_with_clip(self):
        self.ep.m["clips"][1].pop("offset_f")
        layout = json.loads((FIXTURES / "layout-ch2.json").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError) as c:
            align.chapter_words(self.ep, layout)
        self.assertIn("P2.MOV", str(c.exception))


class AlignRowsTest(unittest.TestCase):
    def test_row_found_and_range(self):
        w = words_of("eee " + A + " aaa")
        got = align.align_rows([row("a", A)], w)
        self.assertEqual(got["a"], {"start": 10, "end": 88, "first_word": 1, "last_word": 8})

    def test_offscript_inside_row_stays_one_range(self):
        a = A.split()
        w = words_of(" ".join(a[:5] + ["şey", "yani", "nasıl", "desem"] + a[5:]))
        got = align.align_rows([row("a", A)], w)
        self.assertEqual((got["a"]["first_word"], got["a"]["last_word"]), (0, len(w) - 1))

    def test_ses_parentheses_ignored(self):
        w = words_of(A)
        got = align.align_rows([row("a", "(sakin) " + A + " (ka-ra-de-lik)")], w)
        self.assertEqual((got["a"]["first_word"], got["a"]["last_word"]), (0, 7))

    def test_repeated_sentence_two_rows_monotone(self):
        w = words_of(A + " " + B + " " + A)
        got = align.align_rows([row("a", A), row("b", B), row("c", A)], w)
        self.assertEqual((got["a"]["first_word"], got["a"]["last_word"]), (0, 7))
        self.assertEqual((got["b"]["first_word"], got["b"]["last_word"]), (8, 15))
        self.assertEqual((got["c"]["first_word"], got["c"]["last_word"]), (16, 23))

    def test_row_not_spoken_is_none(self):
        w = words_of(A + " " + C)
        got = align.align_rows([row("a", A), row("b", B), row("c", C)], w)
        self.assertIsNone(got["b"])
        self.assertEqual(got["c"]["first_word"], 8)

    def test_too_few_hits_is_none(self):
        long_b = B + " " + C  # 16 tokens: needs 5 covered, one 3-gram covers 3
        w = words_of("olay ufkunun ötesinden " + A)
        got = align.align_rows([row("b", long_b), row("a", A)], w)
        self.assertIsNone(got["b"])
        self.assertEqual(got["a"]["first_word"], 3)

    def test_paraphrased_ending_does_not_swallow_next_rows(self):
        a = "evren sürekli genişliyor ve uzaklaştıkça hızlanıyor bu da demek oluyor ki galaksiler kaçıyor"
        c = "sonuç olarak bu da demek oluyor ki zaman geriye akmaz"
        spoken = "evren sürekli genişliyor ve uzaklaştıkça hızlanıyor bu da demek oluyor işte"  # words 0..10
        w = words_of(spoken + " " + B + " " + c)  # B 11..18, c 19..28
        got = align.align_rows([row("a", a), row("b", B), row("c", c)], w)
        self.assertEqual((got["a"]["first_word"], got["a"]["last_word"]), (0, 9))
        self.assertEqual((got["b"]["first_word"], got["b"]["last_word"]), (11, 18))
        self.assertEqual((got["c"]["first_word"], got["c"]["last_word"]), (19, 28))

    def test_unspoken_short_row_does_not_jump_ahead(self):
        short = "uzay çok büyük bir yer"
        d = "evrende çok büyük bir boşluk var gerçekten"
        filler = " ".join(f"f{i}" for i in range(55))
        w = words_of(A + " " + B + " " + filler + " " + d)  # A 0..7, B 8..15, d 71..77
        got = align.align_rows([row("a", A), row("s", short), row("b", B), row("d", d)], w)
        self.assertIsNone(got["s"])
        self.assertEqual((got["b"]["first_word"], got["b"]["last_word"]), (8, 15))
        self.assertEqual((got["d"]["first_word"], got["d"]["last_word"]), (71, 77))


class CoverageTest(unittest.TestCase):
    def cov(self, text, rs):
        w = words_of(text)
        return align.coverage(rs, align.align_rows(rs, w), w)

    def test_coverage_runs_to_next_broll_row(self):
        rs = [row("a", A), row("b", B, ("GRAFİK",))]
        got = self.cov(A + " ıı öö " + B, rs)  # 2 words between
        self.assertEqual(got["a"], {"start": 0, "end": 100})
        self.assertEqual(got["b"], {"start": 100, "end": 178})

    def test_coverage_stops_before_kamera_row(self):
        rs = [row("a", A), row("k", B, ("KAMERA",))]
        got = self.cov(A + " " + B, rs)
        self.assertEqual(got, {"a": {"start": 0, "end": 78}})  # KAMERA rows are not in the output

    def test_mixed_kamera_row_is_covered_and_ends_at_its_last_word(self):
        rs = [row("a", A), row("m", B, ("KAMERA", "YAZI")), row("c", C)]
        got = self.cov(A + " " + B + " " + C, rs)
        self.assertEqual(got["a"], {"start": 0, "end": 78})  # no run-on into the presenter row
        self.assertEqual(got["m"], {"start": 80, "end": 158})  # its own last word, no run-on into c
        self.assertEqual(got["c"], {"start": 160, "end": 238})

    def test_coverage_stops_at_offscript_gap(self):
        rs = [row("a", A), row("b", B)]
        got = self.cov(A + " bir iki üç dört beş " + B, rs)  # 5 unmatched words between
        self.assertEqual(got["a"], {"start": 0, "end": 78})

    def test_last_row_ends_at_last_word(self):
        rs = [row("a", A), row("b", B)]
        got = self.cov(A + " " + B + " kapanış sözleri", rs)
        self.assertEqual(got["a"], {"start": 0, "end": 80})
        self.assertEqual(got["b"], {"start": 80, "end": 158})

    def test_coverage_skips_unfound_row(self):
        rs = [row("a", A), row("b", B), row("c", C)]
        got = self.cov(A + " " + C, rs)
        self.assertIsNone(got["b"])
        self.assertEqual(got["a"], {"start": 0, "end": 80})  # next FOUND row is c


class AlignCommandTest(unittest.TestCase):
    def test_align_writes_rows_json(self):
        import broll
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        d = make_episode(tmp, frozen=[2], clips=[{"clip": "P1.MOV", "offset_f": 0}])
        heads = [{"level": 2, "title": "1. Giriş"}, {"level": 2, "title": "2. Gelişme"}]
        rws = [{"id": "R001", "key": "k1", "heading": 0, "tags": ["STOK"], "ses": "x"},
               {"id": "R002", "key": "k2", "heading": 1, "tags": ["STOK"], "ses": A},
               {"id": "R003", "key": "k3", "heading": 1, "tags": ["KAMERA"], "ses": B},
               {"id": "R004", "key": "k4", "heading": 1, "tags": ["GRAFİK"], "ses": C}]
        (d / "script.json").write_text(json.dumps({"headings": heads, "rows": rws}), encoding="utf-8")
        (d / "sections.json").write_text(json.dumps({"chapters": ["1. Giriş", "2. Gelişme"]}), encoding="utf-8")
        ws = [{"start": "00:00:%02d:00" % i, "end": "00:00:%02d:10" % i, "text": t}
              for i, t in enumerate((A + " " + B).split())]
        (d / "transcripts").mkdir()
        (d / "transcripts" / "P1-wav-tr.json").write_text(
            json.dumps({"language": "tr", "segments": [{"start": "", "end": "", "text": "", "words": ws}]}),
            encoding="utf-8")
        (d / "broll" / "layout").mkdir(parents=True)
        (d / "broll" / "layout" / "ch2.json").write_text(json.dumps(
            {"units": "frames", "timeline": "TEST ch2 Gelişme", "frames": 400, "pieces": [[0, "P1.MOV", 0, 400]]}),
            encoding="utf-8")
        self.assertEqual(broll.main(["align", str(d)]), 0)
        got = json.loads((d / "broll" / "rows.json").read_text(encoding="utf-8"))
        self.assertEqual(got, {"units": "frames", "fps": 25, "chapters": {"2": {"timeline": "TEST ch2 Gelişme", "rows": {
            "k2": {"id": "R002", "start": 0, "end": 185}, "k4": None}}}})


if __name__ == "__main__":
    unittest.main()
