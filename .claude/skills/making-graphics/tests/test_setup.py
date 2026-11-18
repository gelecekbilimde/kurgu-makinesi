import subprocess
import unittest

import helpers  # noqa: F401
import setup

ALL = {"node": "/usr/bin/node", "npm": "/usr/bin/npm", "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}


def which_of(present):
    return lambda name: present.get(name)


def node_version(v):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, v + "\n", "")


class Check(unittest.TestCase):
    def test_setup_ok(self):
        self.assertEqual(setup.check(which=which_of(ALL), run=node_version("v22.23.4")), [])

    def test_setup_reports_missing_ffmpeg(self):
        present = {k: v for k, v in ALL.items() if k not in ("ffmpeg", "ffprobe")}
        lines = setup.check(which=which_of(present), run=node_version("v22.1.0"))
        text = "\n".join(lines)
        self.assertIn("dnf install ffmpeg", text)
        self.assertIn("RPM Fusion", text)
        self.assertEqual(len([x for x in lines if "ffmpeg" in x.lower()]), 1, lines)

    def test_setup_reports_missing_node(self):
        present = {k: v for k, v in ALL.items() if k != "node"}
        text = "\n".join(setup.check(which=which_of(present), run=node_version("")))
        self.assertIn("Node 22", text)

    def test_setup_reports_old_node(self):
        text = "\n".join(setup.check(which=which_of(ALL), run=node_version("v20.11.0")))
        self.assertIn("Node 22", text)


if __name__ == "__main__":
    unittest.main()
