"""Live renders with the pinned HyperFrames. Run with GRAPHICS_LIVE=1 after setup.py reports ready."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers
import hf


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,pix_fmt,width,height,nb_read_frames", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"][0]


def frame_png(video, n, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select=eq(n\\,{n})", "-vframes", "1",
                    str(dest)], check=True)
    return dest.read_bytes()


@unittest.skipUnless(helpers.LIVE, "GRAPHICS_LIVE=1 değil")
class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        proj = Path(cls.tmp.name) / "smoke"
        shutil.copytree(helpers.FIXTURES / "smoke", proj)
        (proj / "kit").mkdir()
        shutil.copy(helpers.KIT, proj / "kit" / "hf-kit.js")
        cls.out = Path(cls.tmp.name) / "smoke.mov"
        r = hf.run(hf.hf_cmd("render", str(proj), "--fps", "25", "--format", "mov", "-o", str(cls.out)), proj)
        if r.returncode != 0:
            raise AssertionError(r.stdout[-2000:] + r.stderr[-2000:])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_live_smoke_render(self):
        s = probe(self.out)
        self.assertEqual(int(s["nb_read_frames"]), 25)
        self.assertEqual(s["codec_name"], "prores")
        self.assertTrue(s["pix_fmt"].startswith(("yuva", "rgba", "argb")), s["pix_fmt"])
        self.assertEqual((s["width"], s["height"]), (1920, 1080))

    def test_live_smoke_frames_differ(self):
        d = Path(self.tmp.name)
        self.assertNotEqual(frame_png(self.out, 0, d / "f0.png"), frame_png(self.out, 24, d / "f24.png"))


if __name__ == "__main__":
    unittest.main()


def render_cli(*args):
    """Run make_graphic.py against the real graphics/ root into a temp out/archive; returns (code, out, stderr)."""
    import contextlib
    import io
    import make_graphic
    tmp = tempfile.mkdtemp(prefix="grafik-live-")
    out = Path(tmp) / "out"
    se = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
        code = make_graphic.main([*args, "--out", str(out), "--archive", str(Path(tmp) / "archive")])
    return code, out, se.getvalue()


@unittest.skipUnless(helpers.LIVE, "GRAPHICS_LIVE=1 değil")
class StarterTemplates(unittest.TestCase):
    def test_live_chapter_title(self):
        code, out, err = render_cli("chapter-title", "--set", "line1=Hawking ışıması", "--set", "line2=nasıl çalışır?",
                                    "--resolution", "1080p")
        self.assertEqual(code, 0, err)
        s = probe(out / "chapter-title-1.mp4")
        self.assertEqual((int(s["nb_read_frames"]), s["codec_name"], s["width"], s["height"]), (100, "h264", 1920, 1080))

    def test_live_number_sources(self):
        code, out, err = render_cli("number", "--set", "value=10^67", "--set", "unit=yıl",
                                    "--set", "explanation=Güneş kütlesindeki bir kara deliğin buharlaşma süresi",
                                    "--set", "highlight=buharlaşma süresi", "--set", "source=NASA, 2024",
                                    "--resolution", "1080p")
        self.assertEqual(code, 0, err)
        self.assertEqual((out / "kaynaklar.txt").read_text(), "NASA, 2024\n")
        s = probe(out / "number-1.mp4")
        self.assertEqual(int(s["nb_read_frames"]), 150)

    def test_live_bar_chart_8_bars(self):
        bars = [f"--set=bars={y}={v}" for y, v in zip(range(1960, 2041, 10), (317, 326, 339, 354, 370, 390, 414, 425))]
        code, out, err = render_cli("bar-chart", "--set", "line1=Atmosferdeki CO₂", "--set", "line2=her yıl artıyor",
                                    *bars, "--set", "unit=ppm", "--set", "source=NOAA GML",
                                    "--set", "hand=+%34", "--set", "hand_bar=2030", "--resolution", "1080p")
        self.assertEqual(code, 0, err)
        s = probe(out / "bar-chart-1.mp4")
        self.assertEqual(int(s["nb_read_frames"]), 175)
