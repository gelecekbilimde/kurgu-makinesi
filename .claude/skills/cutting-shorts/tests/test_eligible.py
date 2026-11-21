import tempfile, unittest
import helpers
from helpers import make_episode
import eligible, episode


class EligibleTest(unittest.TestCase):
    def test_eligible_needs_both(self):
        with tempfile.TemporaryDirectory() as t:
            ep = episode.Episode(make_episode(t, frozen=[3, 4], broll_frozen=[4]))
            self.assertEqual(eligible.chapters(ep), [4])

    def test_sentences_split_on_punct_and_pause(self):
        w = [(0, 8, "a", "Merhaba"), (10, 18, "b", "dünya."), (20, 28, "c", "Sonra"),
             (30, 38, "d", "ne"), (60, 68, "e", "oldu?"), (70, 78, "f", "Bilmem")]
        got = eligible.sentences(w, 25)
        self.assertEqual(got, [{"start": 0, "end": 18, "text": "Merhaba dünya."},
                               {"start": 20, "end": 38, "text": "Sonra ne"},
                               {"start": 60, "end": 68, "text": "oldu?"},
                               {"start": 70, "end": 78, "text": "Bilmem"}])

    def test_pause_of_exactly_12_does_not_split(self):
        w = [(0, 8, "a", "bir"), (20, 28, "b", "iki")]
        self.assertEqual(len(eligible.sentences(w, 25)), 1)


if __name__ == "__main__":
    unittest.main()
