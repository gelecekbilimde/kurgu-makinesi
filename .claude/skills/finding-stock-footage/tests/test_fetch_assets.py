"""scripts/fetch-assets.sh must ignore the stock cache under assets/stock/ (verify and manifest)."""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401

SCRIPT = Path(helpers.SCRIPTS).parents[3] / "scripts" / "fetch-assets.sh"


class FetchAssets(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name) / "assets"
        self.dest.mkdir()
        (self.dest / "a.txt").write_text("brand")
        digest = hashlib.sha256(b"brand").hexdigest()
        (self.dest / "assets.sha256").write_text(f"{digest}  a.txt\n")
        clip = self.dest / "stock" / "clips" / "nasa" / "x.mp4"
        clip.parent.mkdir(parents=True)
        clip.write_bytes(b"video")

    def run_script(self, cmd):
        env = dict(os.environ, ASSETS_DEST=str(self.dest), NO_COLOR="1")
        return subprocess.run(["bash", str(SCRIPT), cmd], env=env, capture_output=True, text=True)

    def test_verify_ignores_stock(self):
        r = self.run_script("verify")
        self.assertNotIn("unexpected file", r.stderr + r.stdout)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_manifest_ignores_stock(self):
        r = self.run_script("manifest")
        self.assertEqual(r.returncode, 0, r.stderr)
        manifest = (self.dest / "assets.sha256").read_text()
        self.assertIn("a.txt", manifest)
        self.assertNotIn("stock/", manifest)


if __name__ == "__main__":
    unittest.main()
