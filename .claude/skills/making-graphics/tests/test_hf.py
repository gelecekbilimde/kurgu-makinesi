import subprocess
import unittest
from pathlib import Path

import helpers  # noqa: F401
import hf


class Env(unittest.TestCase):
    def test_env_sets_telemetry_off(self):
        env = hf.hf_env({})
        self.assertEqual(env["HYPERFRAMES_NO_TELEMETRY"], "1")
        self.assertEqual(env["DO_NOT_TRACK"], "1")

    def test_env_does_not_mutate_base(self):
        base = {"A": "b"}
        hf.hf_env(base)
        self.assertEqual(base, {"A": "b"})

    def test_cmd_uses_local_binary(self):
        cmd = hf.hf_cmd("render", "x")
        self.assertTrue(cmd[0].endswith("node_modules/.bin/hyperframes"), cmd[0])
        self.assertEqual(cmd[1:], ["render", "x"])

    def test_run_passes_env(self):
        seen = {}

        def runner(cmd, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        hf.run(["true"], Path("."), runner=runner)
        self.assertEqual(seen["env"]["HYPERFRAMES_NO_TELEMETRY"], "1")
        self.assertEqual(seen["env"]["DO_NOT_TRACK"], "1")
        self.assertTrue(seen["capture_output"])
        self.assertTrue(seen["text"])


class MissingTools(unittest.TestCase):
    def missing(self, cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    def test_missing_hyperframes_points_to_setup(self):
        with self.assertRaises(hf.ToolError) as cm:
            hf.run(hf.hf_cmd("render"), Path("."), runner=self.missing)
        self.assertIn("setup.py", str(cm.exception))

    def test_missing_ffmpeg_points_to_dnf(self):
        with self.assertRaises(hf.ToolError) as cm:
            hf.run(["ffmpeg", "-i", "x"], Path("."), runner=self.missing)
        self.assertIn("dnf install ffmpeg", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
