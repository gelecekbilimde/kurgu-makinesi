import io, json, shutil, tempfile, unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock
import helpers
from helpers import FIXTURES, make_episode
import episode, fetch, stills
from fakes import FakeRun

K2, K3, K5, K6, K7, K8 = "k0000002", "k0000003", "k0000005", "k0000006", "k0000007", "k0000008"
IDS = {K2: "R002", K3: "R003", K5: "R005", K6: "R006", K7: "R007", K8: "R008"}


def stock(q):
    return {"tag": "STOK", "kind": "stock", "query": q}


def graphic(template, fields=None, **kw):
    return {"tag": "GRAFİK", "kind": "graphic", "template": template,
            "fields": fields if fields is not None else {"line1": "a", "bars": ["x=1"], "name": "n"}, **kw}


class FetchBase(unittest.TestCase):
    def setUp(self):
        stills._font.cache_clear()
        stills._chrome.cache_clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = make_episode(self.tmp.name, frozen=[1, 2])
        for f in ("script.json", "sections.json"):
            shutil.copy(FIXTURES / f, self.d / f)
        self.ep = episode.Episode(str(self.d))

    def setup(self, requests, cov):
        """requests: {key: [req]}; cov: {key: frames | None}"""
        rows = {k: (None if f is None else {"id": IDS[k], "start": 100, "end": 100 + f}) for k, f in cov.items()}
        (self.d / "broll").mkdir(exist_ok=True)
        (self.d / "broll" / "rows.json").write_text(json.dumps(
            {"units": "frames", "fps": 25, "chapters": {"1": {"timeline": "TEST ch1", "rows": rows}}}))
        self.write_requests(requests)

    def write_requests(self, requests):
        (self.d / "broll" / "requests.json").write_text(
            json.dumps({"units": "frames", "rows": requests}, ensure_ascii=False), encoding="utf-8")

    def run_fetch(self, fake):
        with redirect_stderr(io.StringIO()):
            s = fetch.run(self.ep, runner=fake)
        self.fetched = json.loads((self.d / "broll" / "fetched.json").read_text(encoding="utf-8"))
        return s

    def asset(self, key, i=0):
        return self.fetched["rows"][key][i]


