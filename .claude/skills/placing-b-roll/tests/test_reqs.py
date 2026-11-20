import json, shutil, subprocess, sys, tempfile, unittest
import helpers
from helpers import FIXTURES, SCRIPTS, make_episode
import episode, rows, reqs


def row(tags, links=(), key="abc"):
    return rows.Row(id="R1", key=key, chapter=0, tags=list(tags), visual="v",
                    links=list(links), refs=[], ses="s", est_s=5)


TEMPLATES = {"baslik": {"name": "baslik", "fields": [
    {"name": "text", "type": "str", "required": True, "help": ""},
    {"name": "sub", "type": "str", "required": False, "help": ""}]}}


class ReqsTest(unittest.TestCase):
    def test_autofill(self):
        self.assertEqual(reqs.autofill(row(["ARŞİV"])),
                         [{"tag": "ARŞİV", "kind": "placeholder", "reason": "arşiv"}])
        self.assertEqual(reqs.autofill(row(["KAYNAK"], ["u1", "u2"])),
                         [{"tag": "KAYNAK", "kind": "kaynak", "url": "u1"}])
        self.assertEqual(reqs.autofill(row(["KAYNAK"])),
                         [{"tag": "KAYNAK", "kind": "placeholder", "reason": "link yok"}])
        self.assertEqual(reqs.autofill(row(["STOK"])), [])

    def test_pending(self):
        r = row(["STOK", "YAZI"])
        data = {"units": "frames", "rows": {"abc": [{"tag": "STOK", "kind": "stock", "query": "x"}]}}
        self.assertEqual(reqs.pending([r], data), [r])
        data["rows"]["abc"].append({"tag": "YAZI", "kind": "graphic", "template": "baslik", "fields": {}})
        self.assertEqual(reqs.pending([r], data), [])

    def test_validate(self):
        ok = {"tag": "GRAFİK", "kind": "graphic", "template": "baslik", "fields": {"text": "a"}}
        self.assertEqual(reqs.validate(ok, TEMPLATES), [])
        self.assertTrue(reqs.validate({**ok, "template": "yok"}, TEMPLATES))
        self.assertTrue(reqs.validate({**ok, "fields": {}}, TEMPLATES))
        self.assertTrue(reqs.validate({"tag": "STOK", "kind": "stock", "query": " "}, TEMPLATES))
        self.assertEqual(reqs.validate({"tag": "STOK", "kind": "stock", "query": "roket"}, TEMPLATES), [])

    def test_load_save(self):
        with tempfile.TemporaryDirectory() as t:
            p = t + "/broll/requests.json"
            self.assertEqual(reqs.load(p), {"units": "frames", "rows": {}})
            reqs.save(p, {"units": "frames", "rows": {"a": []}})
            self.assertEqual(reqs.load(p)["rows"], {"a": []})


class CliTest(unittest.TestCase):
    def test_requests_idempotent_keeps_edits(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_episode(t, frozen=[1, 2])
            for f in ("script.json", "sections.json"):
                shutil.copy(FIXTURES / f, d / f)

            def run():
                return subprocess.run([sys.executable, str(SCRIPTS / "broll.py"), "requests", str(d)],
                                      capture_output=True, text=True)
            p = run()
            self.assertEqual(p.returncode, 0, p.stderr)
            path = d / "broll" / "requests.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["rows"]["k0000006"][0]["url"], "https://example.com/a")
            self.assertEqual(data["rows"]["k0000008"][0]["reason"], "arşiv")
            self.assertIn("R002", p.stdout)
            data["rows"]["k0000006"][0]["url"] = "https://edited"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run().returncode, 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["rows"]["k0000006"][0]["url"], "https://edited")
            self.assertEqual(len(data["rows"]["k0000006"]), 1)


if __name__ == "__main__":
    unittest.main()
