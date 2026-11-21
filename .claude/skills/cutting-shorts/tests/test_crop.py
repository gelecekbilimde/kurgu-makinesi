import unittest

import helpers  # noqa: F401
import crop

W, H = 1080, 1920
SW, SH = 3840, 2160
FILL = (H / SH) / (W / SW)  # 3.160494 (reference.md, fact 2)


def place(t, sx, sy):
    """Where source pixel (sx, sy) lands on the 1080x1920 timeline (reference.md, fact 2)."""
    s = W / SW * t["ZoomX"]
    k = SH * W / SW / H
    return W / 2 + (sx - SW / 2) * s + t["Pan"], H / 2 + (sy - SH / 2) * s - t["Tilt"] * k


class CropTest(unittest.TestCase):
    def test_crop_centres_face(self):
        t = crop.transform({"cx": 1700, "cy": 800, "h": 680}, SW, SH)
        self.assertAlmostEqual(t["ZoomX"], FILL * 1.15, places=4)
        self.assertEqual(t["ZoomX"], t["ZoomY"])
        x, y = place(t, 1700, 800)
        self.assertAlmostEqual(x, W / 2, delta=0.5)
        self.assertAlmostEqual(y, H / 3, delta=0.5)

    def test_crop_clamps_at_edge(self):
        t = crop.transform({"cx": 3790, "cy": 60, "h": 300}, SW, SH)
        left, top = place(t, 0, 0)
        right, bottom = place(t, SW, SH)
        self.assertAlmostEqual(right, W, delta=0.5)   # pushed as far right as it goes
        self.assertAlmostEqual(top, 0, delta=0.5)     # and as far down
        self.assertLessEqual(left, 0)
        self.assertGreaterEqual(bottom, H)
        t = crop.transform({"cx": 10, "cy": 2150, "h": 300}, SW, SH)
        left, top = place(t, 0, 0)
        right, bottom = place(t, SW, SH)
        self.assertAlmostEqual(left, 0, delta=0.5)
        self.assertAlmostEqual(bottom, H, delta=0.5)

    def test_crop_no_face_centre(self):
        t = crop.transform(None, SW, SH)
        self.assertEqual((t["Pan"], t["Tilt"]), (0, 0))
        self.assertAlmostEqual(t["ZoomX"], FILL * 1.15, places=4)
        self.assertEqual(place(t, SW / 2, SH / 2), (W / 2, H / 2))

    def test_window_is_the_shown_source_rectangle(self):
        t = crop.transform({"cx": 1700, "cy": 800, "h": 680}, SW, SH)
        x, y, w, h = crop.window(t, SW, SH)
        self.assertAlmostEqual(place(t, x, y)[0], 0, delta=0.01)
        self.assertAlmostEqual(place(t, x, y)[1], 0, delta=0.01)
        self.assertAlmostEqual(place(t, x + w, y + h)[0], W, delta=0.01)
        self.assertAlmostEqual(place(t, x + w, y + h)[1], H, delta=0.01)


if __name__ == "__main__":
    unittest.main()
