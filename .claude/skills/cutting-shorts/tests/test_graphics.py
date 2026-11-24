import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import helpers
import captions
import episode
import graphics
import shorts
from fakes import TEMPLATES, FakeRun

GRAPHIC = "/ep/broll/grafik/G1-1.mp4"
CHART = "/ep/broll/grafik/G2-1.mp4"
ARCHIVE = {"renders": [
    {"code": "G1-1", "file": "G1-1.mp4", "template": "number", "variant": "ev", "background": True,
     "vertical": False, "frames": 150, "values": {"value": "1,5", "unit": "°C"}},
    {"code": "G2-1", "file": "G2-1.mp4", "template": "bar-chart", "variant": "ev", "background": True,
     "vertical": False, "frames": 175, "values": {"line1": "x"}},
]}
LAYOUT = {"segments": [], "v1": [], "skipped": [], "teaser": [0, 50], "end_card": [900, 975], "frames": 975,
          "broll": [{"rec": 100, "end": 200, "track": 2, "file": GRAPHIC, "src_in": 0, "src_out": 100,
                     "kind": "graphic", "props": {}},
                    {"rec": 300, "end": 400, "track": 2, "file": CHART, "src_in": 0, "src_out": 100,
                     "kind": "graphic", "props": {}},
                    {"rec": 400, "end": 450, "track": 2, "file": "/ep/broll/stills/G1-1-hold-105.png",
                     "src_in": 0, "src_out": 50, "kind": "still", "props": {}, "hold_of": GRAPHIC}]}
WORDS = [{"start": 2, "end": 20, "text": "Fosil"}, {"start": 22, "end": 45, "text": "yakıtlar"},
         {"start": 60, "end": 80, "text": "sonra"}]
CAND = {"id": "c1", "title": "Fosil yakıt", "header": False}


class FakeEp:
    fps = 25
    m = {"title": "COP31"}


def request(templates, cand=CAND):
    return graphics.requests(FakeEp(), cand, LAYOUT, templates, ARCHIVE, words=WORDS)


class RequestsTest(unittest.TestCase):
    def test_graphic_vertical_rerender_request(self):
        rows, _, _ = request(TEMPLATES)
        row = next(r for r in rows if r["code"] == "G1-1")
        self.assertEqual(row, {"template": "number", "code": "G1-1", "fields": {"value": "1,5", "unit": "°C"},
                               "replaces": GRAPHIC, "variant": "ev", "background": True, "vertical": True, "frames": 150})
        self.assertEqual(sum(1 for r in rows if r["code"] == "G1-1"), 1)

    def test_archived_number_goes_back_as_text(self):
        number = {"base": "198", "exp": None, "text": "198"}
        archive = {"renders": [dict(ARCHIVE["renders"][0], values={"value": number, "unit": "taraf"})]}
        rows, _, _ = graphics.requests(FakeEp(), CAND, LAYOUT, TEMPLATES, archive, words=WORDS)
        row = next(r for r in rows if r["code"] == "G1-1")
        self.assertEqual(row["fields"], {"value": "198", "unit": "taraf"})

    def test_non_vertical_template_not_rerendered(self):
        rows, _, _ = request(TEMPLATES)
        self.assertNotIn("G2-1", [r["code"] for r in rows])

    def test_missing_template_placeholder_and_needed(self):
        rows, placeholders, needed = request(TEMPLATES, dict(CAND, header=True))
        self.assertEqual({p["template"] for p in placeholders}, {"teaser-caption", "end-card", "short-header"})
        self.assertEqual(len(needed), 3)
        self.assertTrue(any(n.startswith("teaser-caption") for n in needed))
        wm = next(r for r in rows if r["template"] == "watermark")
        self.assertEqual(wm["fields"], {"state": "static"})
        self.assertNotIn("vertical", wm)
        end = next(p for p in placeholders if p["template"] == "end-card")
        self.assertEqual(end["range"], [900, 975])
        self.assertIn("COP31", end["text"])
        _, placeholders, needed = request(TEMPLATES)
        self.assertNotIn("short-header", {p["template"] for p in placeholders})
        self.assertEqual(len(needed), 2)

    def test_teaser_caption_words_field(self):
        tpl = TEMPLATES + [{"name": "teaser-caption", "output": "overlay", "vertical": True, "fields": []},
                           {"name": "end-card", "output": "fullscreen", "vertical": True, "fields": []}]
        rows, placeholders, needed = request(tpl)
        row = next(r for r in rows if r["template"] == "teaser-caption")
        self.assertEqual(row["fields"], {"words": captions.teaser_words(WORDS, [0, 50])})
        self.assertEqual(row["fields"]["words"][-1], {"text": "yakıtlar", "start": 22, "end": 45})
        self.assertEqual(row["frames"], 50)
        self.assertTrue(row["vertical"])
        end = next(r for r in rows if r["template"] == "end-card")
        self.assertEqual((end["fields"], end["frames"]), ({"title": "COP31"}, 75))
        self.assertEqual(placeholders, [])
        self.assertEqual(needed, [])


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def tc(f):
    return f"00:{f // 1500:02d}:{f // 25 % 60:02d}:{f % 25:02d}"


