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
