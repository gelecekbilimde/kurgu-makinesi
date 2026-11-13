import unittest

import helpers  # noqa: F401  (sets sys.path)
from index import match  # noqa: E402


def entry(id, keywords, orientation="horizontal", title="", added="2026-11-13T10:00:00+00:00"):
    return {"source": "pixabay", "id": id, "title": title, "keywords": keywords, "orientation": orientation,
            "added": added}


class Match(unittest.TestCase):
    def test_match_all_words(self):
        e = [entry("1", ["rocket", "launch pad"])]
        self.assertEqual(len(match(e, "rocket launch")), 1)
        self.assertEqual(match(e, "rocket moon"), [])
        self.assertEqual(len(match(e, "Rocket")), 1)

    def test_match_uses_title(self):
        self.assertEqual(len(match([entry("1", [], title="Ay'a iniş")], "iniş")), 1)

    def test_match_orientation_first(self):
        e = [entry("h", ["rocket"]), entry("v", ["rocket"], orientation="vertical")]
        self.assertEqual([x["id"] for x in match(e, "rocket", "vertical")], ["v", "h"])

    def test_newest_first_within_orientation(self):
        e = [entry("old", ["rocket"], added="2026-01-01T00:00:00+00:00"), entry("new", ["rocket"])]
        self.assertEqual([x["id"] for x in match(e, "rocket")], ["new", "old"])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(match([entry("1", ["rocket"])], "  "), [])


if __name__ == "__main__":
    unittest.main()