class StockTest(FetchBase):
    def test_batch_codes_counts_and_assets(self):
        self.setup({K2: [stock("rocket launch")], K3: [stock("black hole")]}, {K2: 175, K3: 425})
        fake = FakeRun(stock={"R002": [10.0, 6.5, 4.0], "R003": [3.99, 8, 8, 8]})
        self.run_fetch(fake)
        self.assertEqual(fake.batches["stock"], [[
            {"code": "R002", "query": "rocket launch", "orientation": "horizontal", "count": 3},
            {"code": "R003", "query": "black hole", "orientation": "horizontal", "count": 4}]])
        cmd = fake.tool_calls("find_stock.py")[0]
        self.assertEqual(cmd[cmd.index("--out") + 1], str(self.d / "broll" / "stok"))
        a = self.asset(K2)
        self.assertEqual(self.fetched["units"], "frames")
        self.assertEqual((a["tag"], a["kind"], a["track"], a["hold"], a["note"], a["code"]),
                         ("STOK", "stock", 2, None, None, "R002"))
        self.assertEqual([f["code"] for f in a["files"]], ["R002-1", "R002-2", "R002-3"])
        self.assertEqual([f["frames"] for f in a["files"]], [250, 162, 100])
        self.assertEqual(a["files"][0]["credit"], "Pixabay / user1")
        self.assertEqual(a["files"][0]["file"], str(self.d / "broll" / "stok" / "R002-1_pixabay-1.mp4"))
        self.assertEqual(self.asset(K3)["files"][0]["frames"], 99)

    def test_finder_exit_2_gives_placeholder(self):
        self.setup({K2: [stock("rocket launch")]}, {K2: 175})
        fake = FakeRun(stock={})
        s = self.run_fetch(fake)
        a = self.asset(K2)
        self.assertEqual((a["kind"], a["note"], a["track"]), ("placeholder", "aday bulunamadı", 2))
        self.assertTrue(a["files"][0]["file"].startswith(str(self.d / "broll" / "stills")))
        self.assertIsNone(a["files"][0]["frames"])
        self.assertTrue(Path(a["files"][0]["file"]).exists())
        self.assertEqual(s.placeholders, {"aday bulunamadı": 1})

    def test_changed_request_refetches_only_that_row(self):
        self.setup({K2: [stock("rocket launch")], K3: [stock("black hole")]}, {K2: 175, K3: 175})
        fake = FakeRun(stock={"R002": [10, 10, 10], "R003": [10, 10, 10]})
        self.run_fetch(fake)
        first = json.loads(json.dumps(self.fetched))
        old_files = [f["file"] for f in self.asset(K3)["files"]]

        fake2 = FakeRun(stock={"R002": [10, 10, 10], "R003": [9, 9, 9]})
        s = self.run_fetch(fake2)
        self.assertNotIn("stock", fake2.batches)  # nothing changed: no finder call
        self.assertEqual(self.fetched, first)
        self.assertEqual(s.cached, 2)

        self.write_requests({K2: [stock("rocket launch")], K3: [stock("supermassive black hole")]})
        s = self.run_fetch(fake2)
        self.assertEqual(fake2.batches["stock"], [[{"code": "R003", "query": "supermassive black hole",
                                                    "orientation": "horizontal", "count": 3}]])
        self.assertEqual(self.fetched["rows"][K2], first["rows"][K2])
        self.assertEqual([f["code"] for f in self.asset(K3)["files"]], ["R003-4", "R003-5", "R003-6"])
        self.assertNotEqual(self.asset(K3)["request_hash"], first["rows"][K3][0]["request_hash"])
        for f in old_files:
            self.assertTrue(Path(f).exists())  # old candidates are not deleted
        self.assertEqual((s.fetched, s.cached), (1, 1))

    def test_changed_second_request_keeps_its_own_code(self):
        a, b = stock("rocket launch"), stock("launch pad")
        self.setup({K5: [a, b]}, {K5: 175})
        fake = FakeRun(stock={"R005": [10, 10, 10], "R005b": [10, 10, 10]})
        self.run_fetch(fake)
        self.assertEqual([r["code"] for r in fake.batches["stock"][0]], ["R005", "R005b"])
        self.assertEqual([x["code"] for x in self.fetched["rows"][K5]][:2], ["R005", "R005b"])  # + YAZI: istek yok
        first_a = self.asset(K5, 0)

        self.write_requests({K5: [a, stock("empty launch pad")]})
        self.run_fetch(fake)
        self.assertEqual(fake.batches["stock"][1], [{"code": "R005b", "query": "empty launch pad",
                                                     "orientation": "horizontal", "count": 3}])
        self.assertEqual(self.asset(K5, 0), first_a)
        self.assertEqual(self.asset(K5, 1)["code"], "R005b")
        self.assertEqual([f["code"] for f in self.asset(K5, 1)["files"]], ["R005b-4", "R005b-5", "R005b-6"])

    def test_inserted_request_never_takes_a_kept_code(self):
        a = stock("rocket launch")
        self.setup({K5: [a]}, {K5: 175})
        fake = FakeRun(stock={"R005": [10], "R005b": [10]})
        self.run_fetch(fake)
        self.write_requests({K5: [stock("launch pad"), a]})  # new request in front of the fetched one
        self.run_fetch(fake)
        self.assertEqual([r["code"] for r in fake.batches["stock"][1]], ["R005b"])
        self.assertEqual([x["code"] for x in self.fetched["rows"][K5]][:2], ["R005b", "R005"])  # + YAZI: istek yok

    def test_finder_crash_is_retried(self):
        self.setup({K2: [stock("rocket launch")]}, {K2: 175})
        self.run_fetch(FakeRun(stock={}, stock_rc=1))
        self.assertEqual(self.asset(K2)["kind"], "placeholder")
        self.assertTrue(self.asset(K2)["note"].startswith("stok aracı hata verdi"))
        fake = FakeRun(stock={"R002": [10]})
        self.run_fetch(fake)
        self.assertEqual(self.asset(K2)["kind"], "stock")


