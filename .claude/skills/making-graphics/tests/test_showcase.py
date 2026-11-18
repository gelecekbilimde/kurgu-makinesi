import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers
import make_graphic
from fakes import FakeRun

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class Showcase(unittest.TestCase):
    def run_showcase(self, design="demo"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        root = helpers.make_root(tmp.name)
        (root / "templates/demo/fixed/samples.json").write_text('[{"label": "a", "fields": {"state": "a"}}]')
        if design == "starter":
            import shutil
            shutil.copytree(root / "designs/demo", root / "designs/starter")
            shutil.copytree(root / "templates/demo", root / "templates/starter")
        out = d / "show"
        run = FakeRun()
        se = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
            code = make_graphic.main(["--showcase", "--design", design, "--root", str(root), "--archive",
                                      str(d / "arch"), "--out", str(out)], env={"HOME": str(d)}, run=run, now=NOW)
        self.assertEqual(code, 0, se.getvalue())
        return out, run

    def test_showcase_lists_every_template(self):
        out, run = self.run_showcase()
        html = (out / "index.html").read_text()
        self.assertIn("demo", html)
        self.assertIn("fixed", html)
        self.assertIn("Test şablonu", html)
        self.assertTrue(all("1080p" not in " ".join(c) for c in run.renders()))
        self.assertTrue(all("--resolution" not in c for c in run.renders()))
        self.assertTrue((out / "design" / "tokens.css").is_file())
        self.assertIn("design/tokens.css", html)

    def test_showcase_overlays_become_webm(self):
        out, run = self.run_showcase()
        self.assertTrue(any(c[0].endswith("ffmpeg") and "libvpx-vp9" in c for c in run.calls))
        self.assertIn(".webm", (out / "index.html").read_text())

    def test_showcase_marks_starter(self):
        out, _ = self.run_showcase("starter")
        self.assertIn("başlangıç örneği", (out / "index.html").read_text())

    def test_showcase_plain_design_not_marked(self):
        out, _ = self.run_showcase("demo")
        self.assertNotIn("başlangıç örneği", (out / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
