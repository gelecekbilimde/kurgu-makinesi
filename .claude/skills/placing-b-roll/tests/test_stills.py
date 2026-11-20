import os, subprocess, sys, tempfile, unittest
from pathlib import Path
import helpers  # noqa: F401
import stills
from fakes import FakeRun

LIVE = os.environ.get("STILLS_LIVE") == "1"


class PlaceholderTest(unittest.TestCase):
    def setUp(self):
        stills._font.cache_clear()

    def run_placeholder(self, overlay, text="Bir galaksinin yavaşça dönüşü"):
        seen = {}
        fake = FakeRun()

        def runner(cmd, **kw):
            cmd = [str(c) for c in cmd]
            if Path(cmd[0]).name == "ffmpeg":
                vf = cmd[cmd.index("-vf") + 1] if "-vf" in cmd else cmd[cmd.index("-filter_complex") + 1]
                tf = vf.split("textfile='", 1)[1].split("'", 1)[0]
                seen["text"] = Path(tf).read_text(encoding="utf-8")
                seen["cmd"] = cmd
            return fake(cmd, **kw)

        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "p.png"
            stills.placeholder(out, "R012", "GRAFİK", text, overlay, runner=runner)
            self.assertTrue(out.exists())
            self.assertEqual([p.name for p in Path(t).iterdir()], ["p.png"])  # text file cleaned up
        return seen

    def test_full_frame(self):
        seen = self.run_placeholder(False)
        line = " ".join(seen["cmd"])
        self.assertIn("s=1920x1080", line)
        self.assertIn("textfile=", line)
        self.assertIn("fontfile='/usr/share/fonts/x/NotoSans[wght].ttf'", line)
        self.assertNotIn("pad=", line)
        self.assertTrue(seen["text"].startswith("R012 · GRAFİK\n"))
        self.assertIn("Bir galaksinin yavaşça dönüşü", seen["text"])

    def test_overlay_is_transparent_with_band(self):
        seen = self.run_placeholder(True)
        line = " ".join(seen["cmd"])
        self.assertIn("s=1920x216", line)  # lower-third band
        self.assertIn("pad=1920:1080:0:777:color=black@0", line)  # transparent elsewhere
        self.assertIn("rgba", line)

    def test_wrap(self):
        text = " ".join(["kelime"] * 40)
        seen = self.run_placeholder(False, text)
        lines = seen["text"].splitlines()
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(len(x) <= 60 for x in lines))

    def test_ffmpeg_missing_raises(self):
        def runner(cmd, **kw):
            if Path(str(cmd[0])).name == "ffmpeg":
                raise FileNotFoundError(2, "no", "ffmpeg")
            return FakeRun()(cmd, **kw)
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(stills.StillError):
                stills.placeholder(Path(t) / "p.png", "R1", "STOK", "x", False, runner=runner)


class ScreenshotTest(unittest.TestCase):
    def setUp(self):
        stills._chrome.cache_clear()

    def shot(self, **kw):
        fake = FakeRun(**kw)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "R006.png"
            res = stills.screenshot("https://example.com/a", out, runner=fake)
        return res, fake

    def test_ok(self):
        res, fake = self.shot()
        self.assertIsNone(res)
        npx = fake.tool_calls("npx")[0]
        self.assertEqual(npx[1:], ["--no-install", "hyperframes", "browser", "path"])
        chrome = fake.tool_calls("chrome-headless-shell")[0]
        for flag in ("--headless", "--hide-scrollbars", "--window-size=1920,1080"):
            self.assertIn(flag, chrome)
        self.assertTrue(any(c.startswith("--screenshot=") and c.endswith("R006.png") for c in chrome))
        self.assertEqual(chrome[-1], "https://example.com/a")

    def test_failures(self):
        self.assertEqual(self.shot(shot_rc=1)[0], "sayfa açılmadı")
        self.assertEqual(self.shot(shot_size=None)[0], "sayfa açılmadı")
        self.assertEqual(self.shot(shot_timeout=True)[0], "sayfa açılmadı")
        self.assertEqual(self.shot(shot_size=1000)[0], "sayfa engelli olabilir")

    def test_no_chrome(self):
        def runner(cmd, **kw):
            if Path(str(cmd[0])).name == "npx":
                return subprocess.CompletedProcess(cmd, 1, "", "not found")
            raise AssertionError(cmd)
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(stills.screenshot("https://x", Path(t) / "a.png", runner=runner), "sayfa açılmadı")


