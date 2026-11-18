import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
import hf
import render
from fakes import FakeRun


class Render(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.staged = self.d / "stage"
        self.staged.mkdir()
        (self.staged / "vars.json").write_text("{}")

    def call(self, output="overlay", resolution="4k", fixed=False, vertical=False, run=None, name="x.mov"):
        run = run or FakeRun()
        out = self.d / name
        render.render(self.staged, output, resolution, fixed, vertical, 25, out, run=run)
        return run, out

    def test_render_args_overlay_4k(self):
        run, out = self.call()
        cmd = run.calls[0]
        for a in ("--format mov", "--resolution landscape-4k", "--fps 25", "--strict-variables"):
            self.assertIn(a, " ".join(cmd))
        self.assertIn(str(self.staged / "vars.json"), cmd)
        self.assertEqual(out.read_bytes(), b"video mov")

    def test_render_fullscreen_is_mp4(self):
        run, _ = self.call(output="fullscreen", name="x.mp4")
        self.assertIn("--format mp4", " ".join(run.calls[0]))

    def test_render_vertical_uses_portrait_4k(self):
        run, _ = self.call(vertical=True)
        self.assertIn("--resolution portrait-4k", " ".join(run.calls[0]))

    def test_render_1080p_has_no_resolution(self):
        run, _ = self.call(resolution="1080p")
        self.assertNotIn("--resolution", run.calls[0])

    def test_render_fixed_canvas_has_no_resolution(self):
        run, _ = self.call(fixed=True)
        self.assertNotIn("--resolution", run.calls[0])

    def test_render_still_keeps_single_png(self):
        run, out = self.call(output="still", fixed=True, name="x.png")
        self.assertIn("--format png-sequence", " ".join(run.calls[0]))
        self.assertTrue(out.is_file())
        self.assertEqual(out.read_bytes(), b"png")
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["stage", "x.png"])

    def test_render_failure_raises_and_leaves_nothing(self):
        with self.assertRaises(hf.ToolError) as cm:
            self.call(run=FakeRun(fail=True))
        self.assertIn("Chrome", str(cm.exception))
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["stage"])

    def test_poster_command(self):
        run = FakeRun()
        render.poster(self.d / "x.mov", 70, self.d / "p.png", run=run)
        cmd = " ".join(run.calls[0])
        self.assertTrue(run.calls[0][0].endswith("ffmpeg"))
        self.assertIn("eq(n\\,70)", cmd)
        self.assertIn("rgba", cmd)


if __name__ == "__main__":
    unittest.main()