def make_ep(tmp, broll=(), **extra):
    d = helpers.make_episode(tmp, frozen=[1], broll_frozen=[1],
                             clips=[{"clip": "A.MOV", "camera": "/cam/A.MOV", "offset_f": 0}], **extra)
    words = [{"text": f" kelime{k}", "start": tc(10 * k), "end": tc(10 * k + 8)} for k in range(200)]
    write(d / "transcripts" / "A-wav-tr.json", {"segments": [{"words": words}]})
    write(d / "script.json", {"headings": [{"level": 2, "title": "Bir"}],
                              "rows": [{"id": "R1", "key": "k1", "heading": 0, "ses": "kelime1 kelime2"}]})
    write(d / "sections.json", {"chapters": ["Bir"]})
    write(d / "shorts" / "layout" / "ch1.json",
          {"units": "frames", "timeline": "T ch1", "frames": 2000, "pieces": [[0, "A.MOV", 0, 2000]]})
    write(d / "shorts" / "broll" / "ch1.json", {"units": "frames", "timeline": "T ch1 B-roll", "items": list(broll)})
    cand = {"pieces": [{"chapter": 1, "start": 100, "end": 1000}], "teaser": {"chapter": 1, "start": 400, "end": 460},
            "title": "Bir", "header": False}
    write(d / "shorts" / "candidates.json", {"units": "frames", "candidates": [
        dict(cand, id="c1", accepted=True, frozen=False),
        dict(cand, id="c2", accepted=True, frozen=True),
        dict(cand, id="c3", accepted=False, frozen=False)]})
    return d