class GraphicTest(FetchBase):
    def test_background_and_track(self):
        self.setup({K2: [graphic("bar-chart", {"line1": "a", "bars": ["x=1"], "source": "NASA"})],
                    K3: [graphic("name-line", {"name": "Begüm"})],
                    K5: [graphic("bar-chart", {"line1": "a", "bars": ["x=1"]}, background=False)]},
                   {K2: 200, K3: 100, K5: 200})
        fake = FakeRun()
        self.run_fetch(fake)
        (rows,) = fake.batches["graphic"]
        self.assertEqual(rows[0], {"template": "bar-chart", "code": "G002", "frames": 200, "background": True,
                                   "fields": {"line1": "a", "bars": ["x=1"], "source": "NASA"}})
        self.assertEqual((rows[1]["code"], rows[1]["background"]), ("G003", False))
        self.assertEqual((rows[2]["code"], rows[2]["background"]), ("G005", False))
        cmd = fake.tool_calls("make_graphic.py")[-1]
        self.assertEqual(cmd[cmd.index("--out") + 1], str(self.d / "broll" / "grafik"))
        a = self.asset(K2)
        self.assertEqual((a["kind"], a["track"]), ("graphic", 2))
        self.assertEqual(a["files"], [{"file": str(self.d / "broll" / "grafik" / "G002-1.mp4"), "code": "G002-1",
                                       "frames": 200, "credit": "NASA"}])
        self.assertEqual(self.asset(K3)["track"], 3)
        self.assertIsNone(self.asset(K3)["files"][0]["credit"])
        self.assertEqual(self.asset(K5)["track"], 3)

    def test_frames_clamped_and_hold_only_above_max(self):
        self.setup({K2: [graphic("bar-chart")], K3: [graphic("bar-chart")], K5: [graphic("bar-chart")]},
                   {K2: 50, K3: 200, K5: 425})
        fake = FakeRun()
        self.run_fetch(fake)
        self.assertEqual([r["frames"] for r in fake.batches["graphic"][0]], [100, 200, 375])
        for k in (K2, K3):
            self.assertEqual((self.asset(k)["hold"], self.asset(k)["hold_from"]), (None, None))
        hold = self.asset(K5)["hold"]
        self.assertTrue(hold.startswith(str(self.d / "broll" / "stills")))
        self.assertTrue(Path(hold).exists())
        self.assertEqual(self.asset(K5)["hold_from"], 262)  # round(375 * 0.7), make_graphic's POSTER_AT
        (ff,) = [c for c in fake.tool_calls("ffmpeg") if any(x.startswith("select=") for x in c)]
        self.assertIn(str(self.d / "broll" / "grafik" / "G005-1.mp4"), ff)
        self.assertIn(r"select=eq(n\,262)", ff)

    def test_coverage_change_refetches_graphic(self):
        self.setup({K2: [graphic("bar-chart")]}, {K2: 200})
        self.run_fetch(FakeRun())
        fake = FakeRun()
        self.setup({K2: [graphic("bar-chart")]}, {K2: 250})
        self.run_fetch(fake)
        self.assertEqual(fake.batches["graphic"][0][0]["frames"], 250)

    def test_changed_second_request_keeps_its_own_code(self):
        a = graphic("bar-chart", {"line1": "a", "bars": ["x=1"]})
        self.setup({K5: [a, graphic("name-line", {"name": "Begüm"})]}, {K5: 200})
        fake = FakeRun()
        self.run_fetch(fake)
        self.assertEqual([r["code"] for r in fake.batches["graphic"][0]], ["G005", "G005b"])
        first_a = self.asset(K5, 0)
        self.write_requests({K5: [a, graphic("name-line", {"name": "Begüm Dursun"})]})
        self.run_fetch(fake)
        self.assertEqual([r["code"] for r in fake.batches["graphic"][1]], ["G005b"])
        self.assertEqual(self.asset(K5, 0), first_a)
        self.assertEqual(self.asset(K5, 1)["code"], "G005b")
        self.assertEqual(self.asset(K5, 1)["files"][0]["code"], "G005b-2")

    def test_failed_graphic_gives_placeholder(self):
        self.setup({K2: [graphic("bar-chart")], K3: [graphic("bar-chart")]}, {K2: 200, K3: 200})
        s = self.run_fetch(FakeRun(graphic_fail={"G002": "çubuk değeri sayı değil"}))
        a = self.asset(K2)
        self.assertEqual((a["kind"], a["track"]), ("placeholder", 2))
        self.assertIn("çubuk değeri sayı değil", a["note"])
        self.assertEqual(self.asset(K3)["kind"], "graphic")
        self.assertEqual(s.placeholders, {"grafik üretilemedi": 1, "istek yok": 1})  # K2 is a STOK row

    def test_invalid_request_gives_placeholder(self):
        self.setup({K2: [graphic("bar-chart", {"bars": ["x=1"]})], K3: [stock(" ")]}, {K2: 200, K3: 200})
        fake = FakeRun()
        s = self.run_fetch(fake)
        a = self.asset(K2)
        self.assertEqual(a["kind"], "placeholder")
        self.assertEqual(a["note"], "geçersiz istek: eksik alan: line1")
        self.assertEqual(self.asset(K3)["note"], "geçersiz istek: query boş")
        self.assertNotIn("graphic", fake.batches)
        self.assertNotIn("stock", fake.batches)
        self.assertEqual(s.placeholders, {"geçersiz istek": 2, "istek yok": 2})  # tags not matching the rows

    def test_unknown_yazi_template_placeholder_on_v3(self):
        self.setup({K5: [{"tag": "YAZI", "kind": "graphic", "template": "alinti", "fields": {}}]}, {K5: 100})
        self.run_fetch(FakeRun())
        a = self.asset(K5)
        self.assertEqual((a["kind"], a["track"]), ("placeholder", 3))
        self.assertEqual(a["note"], "geçersiz istek: bilinmeyen şablon: 'alinti'")


