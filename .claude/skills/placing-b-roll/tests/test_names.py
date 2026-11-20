import unittest

import helpers  # noqa: F401
from episode import chapter_timeline_name


class ChapterTimelineName(unittest.TestCase):
    def test_chapter_timeline_name(self):
        self.assertEqual(
            chapter_timeline_name("COP31", "1. Açılış: Zirve neden bu kadar önemli? (Begüm Dursun)", 0),
            "COP31 ch1 Açılış")
        self.assertEqual(
            chapter_timeline_name("COP31", "6. COP31 dünyayı değiştirebilir mi?", 5),
            "COP31 ch6 COP31 dünyayı değiştirebilir mi")
        self.assertEqual(len(chapter_timeline_name("COP31", "1. " + "a" * 100, 0)), 80)


if __name__ == "__main__":
    unittest.main()
