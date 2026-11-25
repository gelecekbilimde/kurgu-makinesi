"""Automated test suite for Kurgu Makinesi multi-editor implementation.

Validates Kdenlive (.kdenlive), Shotcut (.mlt), Adobe Premiere Pro (FCP7 .xml),
and CapCut (draft folder) across:
- Multi-track A-roll (V1), synced external WAV (A2/A1/A3-A4), B-roll (V2), Overlays (V3)
- Kdenlive A/V grouping JSON (kdenlive:docproperties.groups)
- Shotcut frei0r.cairoblend compositing and qimage still producers
- Premiere Pro <link> groups and <pproColor> markers
- CapCut multi-track draft_content.json, native text track, chapters.txt, markers.json
- Color-coded point & range markers + round-trip marker feedback readback
- Per-chapter splitting & freeze/unfreeze skipping
- Vertical Shorts (1080x1920, face crop transform, SRT captions)
- Both `import` and `make` CLI subcommands
"""

from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import kurgu_makinesi
from shared import (
    CropRect,
    load_cutplan,
    read_markers,
    write_capcut,
    write_edits_json,
    write_kdenlive,
    write_premiere,
    write_shotcut,
)

ROOT = Path(__file__).resolve().parent
SAMPLE_CUTPLAN = ROOT / "examples" / "sample_cutplan.json"
SAMPLE_SHORT_PLAN = ROOT / "examples" / "sample_short_plan.json"
SAMPLE_SCRIPT = ROOT / "examples" / "sample_script.md"