class KaynakAndPlaceholderTest(FetchBase):
    def test_kaynak(self):
        self.setup({K6: [{"tag": "KAYNAK", "kind": "kaynak", "url": "https://example.com/a"}]}, {K6: 100})
        self.run_fetch(FakeRun())
        a = self.asset(K6)
        self.assertEqual((a["kind"], a["track"]), ("kaynak", 2))
        self.assertEqual(a["files"], [{"file": str(self.d / "broll" / "kaynak" / "R006.png"), "code": "R006",
                                       "frames": None, "credit": "https://example.com/a"}])

    def test_kaynak_blocked_gives_placeholder(self):
        self.setup({K6: [{"tag": "KAYNAK", "kind": "kaynak", "url": "https://example.com/a"}]}, {K6: 100})
        s = self.run_fetch(FakeRun(shot_size=1000))
        a = self.asset(K6)
        self.assertEqual((a["kind"], a["note"], a["track"]), ("placeholder", "sayfa engelli olabilir", 2))
        self.assertEqual(s.placeholders, {"sayfa engelli olabilir": 1})

    def test_kaynak_not_opened_is_retried(self):
        self.setup({K6: [{"tag": "KAYNAK", "kind": "kaynak", "url": "https://example.com/a"}]}, {K6: 100})
        self.run_fetch(FakeRun(shot_rc=1))
        a = self.asset(K6)
        self.assertEqual((a["kind"], a["note"], a["request_hash"]), ("placeholder", "sayfa açılmadı", None))
        stills._chrome.cache_clear()
        self.run_fetch(FakeRun())
        self.assertEqual(self.asset(K6)["kind"], "kaynak")
        self.assertIsNotNone(self.asset(K6)["request_hash"])

    def test_kaynak_blocked_is_not_retried(self):
        self.setup({K6: [{"tag": "KAYNAK", "kind": "kaynak", "url": "https://example.com/a"}]}, {K6: 100})
        self.run_fetch(FakeRun(shot_size=1000))
        self.assertIsNotNone(self.asset(K6)["request_hash"])
        stills._chrome.cache_clear()
        fake = FakeRun()
        self.run_fetch(fake)
        self.assertEqual(fake.tool_calls("chrome-headless-shell"), [])
        self.assertEqual(self.asset(K6)["note"], "sayfa engelli olabilir")

    def test_placeholder_requests(self):
        self.setup({K8: [{"tag": "ARŞİV", "kind": "placeholder", "reason": "arşiv"}],
                    K5: [stock("rocket"), {"tag": "YAZI", "kind": "placeholder", "reason": "no template",
                                           "need": "üç satırlık alıntı"}]},
                   {K8: 100, K5: 100})
        fake = FakeRun(stock={"R005": [10]})
        s = self.run_fetch(fake)
        a = self.asset(K8)
        self.assertEqual((a["kind"], a["track"], a["note"]), ("placeholder", 2, "arşiv"))
        y = self.asset(K5, 1)
        self.assertEqual((y["tag"], y["track"], y["note"]), ("YAZI", 3, "no template: üç satırlık alıntı"))
        self.assertEqual(self.asset(K5, 0)["kind"], "stock")
        draws = [" ".join(c) for c in fake.tool_calls("ffmpeg")]
        self.assertEqual(sum("pad=" in c for c in draws), 1)  # only the V3 placeholder is an overlay
        self.assertEqual(s.placeholders, {"arşiv": 1, "no template": 1})

    def test_unfound_rows_skipped_and_reported(self):
        self.setup({K2: [stock("x")]}, {K2: None})
        s = self.run_fetch(FakeRun())
        self.assertEqual(self.fetched["rows"], {})
        self.assertEqual(s.not_found, ["R002"])

    def test_summary_lines(self):
        self.setup({K2: [stock("x")], K8: [{"tag": "ARŞİV", "kind": "placeholder", "reason": "arşiv"}]},
                   {K2: 100, K8: 100})
        s = self.run_fetch(FakeRun(stock={"R002": [10]}))
        text = "\n".join(s.lines())
        self.assertIn("2 istek getirildi", text)
        self.assertIn("önbellek/arşivden 1 dosya", text)
        self.assertIn("arşiv: 1", text)

    def test_missing_rows_json(self):
        (self.d / "broll").mkdir()
        with self.assertRaises(fetch.FetchError):
            fetch.run(self.ep, runner=FakeRun())


