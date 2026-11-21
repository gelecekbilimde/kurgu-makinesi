import unittest
import helpers  # noqa: F401  (sys.path)
import captions
from rows import Row


def row(ses):
    return Row(id="r", key="k", chapter=0, tags=[], visual="", ses=ses)


def w(text, start, end):
    return {"text": text, "start": start, "end": end}


def run(texts, start=0, dur=8, gap=2):
    out, t = [], start
    for x in texts:
        out.append(w(x, t, t + dur))
        t += dur + gap
    return out


class SpellTest(unittest.TestCase):
    def test_script_spelling_wins(self):
        words = run(["sıcaklık", "1,5", "derece", "cop31", "toplantısı"])
        rows = [row("Bu sıcaklık 1,5°C derece (duraklama) ve COP31'in toplantısı")]
        got = captions.spell(words, rows)
        self.assertEqual(got[1], "1,5°C")
        self.assertEqual(got[3], "COP31'in")
        self.assertEqual(got[0], "sıcaklık")

    def test_unmatched_keeps_transcript(self):
        words = run(["tamamen", "başka", "bir", "cümle"])
        self.assertEqual(captions.spell(words, [row("alakasız söz dizisi burada")]),
                         ["tamamen", "başka", "bir", "cümle"])


class CuesTest(unittest.TestCase):
    def test_line_and_cue_limits(self):
        words = run(["kelimeler"] * 30)
        cs = captions.cues(words, 25)
        self.assertGreater(len(cs), 1)
        for c in cs:
            lines = c["text"].split("\n")
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(all(len(l) <= 32 for l in lines))
        self.assertEqual(" ".join(c["text"].replace("\n", " ") for c in cs), " ".join(["kelimeler"] * 30))

    def test_break_on_pause(self):
        a, b = run(["bir", "iki"]), run(["üç", "dört"], start=100)
        cs = captions.cues(a + b, 25)
        self.assertEqual([c["text"] for c in cs], ["bir iki", "üç dört"])
        self.assertEqual(cs[0]["end"], a[1]["end"] + captions.POST_F)  # gap > 12: not extended

    def test_break_after_sentence_end_and_extend(self):
        ws = [w("Bitti.", 0, 10), w("Yeni", 16, 24)]
        cs = captions.cues(ws, 25)
        self.assertEqual([c["text"] for c in cs], ["Bitti.", "Yeni"])
        self.assertEqual(cs[0]["end"], 16)  # gap 6 <= 12: extended to next cue start
        self.assertEqual(cs[1]["end"], 24 + captions.POST_F)

    def test_no_cue_in_teaser_or_end_card(self):
        ws = run(["a"] * 6, start=0, dur=10, gap=0)  # 0..60
        cs = captions.cues(ws, 25, avoid=[(0, 25), (50, 60)])
        self.assertTrue(cs)
        for c in cs:
            for a, b in [(0, 25), (50, 60)]:
                self.assertTrue(c["end"] <= a or c["start"] >= b, (c, a, b))


class TeaserTest(unittest.TestCase):
    def test_teaser_words_relative(self):
        ws = [w("x", 0, 10), w("a", 40, 50), w("b", 52, 60), w("y", 90, 99)]
        self.assertEqual(captions.teaser_words(ws, [38, 70]),
                         [{"text": "a", "start": 2, "end": 12}, {"text": "b", "start": 14, "end": 22}])


class SrtTest(unittest.TestCase):
    def test_srt_format(self):
        s = captions.srt([{"start": 0, "end": 30, "text": "bir\niki"},
                          {"start": 3600 * 25 + 61 * 25 + 7, "end": 3600 * 25 + 62 * 25, "text": "son"}], 25)
        self.assertEqual(s, "1\n00:00:00,000 --> 00:00:01,200\nbir\niki\n\n"
                            "2\n01:01:01,280 --> 01:01:02,000\nson\n\n")


if __name__ == "__main__":
    unittest.main()