class PrepareTest(unittest.TestCase):
    def test_vertical_rerender_and_hold_still(self):
        """Ruling 2: a copied graphic with a vertical template is re-rendered vertical and its hold still is taken
        from the new render at the same hold_from; assets.json maps both old files to the new ones."""
        run, err = FakeRun(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            d0 = Path(tmp) / "src"
            g_old, h_old = str(d0 / "broll" / "grafik" / "G1-1.mp4"), str(d0 / "broll" / "stills" / "G1-1-hold-105.png")
            d = make_ep(tmp, title="COP31", broll=[
                {"track": 2, "start": 200, "end": 300, "file": g_old, "src_in": 0, "src_out": 100,
                 "kind": "graphic", "props": {}},
                {"track": 2, "start": 300, "end": 400, "file": h_old, "src_in": 0, "src_out": 100,
                 "kind": "still", "props": {}, "hold_of": g_old}])
            write(d / "broll" / "grafik" / "results.json", {"notes": [], "renders": [
                {"code": "G1-1", "file": "G1-1.mp4", "template": "number", "variant": "ev", "background": True,
                 "vertical": False, "frames": 150, "values": {"value": "1,5"}}]})
            write(d / "broll" / "fetched.json", {"units": "frames", "rows": {"k1": [
                {"kind": "graphic", "files": [{"file": g_old}], "hold": h_old, "hold_from": 105}]}})
            rc = shorts.prepare(episode.Episode(d), ["c1"], runner=run)
            self.assertEqual(rc, 0, err.getvalue())
            c1 = d / "shorts" / "c1"
            assets = json.loads((c1 / "assets.json").read_text(encoding="utf-8"))
            batch = json.loads((c1 / "grafik-batch.json").read_text(encoding="utf-8"))
        g_new, h_new = str(c1 / "grafik" / "G1-1-1.mp4"), str(c1 / "stills" / "G1-1-1-hold-105.png")
        self.assertEqual(assets["replace"], {g_old: g_new, h_old: h_new})
        row = next(r for r in batch if r["code"] == "G1-1")
        self.assertTrue(row["vertical"])
        self.assertNotIn("replaces", row)
        grab = [c for c in run.commands("ffmpeg") if c[-1] == h_new]
        self.assertEqual(len(grab), 1)
        self.assertEqual(grab[0][grab[0].index("-i") + 1], g_new)
        self.assertIn("select=eq(n\\,105)", grab[0][grab[0].index("-vf") + 1])
        self.assertIn("1 dikey B-roll grafiği", err.getvalue())  # the hold still is not counted as a graphic

    def test_missing_title_stops(self):
        run, err = FakeRun(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            d = make_ep(tmp)
            rc = shorts.prepare(episode.Episode(d), [], runner=run)
            self.assertFalse((d / "shorts" / "c1").exists())
        self.assertEqual(rc, 1)
        self.assertIn("episode.json'da 'title' yok (bitiş kartı için gerekli)", err.getvalue())
        self.assertEqual(run.calls, [])

    def test_prepare_skips_frozen_and_unaccepted(self):
        run, err = FakeRun(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            d = make_ep(tmp, title="COP31")
            rc = shorts.prepare(episode.Episode(d), [], runner=run)
            self.assertEqual(rc, 0, err.getvalue())
            self.assertTrue((d / "shorts" / "c1" / "assets.json").exists())
            self.assertFalse((d / "shorts" / "c2").exists())
            self.assertFalse((d / "shorts" / "c3").exists())
            assets = json.loads((d / "shorts" / "c1" / "assets.json").read_text(encoding="utf-8"))
            srt = (d / "shorts" / "c1" / "captions.srt").read_text(encoding="utf-8")
            rc_named = shorts.prepare(episode.Episode(d), ["c3"], runner=FakeRun())
        self.assertEqual(rc_named, 1)  # a named candidate that is not accepted is refused
        self.assertEqual(assets["units"], "frames")
        self.assertRegex(assets["teaser_cutout"][0]["file"].rsplit("/", 1)[1], r"^teaser-cutout-[0-9a-f]{8}\.mov$")
        roles = {g["role"]: g for g in assets["graphics"]}
        self.assertTrue(roles["teaser-caption"]["placeholder"])
        self.assertRegex(roles["teaser-caption"]["file"], r"/stills/teaser-caption-[0-9a-f]{8}\.png$")
        self.assertFalse(roles["watermark"]["placeholder"])
        self.assertEqual(roles["watermark"]["range"], [60, 960])
        self.assertIn("\nkelime", srt)
        self.assertNotIn("  ", srt)  # the transcript's padding spaces are not carried into the captions
        media = [c[2] for c in run.commands("shorts_media.py")]
        self.assertEqual(media, ["faces", "matte"])
        self.assertTrue(all(c[0].endswith(".venv/bin/python") for c in run.commands("shorts_media.py")))
        self.assertIn("Gereken şablonlar:", err.getvalue())


    def _cand(self, d, **teaser):
        path = d / "shorts" / "candidates.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["candidates"][0]["teaser"].update(teaser)
        path.write_text(json.dumps(data), encoding="utf-8")

    def _assets(self, d):
        return json.loads((d / "shorts" / "c1" / "assets.json").read_text(encoding="utf-8"))

    def test_cutout_and_placeholder_names_follow_their_content(self):
        """Final review 2: a changed teaser gives the cut-out a new file name (Resolve's media pool returns the
        clip imported earlier for the same path); the same inputs give the same name."""
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            d = make_ep(tmp, title="COP31")
            shorts.prepare(episode.Episode(d), ["c1"], runner=FakeRun())
            first = self._assets(d)
            shorts.prepare(episode.Episode(d), ["c1"], runner=FakeRun())
            again = self._assets(d)
            self._cand(d, end=480)
            shorts.prepare(episode.Episode(d), ["c1"], runner=FakeRun())
            moved = self._assets(d)
            media = json.loads((d / "shorts" / "c1" / "media.json").read_text(encoding="utf-8"))
        cut = [a["teaser_cutout"][0]["file"] for a in (first, again, moved)]
        self.assertEqual(cut[0], cut[1])
        self.assertNotEqual(cut[0], cut[2])
        self.assertEqual(media["cutouts"][0]["file"], cut[2])  # the matte job writes the new name
        self.assertEqual((moved["teaser_cutout"][0]["rec"], moved["teaser_cutout"][0]["end"]), (0, 80))
        roles = [{g["role"]: g["file"] for g in a["graphics"]} for a in (first, moved)]
        self.assertNotEqual(roles[0]["teaser-caption"], roles[1]["teaser-caption"])  # its text is the teaser's
        self.assertEqual(roles[0]["end-card"], roles[1]["end-card"])  # same text drawn: same file

    def test_unknown_camera_clip_is_a_turkish_error(self):
        """Final review 4: a camera piece the episode doesn't know stops that short only, with a Turkish line."""
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            d = make_ep(tmp, title="COP31")
            write(d / "shorts" / "layout" / "ch1.json",
                  {"units": "frames", "timeline": "T ch1", "frames": 2000,
                   "pieces": [[0, "A.MOV", 0, 300], [300, "B.MOV", 0, 1700]]})
            rc = shorts.prepare(episode.Episode(d), ["c1"], runner=FakeRun())
            self.assertFalse((d / "shorts" / "c1" / "captions.srt").exists())  # written only with assets.json
            self.assertFalse((d / "shorts" / "c1" / "assets.json").exists())
        self.assertEqual(rc, 1)
        self.assertIn("c1: hata: kamera parçası 'B.MOV' (bölüm 1) episode.json'un clips listesinde yok",
                      err.getvalue())

    def test_missing_chapter_layout_key_is_reported_per_short(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            d = make_ep(tmp, title="COP31")
            write(d / "shorts" / "broll" / "ch1.json", {"units": "frames", "timeline": "T ch1 B-roll"})
            rc = shorts.prepare(episode.Episode(d), ["c1"], runner=FakeRun())
        self.assertEqual(rc, 1)
        self.assertIn("c1: hata: eksik kayıt 'items'", err.getvalue())


if __name__ == "__main__":
    unittest.main()
