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

    def test_live_name_line_alpha(self):
        code, out, err = render_cli("name-line", "--set", "name=Burak Cankaya", "--set", "role=sunucu, Gelecek Bilimde",
                                    "--resolution", "1080p")
        self.assertEqual(code, 0, err)
        mov = out / "name-line-1.mov"
        s = probe(mov)
        self.assertEqual(s["codec_name"], "prores")
        self.assertTrue(s["pix_fmt"].startswith("yuva"), s["pix_fmt"])
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mov), "-vf", "select=eq(n\\,90),alphaextract,crop=8:8:0:0",
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True)
        self.assertEqual(max(r.stdout), 0, "top-left corner must be fully transparent")


def png_size_alpha(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,pix_fmt", "-of", "json",
                        str(path)], capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    return s["width"], s["height"], s["pix_fmt"]


def mean_diff(video, n, png):
    """Mean absolute difference (0-255, all four channels) between frame n of video and a PNG."""
    sel = f"select=eq(n\\,{n})" if n >= 0 else "reverse"
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-i", str(png), "-filter_complex",
                        f"[0]{sel},format=rgba,setpts=0[a];[1]format=rgba[b];[a][b]blend=all_mode=difference,"
                        "format=gray,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True, check=True)
    vals = [float(x.split("=")[1]) for x in r.stdout.split() if x.startswith("lavfi.signalstats.YAVG=")]
    return vals[0]


@unittest.skipUnless(helpers.LIVE, "GRAPHICS_LIVE=1 değil")
class Watermark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {}
        for state, frames in (("static", None), ("revolve", 150), ("star", 75), ("wireframe", 50)):
            args = ["watermark", "--set", f"state={state}"] + (["--frames", str(frames)] if frames else [])
            code, out, err = render_cli(*args)
            if code != 0:
                raise AssertionError(err)
            cls.files[state] = next(out.glob("watermark-1.*"))

    def test_live_watermark_static_png(self):
        w, h, fmt = png_size_alpha(self.files["static"])
        self.assertEqual((w, h), (3800, 2600))
        self.assertIn("a", fmt)

    def test_live_watermark_states_same_canvas(self):
        for state in ("revolve", "star", "wireframe"):
            s = probe(self.files[state])
            self.assertEqual((s["width"], s["height"]), (3800, 2600), state)
            self.assertTrue(s["pix_fmt"].startswith("yuva"), state)

    def test_live_watermark_chains(self):
        for state in ("revolve", "star", "wireframe"):
            n = int(probe(self.files[state])["nb_read_frames"])
            for frame in (0, n - 1):
                with self.subTest(state=state, frame=frame):
                    self.assertLess(mean_diff(self.files[state], frame, self.files["static"]), 2.0)


@unittest.skipUnless(helpers.LIVE, "GRAPHICS_LIVE=1 değil")
class Scaffolded(unittest.TestCase):
    def test_live_new_template_renders(self):
        import contextlib
        import io
        import scaffold
        import make_graphic
        tmp = Path(tempfile.mkdtemp(prefix="grafik-scaffold-"))
        root = tmp / "graphics"
        shutil.copytree(helpers.REPO / "graphics" / "designs" / "starter", root / "designs" / "starter",
                        ignore=shutil.ignore_patterns("reference"))
        (root / "config.json").write_text('{"design": "starter"}')
        scaffold.new_template(root, "starter", "deneme")
        se = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
            code = make_graphic.main(["deneme", "--set", "title=Deneme başlığı", "--frames", "50", "--resolution",
                                      "1080p", "--root", str(root), "--archive", str(tmp / "a"), "--out", str(tmp / "o")])
        self.assertEqual(code, 0, se.getvalue())
        s = probe(tmp / "o" / "deneme-1.mp4")
        self.assertEqual((int(s["nb_read_frames"]), s["width"]), (50, 1920))
