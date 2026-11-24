#!/usr/bin/env python3
"""Tests for Kurgu Makinesi. Run: python3 -m unittest -v test_kurgu   (needs ffmpeg for the media fixture)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import kurgu_makinesi as cli  # noqa: E402
from shared import capcut, kdenlive, premiere, shotcut  # noqa: E402
from shared.script_parser import Script, extract_chapters  # noqa: E402
from shared.timeline import PlanError, load_cutplan  # noqa: E402

SCRIPT = "## Intro\n#intro\nHello there.\n\n## Main: part 1\n#main\nBody text.\n\n## Outro\nBye.\n"


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed for the media fixture")
class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.media = cls.tmp / "cam.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=10", "-shortest", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.media)], check=True)
        cls.silent = cls.tmp / "mute.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25:duration=4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.silent)], check=True)
        cls.script = cls.tmp / "script.md"
        cls.script.write_text(SCRIPT, encoding="utf-8")
        cls.plan = cls.tmp / "plan.json"
        cls.plan.write_text(json.dumps({"name": "ep1", "clips": [
            {"file": "cam.mp4", "in": 1.0, "out": 3.0, "chapter": 1},
            {"file": "cam.mp4", "in": 4.0, "out": 6.5, "chapter": 1},
            {"file": "cam.mp4", "in": 7.0, "out": 9.0, "chapter": 2},
            {"file": "mute.mp4", "in": 0, "out": 2.0, "chapter": "Outro"}]}), encoding="utf-8")
        chapters = Script(str(cls.script)).load().titles
        cls.tl, cls.warn = load_cutplan(str(cls.plan), chapters)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestParser(unittest.TestCase):
    def test_chapters_have_content_and_tags_are_excluded(self):
        ch = extract_chapters(SCRIPT)
        self.assertEqual([c["title"] for c in ch], ["Intro", "Main: part 1", "Outro"])
        self.assertEqual(ch[0]["content"], "Hello there.")
        self.assertNotIn("#main", ch[1]["content"])

    def test_script_tags(self):
        p = Path(tempfile.mkdtemp()) / "s.md"
        p.write_text(SCRIPT, encoding="utf-8")
        self.assertEqual(Script(str(p)).load().tags, {"#intro", "#main"})


class TestModel(Base):
    def test_frames_and_layout(self):
        self.assertEqual(self.tl.fps_num, 25)
        self.assertEqual((self.tl.width, self.tl.height), (320, 180))
        # 2.0 + 2.5 + 2.0 + 2.0 s = 8.5 s = 212.5 -> per clip rounding: 50 + 62(.5->62) + 50 + 50
        self.assertEqual([p.end - p.start for p in self.tl.layout()], [50, 62, 50, 50])
        self.assertEqual(self.tl.total_frames, 212)

    def test_markers_only_when_chapter_changes(self):
        m = self.tl.markers()
        self.assertEqual([(x.frame, x.text) for x in m], [(0, "Intro"), (112, "Main: part 1"), (162, "Outro")])

    def test_audio_probe(self):
        self.assertEqual([c.has_audio for c in self.tl.clips], [True, True, True, False])

    def test_bad_plans(self):
        d = self.tmp
        bad = d / "bad.json"
        bad.write_text(json.dumps({"clips": [{"file": "cam.mp4", "in": 5, "out": 3}]}))
        with self.assertRaises(PlanError):
            load_cutplan(str(bad))
        bad.write_text(json.dumps({"clips": [{"file": "cam.mp4", "in": 0, "out": 99}]}))
        with self.assertRaises(PlanError):
            load_cutplan(str(bad))
        bad.write_text("{not json")
        with self.assertRaises(PlanError):
            load_cutplan(str(bad))
        bad.write_text(json.dumps({"clips": []}))
        with self.assertRaises(PlanError):
            load_cutplan(str(bad))

    def test_clock(self):
        self.assertEqual(self.tl.clock(112), "00:00:04.480")
        self.assertEqual(self.tl.clock(25 * 3725), "01:02:05.000")


class TestShotcut(Base):
    def test_structure(self):
        root = shotcut.build(self.tl).getroot()
        self.assertEqual(root.tag, "mlt")
        self.assertEqual(len(root.findall("chain")), 2)          # cam.mp4 once, mute.mp4 once
        entries = root.find("playlist[@id='playlist0']").findall("entry")
        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0].get("in"), "00:00:01.000")
        self.assertEqual(entries[0].get("out"), "00:00:02.960")  # 50 frames from 1.0s, out inclusive
        tr = root.find("tractor")
        props = {p.get("name"): p.text for p in tr.findall("property")}
        self.assertEqual(props["shotcut:markers:1:text"], "Main: part 1")
        self.assertEqual(props["shotcut:markers:1:start"], "00:00:04.480")
        self.assertEqual(props["shotcut:markers:2:color"], "#00aa00")
        self.assertEqual(tr.get("out"), tl_clock(self.tl, 211))
        self.assertEqual([t.get("producer") for t in tr.findall("track")], ["background", "playlist0"])

    def test_every_entry_producer_exists(self):
        root = shotcut.build(self.tl).getroot()
        ids = {e.get("id") for e in root if e.tag in ("chain", "producer", "playlist")}
        for e in root.iter("entry"):
            self.assertIn(e.get("producer"), ids)


class TestKdenlive(Base):
    def setUp(self):
        self.root = kdenlive.build(self.tl).getroot()

    def test_guides_json(self):
        main = self.root.find("playlist[@id='main_bin']")
        props = {p.get("name"): p.text for p in main.findall("property")}
        guides = json.loads(props["kdenlive:docproperties.guides"])
        self.assertEqual([(g["pos"], g["comment"]) for g in guides], [(0, "Intro"), (112, "Main: part 1"), (162, "Outro")])
        self.assertEqual(props["kdenlive:docproperties.version"], "1.04")

    def test_bin_ids_and_entries(self):
        bin_ids = {p.text for pr in self.root.findall("producer") for p in pr.findall("property")
                   if p.get("name") == "kdenlive:id"}
        self.assertEqual(bin_ids, {"2", "3"})
        tracks = {t.get("id"): t for t in self.root.findall("tractor")}
        main = self.root.findall("tractor")[-1]
        self.assertEqual([t.get("producer") for t in main.findall("track")],
                         ["black_track", "tractor0", "tractor1", "tractor2", "tractor3"])
        # V1 (tractor2) holds 4 video entries, A1 (tractor1) holds 3 audio entries (the 4th clip has no audio)
        def entries(tid):
            return [e for t in tracks[tid].findall("track")
                    for pl in self.root.findall(f"playlist[@id='{t.get('producer')}']") for e in pl.findall("entry")]
        self.assertEqual(len(entries("tractor2")), 4)
        self.assertEqual(len(entries("tractor1")), 3)
        self.assertEqual(len(entries("tractor0")), 0)

    def test_entry_producers_defined_before_use(self):
        order = [e.get("id") for e in self.root]
        for pl in self.root.findall("playlist"):
            for e in pl.findall("entry"):
                self.assertIn(e.get("producer"), order)
                self.assertLess(order.index(e.get("producer")), order.index(pl.get("id")) if pl.get("id") != "main_bin"
                                else len(order))

    def test_audio_video_split_flags(self):
        for pr in self.root.findall("producer"):
            props = {p.get("name"): p.text for p in pr.findall("property")}
            if "set.test_image" in props and props.get("resource") != "black":
                self.assertNotEqual(props["set.test_image"], props["set.test_audio"])

    def test_unique_ids(self):
        ids = [e.get("id") for e in self.root.iter() if e.get("id")]
        self.assertEqual(len(ids), len(set(ids)))


class TestPremiere(Base):
    def setUp(self):
        self.root = premiere.build(self.tl).getroot()

    def test_sequence(self):
        seq = self.root.find("sequence")
        self.assertEqual(seq.find("duration").text, "212")
        self.assertEqual(seq.find("rate/timebase").text, "25")
        self.assertEqual(seq.find("rate/ntsc").text, "FALSE")
        self.assertEqual([m.find("name").text for m in seq.findall("marker")], ["Intro", "Main: part 1", "Outro"])
        self.assertEqual([m.find("in").text for m in seq.findall("marker")], ["0", "112", "162"])

    def test_tracks_and_timing(self):
        v = self.root.findall("sequence/media/video/track/clipitem")
        self.assertEqual([(c.find("start").text, c.find("end").text, c.find("in").text, c.find("out").text) for c in v],
                         [("0", "50", "25", "75"), ("50", "112", "100", "162"),
                          ("112", "162", "175", "225"), ("162", "212", "0", "50")])
        a = self.root.findall("sequence/media/audio/track")
        self.assertEqual([len(t.findall("clipitem")) for t in a], [3, 3])   # muted clip has no audio items

    def test_file_defined_once_then_referenced(self):
        files = list(self.root.iter("file"))
        full = [f for f in files if f.find("pathurl") is not None]
        self.assertEqual(len(full), 2)
        self.assertTrue(all(f.find("pathurl").text.startswith("file://localhost/") for f in full))
        ids = [f.get("id") for f in full]
        self.assertEqual(sorted(ids), ["file-1", "file-2"])
        for f in files:
            self.assertIn(f.get("id"), ids)

    def test_links_reference_real_clipitems(self):
        ids = {c.get("id") for c in self.root.iter("clipitem")}
        self.assertEqual(len(ids), len(list(self.root.iter("clipitem"))))
        for ref in self.root.iter("linkclipref"):
            self.assertIn(ref.text, ids)

    def test_ntsc(self):
        from fractions import Fraction
        import copy
        tl = copy.copy(self.tl)
        tl.fps = Fraction(30000, 1001)
        r = premiere.build(tl).getroot()
        self.assertEqual((r.find("sequence/rate/timebase").text, r.find("sequence/rate/ntsc").text), ("30", "TRUE"))


class TestCapcut(Base):
    def test_draft(self):
        d = capcut.build(self.tl)
        self.assertEqual(d["canvas_config"]["width"], 320)
        segs = d["tracks"][0]["segments"]
        self.assertEqual(len(segs), 4)
        self.assertEqual(segs[0]["target_timerange"], {"start": 0, "duration": 2_000_000})
        self.assertEqual(segs[0]["source_timerange"], {"start": 1_000_000, "duration": 2_000_000})
        self.assertEqual(segs[1]["target_timerange"]["start"], 2_000_000)
        self.assertEqual(d["duration"], 8_480_000)
        mats = {m["id"] for m in d["materials"]["videos"]}
        self.assertTrue(all(s["material_id"] in mats for s in segs))
        speeds = {m["id"] for m in d["materials"]["speeds"]}
        self.assertTrue(all(r in speeds for s in segs for r in s["extra_material_refs"]))

    def test_chapters_txt(self):
        self.assertEqual(capcut.chapters_text(self.tl), "00:00 Intro\n00:04 Main: part 1\n00:06 Outro\n")


class TestCli(Base):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(Path(__file__).parent / "kurgu_makinesi.py"), *args],
                              capture_output=True, text=True)

    def test_help(self):
        r = self.run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Rough Cutting Tool", r.stdout)

    def test_import_all_writes_wellformed_files(self):
        out = self.tmp / "out"
        r = self.run_cli("import", str(self.plan), "--script", str(self.script), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
        self.assertEqual(files, ["ep1.kdenlive", "ep1.mlt", "ep1.xml", "ep1/chapters.txt",
                                 "ep1/draft_content.json", "ep1/draft_meta_info.json"])
        for f in ("ep1.kdenlive", "ep1.mlt"):
            ET.parse(out / f)
        json.loads((out / "ep1/draft_content.json").read_text())
        if shutil.which("xmllint"):
            for f in ("ep1.kdenlive", "ep1.mlt"):
                self.assertEqual(subprocess.run(["xmllint", "--noout", str(out / f)]).returncode, 0)
            # xmeml has a DOCTYPE without a DTD: check well-formedness only
            self.assertEqual(subprocess.run(["xmllint", "--noout", str(out / "ep1.xml")],
                                            capture_output=True).returncode, 0)
        self.assertIn("Intro", (out / "ep1.mlt").read_text(encoding="utf-8"))

    def test_import_single_format_and_name(self):
        out = self.tmp / "o2"
        r = self.run_cli("import", str(self.plan), "--format", "shotcut", "--name", "Çalışma 1", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p.name for p in out.iterdir()], ["Çalışma 1.mlt"])

    def test_bad_input_is_an_error_not_a_traceback(self):
        r = self.run_cli("import", str(self.tmp / "nope.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not found", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


def tl_clock(tl, frames):
    return tl.clock(frames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