class TestKurguMultiEditor(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_kdenlive_multitrack_grouping_and_readback(self) -> None:
        tl = load_cutplan(SAMPLE_CUTPLAN, script_path=SAMPLE_SCRIPT)
        kdenlive_file = write_kdenlive(tl, self.out)
        self.assertTrue(kdenlive_file.exists())
        self.assertTrue((self.out / f"{tl.name}.srt").exists())

        root = ET.parse(str(kdenlive_file)).getroot()
        # Verify 5 track playlists (A2, A1, V1, V2, V3)
        playlists = {pl.attrib["id"]: pl for pl in root.findall("playlist")}
        for pid in ("playlist_a2", "playlist_a1", "playlist_v1", "playlist_v2", "playlist_v3"):
            self.assertIn(pid, playlists)

        self.assertEqual(len(playlists["playlist_v1"].findall("entry")), 3)
        self.assertEqual(len(playlists["playlist_a2"].findall("entry")), 3)
        self.assertEqual(len(playlists["playlist_v2"].findall("entry")), 2)
        self.assertEqual(len(playlists["playlist_v3"].findall("entry")), 1)

        # Verify A/V grouping property exists and links V1 with synced A2
        groups_prop = root.find(".//property[@name='kdenlive:docproperties.groups']")
        self.assertIsNotNone(groups_prop)
        groups = json.loads(groups_prop.text or "[]")
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0]["type"], "AVSplit")

        # Verify round-trip Yellow marker readback
        yellow_markers = read_markers(kdenlive_file, color_filter="Yellow")
        self.assertEqual(len(yellow_markers), 1)
        self.assertEqual(yellow_markers[0].frame, 24 * 25)
        self.assertEqual(yellow_markers[0].duration_frames, 3 * 25)

    def test_shotcut_multitrack_cairoblend_and_readback(self) -> None:
        tl = load_cutplan(SAMPLE_CUTPLAN, script_path=SAMPLE_SCRIPT)
        mlt_file = write_shotcut(tl, self.out)
        self.assertTrue(mlt_file.exists())

        root = ET.parse(str(mlt_file)).getroot()
        playlists = {pl.attrib["id"]: pl for pl in root.findall("playlist")}
        self.assertEqual(len(playlists["playlist0"].findall("entry")), 3)  # V1
        self.assertEqual(len(playlists["playlist1"].findall("entry")), 2)  # V2 B-roll
        self.assertEqual(len(playlists["playlist2"].findall("entry")), 1)  # V3 Overlays
        self.assertEqual(len(playlists["playlist3"].findall("entry")), 3)  # A1 External WAV

        # Verify qimage used for PNG graphics/screenshots
        services = [p.text for p in root.findall(".//producer/property[@name='mlt_service']")]
        self.assertIn("qimage", services)

        # Verify frei0r.cairoblend compositing transitions
        transitions = [p.text for p in root.findall(".//tractor/transition/property[@name='mlt_service']")]
        self.assertIn("frei0r.cairoblend", transitions)
        self.assertIn("mix", transitions)

        # Verify round-trip Yellow marker readback
        yellow_markers = read_markers(mlt_file, color_filter="Yellow")
        self.assertEqual(len(yellow_markers), 1)
        self.assertEqual(yellow_markers[0].frame, 24 * 25)
        self.assertEqual(yellow_markers[0].duration_frames, 3 * 25)

    def test_premiere_fcp7_xml_multitrack_and_readback(self) -> None:
        tl = load_cutplan(SAMPLE_CUTPLAN, script_path=SAMPLE_SCRIPT)
        xml_file = write_premiere(tl, self.out)
        self.assertTrue(xml_file.exists())

        root = ET.parse(str(xml_file)).getroot()
        self.assertEqual(root.tag, "xmeml")
        vtracks = root.findall(".//sequence/media/video/track")
        atracks = root.findall(".//sequence/media/audio/track")
        self.assertEqual(len(vtracks), 3)
        self.assertEqual(len(atracks), 4)
        self.assertEqual(len(vtracks[0].findall("clipitem")), 3)
        self.assertEqual(len(vtracks[1].findall("clipitem")), 2)
        self.assertEqual(len(vtracks[2].findall("clipitem")), 1)
        self.assertEqual(len(atracks[2].findall("clipitem")), 3)  # External WAV L

        # Verify round-trip Yellow marker readback
        yellow_markers = read_markers(xml_file, color_filter="Yellow")
        self.assertEqual(len(yellow_markers), 1)
        self.assertEqual(yellow_markers[0].frame, 24 * 25)
        self.assertEqual(yellow_markers[0].duration_frames, 3 * 25)

    def test_capcut_multitrack_captions_and_readback(self) -> None:
        tl = load_cutplan(SAMPLE_CUTPLAN, script_path=SAMPLE_SCRIPT)
        draft_dir = write_capcut(tl, self.out)
        self.assertTrue((draft_dir / "draft_content.json").exists())
        self.assertTrue((draft_dir / "draft_meta_info.json").exists())
        self.assertTrue((draft_dir / "chapters.txt").exists())
        self.assertTrue((draft_dir / "markers.json").exists())
        self.assertTrue((draft_dir / f"{tl.name}.srt").exists())

        content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
        track_types = [t["type"] for t in content["tracks"]]
        self.assertEqual(track_types.count("video"), 3)
        self.assertEqual(track_types.count("audio"), 1)
        self.assertEqual(track_types.count("text"), 1)

        chapters_txt = (draft_dir / "chapters.txt").read_text(encoding="utf-8")
        self.assertIn("00:00 ch1 Giriş", chapters_txt)
        self.assertIn("00:22 ch2 Bilimsel Arka Plan", chapters_txt)

        yellow_markers = read_markers(draft_dir, color_filter="Yellow")
        self.assertEqual(len(yellow_markers), 1)
        self.assertEqual(yellow_markers[0].frame, 24 * 25)
        self.assertEqual(yellow_markers[0].duration_frames, 3 * 25)

    def test_vertical_shorts_crop_and_cli_commands(self) -> None:
        tl = load_cutplan(SAMPLE_CUTPLAN, script_path=SAMPLE_SCRIPT, vertical_short=True)
        tl.clips[0].crop = CropRect(scale=1.7778, center_x=0.45, center_y=0.5)
        self.assertEqual((tl.width, tl.height), (1080, 1920))

        # Test all 4 writers in vertical mode
        k_file = write_kdenlive(tl, self.out / "v_kdenlive")
        s_file = write_shotcut(tl, self.out / "v_shotcut")
        p_file = write_premiere(tl, self.out / "v_premiere")
        c_dir = write_capcut(tl, self.out / "v_capcut")

        self.assertIn("1080", k_file.read_text(encoding="utf-8"))
        self.assertIn("affineSizePosition", s_file.read_text(encoding="utf-8"))
        self.assertIn("Basic Motion", p_file.read_text(encoding="utf-8"))
        cc = json.loads((c_dir / "draft_content.json").read_text(encoding="utf-8"))
        self.assertEqual(cc["canvas_config"]["ratio"], "9:16")

        # Test CLI `make` alias + `--chapters` + `freeze` + `read-markers`
        rc = kurgu_makinesi.main(["freeze", "1", "--out", str(self.out / "cli_out")])
        self.assertEqual(rc, 0)
        rc = kurgu_makinesi.main(
            [
                "make",
                "shotcut",
                str(SAMPLE_CUTPLAN),
                "--script",
                str(SAMPLE_SCRIPT),
                "--chapters",
                "--out",
                str(self.out / "cli_out"),
            ]
        )
        self.assertEqual(rc, 0)
        ch_files = list((self.out / "cli_out" / "chapters").glob("*.mlt"))
        # Chapter 1 was frozen, so only Chapter 2 should be generated
        self.assertEqual(len(ch_files), 1)
        self.assertIn("ch2", ch_files[0].name)

        edits_out = self.out / "edits.json"
        rc = kurgu_makinesi.main(
            [
                "read-markers",
                str(self.out / "cli_out" / "gb_ep01_ornek.mlt"),
                "--color",
                "Yellow",
                "--out",
                str(edits_out),
            ]
        )
        self.assertEqual(rc, 0)
        edits_data = json.loads(edits_out.read_text(encoding="utf-8"))
        self.assertEqual(len(edits_data["edits"]), 1)
        self.assertEqual(edits_data["edits"][0]["start_f"], 600)
        self.assertEqual(edits_data["edits"][0]["end_f"], 675)

        # Test bundled shorts example via CLI `shorts` subcommand
        shorts_out = self.out / "cli_shorts"
        rc = kurgu_makinesi.main(
            ["shorts", str(SAMPLE_SHORT_PLAN), "--format", "all", "--out", str(shorts_out)]
        )
        self.assertEqual(rc, 0)
        self.assertTrue((shorts_out / "kdenlive" / "gb_ep01_short_ornek.kdenlive").exists())
        self.assertTrue((shorts_out / "shotcut" / "gb_ep01_short_ornek.mlt").exists())
        self.assertTrue((shorts_out / "premiere" / "gb_ep01_short_ornek.xml").exists())
        self.assertTrue((shorts_out / "capcut" / "gb_ep01_short_ornek" / "draft_content.json").exists())


if __name__ == "__main__":
    unittest.main()
