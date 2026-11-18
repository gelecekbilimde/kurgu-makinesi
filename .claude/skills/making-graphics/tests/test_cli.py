import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers
import make_graphic
from fakes import FakeRun

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class Cli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.root = helpers.make_root(tmp.name)
        self.archive = self.d / "assets" / "graphics"
        self.out = self.d / "out"
        self.home = self.d / "home"

    def main(self, *argv, run=None, out=True):
        run = run if run is not None else FakeRun()
        args = [*argv, "--root", str(self.root), "--archive", str(self.archive)]
        if out:
            args += ["--out", str(self.out)]
        so, se = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            code = make_graphic.main(args, env={"HOME": str(self.home)}, run=run, now=NOW)
        return code, so.getvalue(), se.getvalue(), run

    def results(self):
        return json.loads((self.out / "results.json").read_text())

    def files(self, d):
        return sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()) if d.exists() else []

    def test_render_delivers_and_archives(self):
        code, so, se, run = self.main("demo", "--set", "value=10^67", "--set", "source=NASA, 2024")
        self.assertEqual(code, 0, se)
        r = self.results()["renders"][0]
        self.assertEqual(r["file"], "demo-1.mov")
        self.assertEqual((r["template"], r["design"], r["variant"], r["frames"], r["fps"], r["resolution"]),
                         ("demo", "demo", "a", 150, 25, "4k"))
        self.assertEqual(r["sources"], ["NASA, 2024"])
        self.assertFalse(r["from_archive"])
        self.assertEqual((self.out / "kaynaklar.txt").read_text(), "NASA, 2024\n")
        self.assertTrue((self.archive / "demo" / r["archive_id"] / "vars.json").is_file())
        self.assertIn("demo-1.mov", so)

    def test_fullscreen_defaults_to_alpha_mov(self):
        code, _, se, run = self.main("demo", "--set", "value=1")
        self.assertEqual(code, 0, se)
        r = self.results()["renders"][0]
        self.assertEqual((r["file"], r["output"], r["background"]), ("demo-1.mov", "overlay", False))
        self.assertIn("--format mov", " ".join(run.renders()[0]))

    def test_background_flag_gives_mp4(self):
        code, _, se, run = self.main("demo", "--set", "value=1", "--background")
        self.assertEqual(code, 0, se)
        r = self.results()["renders"][0]
        self.assertEqual((r["file"], r["output"], r["background"]), ("demo-1.mp4", "fullscreen", True))
        self.assertIn("--format mp4", " ".join(run.renders()[0]))

    def test_background_is_part_of_archive_id(self):
        self.main("demo", "--set", "value=1")
        _, _, _, run = self.main("demo", "--set", "value=1", "--background")
        self.assertEqual(len(run.renders()), 1)

    def test_batch_row_background(self):
        f = self.d / "rows.json"
        f.write_text(json.dumps([{"template": "demo", "code": "G1", "fields": {"value": "1"}, "background": True}]))
        code, _, se, _ = self.main("--batch", str(f))
        self.assertEqual(code, 0, se)
        self.assertEqual(self.results()["renders"][0]["file"], "G1-1.mp4")

    def test_archive_reuse(self):
        self.main("demo", "--set", "value=1")
        code, so, _, run = self.main("demo", "--set", "value=1")
        self.assertEqual(code, 0)
        self.assertEqual(run.renders(), [])
        self.assertTrue(self.results()["renders"][1]["from_archive"])
        self.assertEqual(self.results()["renders"][1]["file"], "demo-2.mov")

    def test_fresh_forces_render(self):
        self.main("demo", "--set", "value=1")
        _, _, _, run = self.main("demo", "--set", "value=1", "--fresh")
        self.assertEqual(len(run.renders()), 1)

    def test_design_change_invalidates_archive(self):
        self.main("demo", "--set", "value=1")
        (self.root / "designs" / "demo" / "tokens.css").write_text(":root { --ink: #000; }")
        _, _, _, run = self.main("demo", "--set", "value=1")
        self.assertEqual(len(run.renders()), 1)

    def test_render_failure_leaves_no_entry(self):
        code, _, se, _ = self.main("demo", "--set", "value=1", run=FakeRun(fail=True))
        self.assertEqual(code, 1)
        lines = [x for x in se.splitlines() if x.strip()]
        self.assertEqual(len(lines), 1, se)
        self.assertTrue(lines[0].startswith("Hata:"), se)
        self.assertEqual(self.files(self.archive), [])
        self.assertEqual(self.files(self.out), [])

    def test_validation_error_exit_2(self):
        code, _, se, run = self.main("demo", "--set", "value=abc", "--set", "state=x")
        self.assertEqual(code, 2)
        self.assertIn("value", se)
        self.assertIn("state", se)
        self.assertEqual(run.calls, [])

    def test_frames_out_of_range(self):
        code, _, se, _ = self.main("demo", "--set", "value=1", "--frames", "10")
        self.assertEqual(code, 2)
        self.assertIn("75", se)

    def test_frames_scale_with_fps(self):
        code, _, se, _ = self.main("demo", "--set", "value=1", "--fps", "50", "--frames", "700")
        self.assertEqual(code, 0, se)
        self.assertEqual(self.results()["renders"][0]["frames"], 700)

    def test_unknown_template(self):
        code, _, se, _ = self.main("yok")
        self.assertEqual(code, 2)
        self.assertIn("fixed", se)

    def test_vertical_not_supported(self):
        (self.root / "templates/demo/demo/template.json").write_text(
            (self.root / "templates/demo/demo/template.json").read_text().replace('"vertical": true',
                                                                                   '"vertical": false'))
        code, _, se, _ = self.main("demo", "--set", "value=1", "--vertical")
        self.assertEqual(code, 2)
        self.assertIn("dikey", se)

    def test_still_output_by_state(self):
        code, _, se, run = self.main("demo", "--set", "value=1", "--set", "state=static")
        self.assertEqual(code, 0, se)
        r = self.results()["renders"][0]
        self.assertEqual((r["file"], r["frames"]), ("demo-1.png", 1))
        self.assertIn("png-sequence", " ".join(run.renders()[0]))

    def test_fixed_canvas_ignores_resolution(self):
        code, _, se, run = self.main("fixed", "--set", "state=a", "--vertical")
        self.assertEqual(code, 0, se)
        r = self.results()["renders"][0]
        self.assertEqual((r["file"], r["resolution"], r["vertical"]), ("fixed-1.mov", "native", False))
        self.assertNotIn("--resolution", run.renders()[0])

    def test_repeated_set_builds_list(self):
        code, _, se, _ = self.main("demo", "--set", "value=1", "--set", "bars=Mars=3,7", "--set", "bars=Dünya=9")
        self.assertEqual(code, 0, se)
        self.assertEqual(len(self.results()["renders"][0]["values"]["bars"]), 2)

    def test_repeated_set_on_text_field_rejected(self):
        code, _, se, _ = self.main("demo", "--set", "value=1", "--set", "explanation=a", "--set", "explanation=b")
        self.assertEqual(code, 2)
        self.assertIn("explanation", se)

    def test_fields_file(self):
        f = self.d / "fields.json"
        f.write_text(json.dumps({"value": "2", "bars": ["a=1", "b=2"]}))
        code, _, se, _ = self.main("demo", "--fields-file", str(f), "--set", "value=3")
        self.assertEqual(code, 0, se)
        self.assertEqual(self.results()["renders"][0]["values"]["value"]["text"], "3")

    def test_unknown_variant(self):
        code, _, se, _ = self.main("demo", "--set", "value=1", "--variant", "zzz")
        self.assertEqual(code, 2)
        self.assertIn("a, b", se)

    def test_default_out_dir(self):
        code, so, se, _ = self.main("demo", "--set", "value=1", "--set", "explanation=Güneş Işığı", out=False)
        self.assertEqual(code, 0, se)
        self.assertTrue((self.home / "Downloads/grafik/demo-gunes-isigi/demo-1.mov").is_file())

    def test_list_json_shape(self):
        code, so, _, _ = self.main("--list", "--json", out=False)
        self.assertEqual(code, 0)
        data = json.loads(so)
        self.assertEqual([t["name"] for t in data], ["demo", "fixed"])
        self.assertEqual(set(data[0]), {"name", "description", "output", "vertical", "frames", "fields"})
        self.assertEqual(set(data[0]["fields"][0]), {"name", "type", "required", "help"})

    def test_list_human(self):
        code, so, _, _ = self.main("--list", out=False)
        self.assertEqual(code, 0)
        self.assertIn("demo", so)
        self.assertIn("Test şablonu", so)

    def test_batch(self):
        f = self.d / "rows.json"
        f.write_text(json.dumps([{"template": "demo", "code": "G1", "fields": {"value": "1"}},
                                 {"template": "fixed", "code": "G2", "fields": {"state": "b"}}]))
        code, _, se, _ = self.main("--batch", str(f))
        self.assertEqual(code, 0, se)
        self.assertEqual([r["file"] for r in self.results()["renders"]], ["G1-1.mov", "G2-1.mov"])

    def test_batch_bad_row_does_not_stop_others(self):
        f = self.d / "rows.json"
        f.write_text(json.dumps([{"template": "yok", "code": "G1", "fields": {}},
                                 {"template": "demo", "code": "G2", "fields": {"value": "1"}}]))
        code, _, se, run = self.main("--batch", str(f))
        self.assertEqual(code, 0, se)
        self.assertEqual(len(run.renders()), 1)
        notes = self.results()["notes"]
        self.assertTrue(any("G1" in n for n in notes), notes)
        self.assertIn("G1", se)

    def test_batch_needs_out(self):
        f = self.d / "rows.json"
        f.write_text("[]")
        code, _, se, _ = self.main("--batch", str(f), out=False)
        self.assertEqual(code, 1)
        self.assertIn("--out", se)

    def test_reindex_rebuilds_from_vars(self):
        self.main("demo", "--set", "value=1")
        (self.archive / "index.json").unlink()
        code, so, _, _ = self.main("--reindex", out=False)
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads((self.archive / "index.json").read_text())), 1)
        self.assertIn("1", so)

    def test_one_mode_only(self):
        code, _, se, _ = self.main("demo", "--list")
        self.assertEqual(code, 1)
        self.assertIn("Kullanım", se)


if __name__ == "__main__":
    unittest.main()