class FrameAtTest(unittest.TestCase):
    def test_cmd_selects_exact_frame(self):
        fake = FakeRun()
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "h.png"
            self.assertTrue(stills.frame_at(Path(t) / "v.mp4", 263, out, runner=fake))
        cmd = fake.tool_calls("ffmpeg")[0]
        self.assertNotIn("-sseof", cmd)
        self.assertEqual(cmd[cmd.index("-i") + 1], str(Path(t) / "v.mp4"))
        self.assertEqual(cmd[cmd.index("-vf") + 1], r"select=eq(n\,263)")
        self.assertEqual(cmd[-3:], ["-frames:v", "1", str(out)])


@unittest.skipUnless(LIVE, "STILLS_LIVE=1 for live FFmpeg/Chrome checks")
class LiveTest(unittest.TestCase):
    """Renders into $STILLS_OUT (default: a temp dir, printed) so the PNGs can be opened and checked."""

    def test_live(self):
        out = Path(os.environ.get("STILLS_OUT") or tempfile.mkdtemp(prefix="stills-"))
        out.mkdir(parents=True, exist_ok=True)
        text = "Ağır İşçi şövalyesi: ğüşıöç İĞÜŞÖÇ, " + "uzun bir açıklama " * 6
        stills.placeholder(out / "full.png", "R012", "GRAFİK", text, False)
        stills.placeholder(out / "overlay.png", "R015", "YAZI", text, True)
        self.assertIsNone(stills.screenshot("https://example.com", out / "example.png"))
        for n in ("full.png", "overlay.png", "example.png"):
            self.assertGreater((out / n).stat().st_size, 1000, n)
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,pix_fmt", "-of",
                            "csv=p=0", str(out / "overlay.png")], capture_output=True, text=True)
        self.assertIn("1920,1080", p.stdout)
        self.assertIn("rgba", p.stdout)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out / "overlay.png"), "-f", "rawvideo",
                              "-pix_fmt", "rgba", "-"], capture_output=True).stdout
        alpha = lambda x, y: raw[(y * 1920 + x) * 4 + 3]  # noqa: E731
        self.assertEqual(alpha(10, 10), 0)  # transparent above the band
        self.assertEqual(alpha(10, 900), 153)  # band
        print(f"\nSTILLS_LIVE çıktıları: {out}")

    def test_live_hold_frame_is_built_chart(self):
        """A real bar-chart render: the hold frame (POSTER_AT) is the built chart, brighter than the faded end."""
        import fetch
        out = Path(os.environ.get("STILLS_OUT") or tempfile.mkdtemp(prefix="stills-"))
        gdir = out / "grafik"
        p = subprocess.run([sys.executable, str(fetch.MAKE_GRAPHIC), "bar-chart", "--set", "line1=Katılımcı sayısı",
                            "--set", "bars=2024=425", "--set", "bars=2020=414", "--set", "source=UNFCCC",
                            "--frames", "375", "--background", "--resolution", "1080p", "--code", "GLIVE",
                            "--out", str(gdir)], capture_output=True, text=True, cwd=str(fetch.REPO))
        self.assertEqual(p.returncode, 0, p.stderr)
        video = sorted(gdir.glob("GLIVE-*.mp4"))[-1]
        n = round(375 * fetch.POSTER_AT)
        self.assertTrue(stills.frame_at(video, n, out / "hold.png"))
        self.assertTrue(stills.frame_at(video, 374, out / "last.png"))

        def luma(png):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(png), "-f", "rawvideo", "-pix_fmt", "gray",
                                  "-"], capture_output=True).stdout
            return sum(raw) / len(raw)
        self.assertGreater(luma(out / "hold.png"), luma(out / "last.png"))
        print(f"\nbekletme karesi {n}: {out / 'hold.png'} (son kare: {out / 'last.png'})")


if __name__ == "__main__":
    unittest.main()
