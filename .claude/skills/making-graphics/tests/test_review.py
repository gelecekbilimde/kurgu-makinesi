import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers
import make_graphic
import review
from fakes import FakeRun

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class Samples(unittest.TestCase):
    def test_samples_renders_every_row_fresh(self):
        seen = []

        def render_fn(row):
            seen.append(row)
            return {"code": row["code"], "archive_id": "x"}

        rows = [{"label": "a", "fields": {"value": "1"}}, {"label": "b", "fields": {"value": "2"}, "variant": "b"}]
        entries = review.samples("demo", rows, render_fn)
        self.assertEqual(len(entries), 2)
        self.assertEqual([r["template"] for r in seen], ["demo", "demo"])
        self.assertTrue(all(r["fresh"] for r in seen))
        self.assertEqual([r["code"] for r in seen], ["01-a", "02-b"])
        self.assertEqual(seen[1]["variant"], "b")
        self.assertNotIn("label", seen[0])

    def test_contact_sheet_command(self):
        run = FakeRun()
        with tempfile.TemporaryDirectory() as d:
            posters = [Path(d) / f"p{i}.png" for i in range(5)]
            review.contact_sheet(posters, Path(d) / "contact.png", run=run)
        cmd = " ".join(run.calls[0])
        self.assertTrue(run.calls[0][0].endswith("ffmpeg"))
        self.assertIn("tile=", cmd)
        self.assertIn("force_original_aspect_ratio=decrease", cmd)
        self.assertIn("concat=n=5", cmd)
        self.assertEqual(sum(1 for c in run.calls[0] if c == "-i"), 5)


class SamplesCli(unittest.TestCase):
    def test_samples_flag_renders_and_builds_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_root(d)
            out = Path(d) / "samples"
            run = FakeRun()
            se = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
                code = make_graphic.main(["--samples", "demo", "--root", str(root), "--archive",
                                          str(Path(d) / "arch"), "--out", str(out)],
                                         env={"HOME": d}, run=run, now=NOW)
            self.assertEqual(code, 0, se.getvalue())
            self.assertEqual(len(run.renders()), 2)
            self.assertTrue((out / "01-kisa-1.mp4").is_file())
            self.assertTrue((out / "contact.png").is_file())

    def test_samples_without_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_root(d)
            se = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
                code = make_graphic.main(["--samples", "fixed", "--root", str(root), "--archive", str(Path(d) / "a")],
                                         env={"HOME": d}, run=FakeRun(), now=NOW)
            self.assertEqual(code, 2)
            self.assertIn("samples.json", se.getvalue())


if __name__ == "__main__":
    unittest.main()