class MissingRequestTest(FetchBase):
    def test_found_rows_without_a_request_get_istek_yok_placeholders(self):
        import build
        yazi = {"tag": "YAZI", "kind": "placeholder", "reason": "şablon yok"}
        self.setup({K5: [yazi]}, {K2: 100, K5: 100})  # K2 (STOK) has no request; K5 [STOK, YAZI] only YAZI's
        s = self.run_fetch(FakeRun())
        a = self.asset(K2)
        self.assertEqual((a["tag"], a["kind"], a["note"], a["request_hash"]), ("STOK", "placeholder", "istek yok", None))
        self.assertTrue(Path(a["files"][0]["file"]).exists())
        self.assertEqual([(x["tag"], x["note"]) for x in self.fetched["rows"][K5]],
                         [("YAZI", "şablon yok"), ("STOK", "istek yok")])
        self.assertEqual(s.placeholders, {"istek yok": 2, "şablon yok": 1})
        rows = json.loads((self.d / "broll" / "rows.json").read_text())["chapters"]["1"]["rows"]
        text = "\n".join(build.summary([(1, rows, [])], self.fetched, {"rows": {K5: [yazi]}}, IDS))
        self.assertIn("istek yok: R002 (STOK), R005 (STOK)", text)

    def test_istek_yok_is_reevaluated_when_the_request_arrives(self):
        self.setup({}, {K2: 100})
        self.run_fetch(FakeRun())
        self.assertEqual(self.asset(K2)["note"], "istek yok")
        self.write_requests({K2: [stock("rocket")]})
        s = self.run_fetch(FakeRun(stock={"R002": [10]}))
        self.assertEqual([x["kind"] for x in self.fetched["rows"][K2]], ["stock"])
        self.assertEqual(s.placeholders, {})


class MixedKameraRowTest(FetchBase):
    def setUp(self):
        super().setUp()
        sj = json.loads((self.d / "script.json").read_text(encoding="utf-8"))
        for r in sj["rows"]:
            if r["id"] in ("R002", "R003"):
                r["tags"] = ["KAMERA"] + r["tags"]
        (self.d / "script.json").write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")

    def test_mixed_row_requests_go_on_v3_and_fullscreen_graphics_lose_their_background(self):
        self.setup({K2: [stock("rocket")], K3: [graphic("bar-chart", {"line1": "a", "bars": ["x=1"]})]},
                   {K2: 100, K3: 200})
        fake = FakeRun(stock={"R002": [10]})
        self.run_fetch(fake)
        self.assertEqual(fake.batches["graphic"][0][0]["background"], False)
        self.assertEqual((self.asset(K2)["kind"], self.asset(K2)["track"]), ("stock", 3))
        self.assertEqual((self.asset(K3)["kind"], self.asset(K3)["track"]), ("graphic", 3))

    def test_mixed_row_placeholder_and_kaynak_on_v3(self):
        self.setup({K2: [{"tag": "STOK", "kind": "placeholder", "reason": "arşiv"}],
                    K3: [{"tag": "GRAFİK", "kind": "kaynak", "url": "https://example.com/a"}]}, {K2: 100, K3: 100})
        self.run_fetch(FakeRun())
        self.assertEqual((self.asset(K2)["kind"], self.asset(K2)["track"]), ("placeholder", 3))
        self.assertEqual((self.asset(K3)["kind"], self.asset(K3)["track"]), ("kaynak", 3))

    def test_mixed_row_without_request_gets_istek_yok_on_v3(self):
        self.setup({}, {K2: 100})
        self.run_fetch(FakeRun())
        self.assertEqual((self.asset(K2)["tag"], self.asset(K2)["note"], self.asset(K2)["track"]),
                         ("STOK", "istek yok", 3))


class CliTest(FetchBase):
    def test_fetch_subcommand(self):
        import broll
        summary = fetch.Summary()
        with mock.patch.object(fetch, "run", return_value=summary) as run, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(broll.main(["fetch", str(self.d)]), 0)
        self.assertEqual(run.call_args[0][0].dir, str(self.d))
        self.assertIn("istek getirildi", err.getvalue())


if __name__ == "__main__":
    unittest.main()
