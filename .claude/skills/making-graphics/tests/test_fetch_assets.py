"""scripts/fetch-assets.sh must ignore the graphics archive under assets/graphics/ (verify and manifest)."""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers

SCRIPT = helpers.REPO / "scripts" / "fetch-assets.sh"


class FetchAssets(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name) / "assets"
        self.dest.mkdir()
        (self.dest / "a.txt").write_text("brand")
        digest = hashlib.sha256(b"brand").hexdigest()
        (self.dest / "assets.sha256").write_text(f"{digest}  a.txt\n")
        render = self.dest / "graphics" / "number" / "abc" / "render.mov"
        render.parent.mkdir(parents=True)
        render.write_bytes(b"video")

    def run_script(self, cmd):
        env = dict(os.environ, ASSETS_DEST=str(self.dest), NO_COLOR="1")
        return subprocess.run(["bash", str(SCRIPT), cmd], env=env, capture_output=True, text=True)

    def test_verify_ignores_graphics(self):
        r = self.run_script("verify")
        self.assertNotIn("unexpected file", r.stderr + r.stdout)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_manifest_ignores_graphics(self):
        r = self.run_script("manifest")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("graphics/", (self.dest / "assets.sha256").read_text())


if __name__ == "__main__":
    unittest.main()
