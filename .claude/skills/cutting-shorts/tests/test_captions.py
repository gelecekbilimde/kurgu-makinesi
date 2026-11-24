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
        words = run(["sıcaklık", "1,5", "derece", "ve", "cop31", "toplantısı"])
        rows = [row("Bu sıcaklık 1,5°C derece (duraklama) ve COP31'in toplantısı")]
        got = captions.spell(words, rows)
        self.assertEqual(got[1], "1,5°C")
        self.assertEqual(got[4], "COP31'in")
        self.assertEqual(got[0], "sıcaklık")

    def test_other_spoken_words_keep_the_transcript(self):
        """Final review 1: a different word said in place of the script's is never replaced by it."""
        words = run(["bu", "konu", "on", "yıl", "sürdü"])
        got = captions.spell(words, [row("Bunun konu onlarca yıl sürdü")])
        self.assertEqual(got, ["bu", "konu", "on", "yıl", "sürdü"])

    def test_unit_spoken_out_is_not_doubled(self):
        words = run(["artış", "1,5", "derece", "oldu"])
        got = captions.spell(words, [row("artış 1,5°C oldu")])
        self.assertEqual(got, ["artış", "1,5", "derece", "oldu"])

    def test_unit_suffix_alone_takes_the_script(self):
        words = run(["artış", "1,5", "oldu"])
        self.assertEqual(captions.spell(words, [row("artış 1,5°C oldu")]), ["artış", "1,5°C", "oldu"])
        words = run(["oran", "40", "oldu"])
        self.assertEqual(captions.spell(words, [row("oran 40% oldu")])[1], "40%")

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
            self.assertTrue(all(len(l) <= captions.MAX_CHARS for l in lines))
        self.assertEqual(" ".join(c["text"].replace("\n", " ") for c in cs), " ".join(["kelimeler"] * 30))

    def test_break_on_pause(self):
        a, b = run(["bir", "iki"], dur=20), run(["üç", "dört"], start=100, dur=20)
        cs = captions.cues(a + b, 25)
        self.assertEqual([c["text"] for c in cs], ["bir iki", "üç dört"])
        self.assertEqual(cs[0]["end"], a[1]["end"] + captions.POST_F)  # gap > 12: not extended

    def test_break_after_sentence_end_and_extend(self):
        ws = [w("Bitti.", 0, 30), w("Yeni", 36, 64)]
        cs = captions.cues(ws, 25)
        self.assertEqual([c["text"] for c in cs], ["Bitti.", "Yeni"])
        self.assertEqual(cs[0]["end"], 36)  # gap 6 <= 12: extended to next cue start
        self.assertEqual(cs[1]["end"], 64 + captions.POST_F)

    def test_short_cue_extended_into_the_gap(self):
        """Final review minor: no cue shorter than a second (fps frames)."""
        cs = captions.cues([w("Neden?", 0, 4), w("Çünkü", 60, 90)], 25)
        self.assertEqual([(c["start"], c["end"], c["text"]) for c in cs], [(0, 25, "Neden?"), (60, 93, "Çünkü")])
        cs = captions.cues([w("Neden?", 0, 4), w("Çünkü", 60, 90)], 50)
        self.assertEqual(cs[0]["end"], 50)  # scaled by fps

    def test_short_cue_merged_with_its_neighbour(self):
        cs = captions.cues([w("Neden?", 0, 4), w("Çünkü", 10, 40)], 25)
        self.assertEqual([(c["start"], c["end"], c["text"]) for c in cs], [(0, 43, "Neden? Çünkü")])

    def test_short_cue_not_merged_over_the_limits_or_the_teaser(self):
        long_ = ["kelimelerkelime"] * 2  # a full cue: 2 lines of 1 word
        ws = run(long_, dur=8, gap=2) + [w("Son.", 60, 64)]
        cs = captions.cues(ws, 25, avoid=[(70, 100)])
        self.assertEqual(cs[-1]["text"], "Son.")
        self.assertEqual(cs[-1]["end"], 70)  # extended up to the avoid range, not merged past the line limit
        for c in cs:
            self.assertTrue(all(len(x) <= captions.MAX_CHARS for x in c["text"].split("\n")) and c["text"].count("\n") <= 1)

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
