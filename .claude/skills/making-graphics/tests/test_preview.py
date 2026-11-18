import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers
import designs
import manifest
import preview
import stage


class FakePreviewRun:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, cwd, runner=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        out = json.dumps({"schemaVersion": 1, "ok": True, "result": {"state": "running", "port": 4567,
                          "serverUrl": "http://127.0.0.1:4567", "studioUrl": "http://127.0.0.1:4567/#project/pv"}}) \
            if "--json" in cmd else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")


class Preview(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = helpers.make_root(tmp.name)
        self.t = manifest.load(designs.template_dir(self.root, "demo", "demo"))
        self.design = designs.design_dir(self.root, "demo")

    def test_preview_command(self):
        run = FakePreviewRun()
        url = preview.preview(self.t, self.design, "a", False, {"value": "10^67"}, self.tmp / "pv", port=4567, run=run,
                              http_ok=lambda u: True)
        cmd = " ".join(run.calls[-1])
        self.assertIn("preview", cmd)
        self.assertIn("--background", cmd)
        self.assertIn("--port 4567", cmd)
        self.assertIn("--no-open", cmd)
        self.assertTrue(url.startswith("http://127.0.0.1:4567"))
        self.assertIn("#project/", url)

    def test_preview_bakes_values_as_defaults(self):
        preview.preview(self.t, self.design, "a", False, {"value": "10^67"}, self.tmp / "pv", port=4567,
                        run=FakePreviewRun(), http_ok=lambda u: True)
        html = (self.tmp / "pv" / "index.html").read_text()
        decl = json.loads(re.search(r"data-composition-variables='([^']*)'", html).group(1).replace("&apos;", "'"))
        self.assertEqual(json.loads({d["id"]: d["default"] for d in decl}["value"])["exp"], "67")

    def test_preview_dead_url_is_an_error(self):
        import hf
        with self.assertRaises(hf.ToolError):
            preview.preview(self.t, self.design, "a", False, {"value": "1"}, self.tmp / "pv", port=4567,
                            run=FakePreviewRun(), http_ok=lambda u: False)


class Bake(unittest.TestCase):
    def test_bake_defaults_with_apostrophe(self):
        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_root(d)
            t = manifest.load(designs.template_dir(root, "demo", "demo"))
            values = manifest.validate(t, {"value": "1", "explanation": "Dünya'nın"})
            dest = stage.stage(t, designs.design_dir(root, "demo"), "a", values, False, 25, 25, Path(d) / "s")
            stage.bake_defaults(dest)
            html = (dest / "index.html").read_text()
            decl = json.loads(re.search(r"data-composition-variables='([^']*)'", html).group(1).replace("&apos;", "'"))
            self.assertEqual({x["id"]: x["default"] for x in decl}["explanation"], "Dünya'nın")


if __name__ == "__main__":
    unittest.main()
