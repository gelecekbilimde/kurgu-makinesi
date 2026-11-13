import json
import threading
import unittest
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import helpers  # noqa: F401  (sets sys.path)
from cache import Cache  # noqa: E402
from http_client import Http  # noqa: E402
from model import SourceError  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.seen.append((self.path, self.headers.get("User-Agent")))
        if self.path.startswith("/json"):
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/limit"):
            self.send_response(429)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path.startswith("/file"):
            body = b"x" * 100_000
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/broken"):
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            self.wfile.write(b"x" * 1000)
            self.close_connection = True


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.seen.clear()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.t = [1000.0]
        self.http = Http(Cache(self.root / "cache"), clock=lambda: self.t[0])

    def test_second_call_served_from_cache(self):
        a = self.http.get_json("s", self.base + "/json", {"q": "x"})
        b = self.http.get_json("s", self.base + "/json", {"q": "x"})
        self.assertEqual(a, {"ok": True})
        self.assertEqual(a, b)
        self.assertEqual(len(Handler.seen), 1)

    def test_cache_expires_after_a_day(self):
        self.http.get_json("s", self.base + "/json", {"q": "x"})
        self.t[0] += 86401
        self.http.get_json("s", self.base + "/json", {"q": "x"})
        self.assertEqual(len(Handler.seen), 2)

    def test_secret_not_in_cache_key_or_file(self):
        self.http.get_json("s", self.base + "/json", {"key": "SECRET", "q": "x"}, secret_params=("key",))
        self.http.get_json("s", self.base + "/json", {"key": "OTHER", "q": "x"}, secret_params=("key",))
        self.assertEqual(len(Handler.seen), 1)
        self.assertIn("SECRET", Handler.seen[0][0])  # the key is sent ...
        for p in (self.root / "cache").rglob("*"):
            if p.is_file():
                self.assertNotIn("SECRET", p.read_text())  # ... but never stored

    def test_headers_not_stored(self):
        self.http.get_json("s", self.base + "/json", {"q": "y"}, headers={"Authorization": "SECRET"})
        for p in (self.root / "cache").rglob("*"):
            if p.is_file():
                self.assertNotIn("SECRET", p.read_text())

    def test_429_raises_source_error(self):
        with self.assertRaises(SourceError) as cm:
            self.http.get_json("pixabay", self.base + "/limit", {"key": "SECRET"}, secret_params=("key",))
        self.assertIn("429", str(cm.exception))
        self.assertNotIn("SECRET", str(cm.exception))
        self.assertEqual(cm.exception.slug, "pixabay")

    def test_network_error_raises_source_error(self):
        with self.assertRaises(SourceError):
            self.http.get_json("s", "http://127.0.0.1:1/json", {})

    def test_user_agent(self):
        self.http.get_json("s", self.base + "/json", {"q": "ua"})
        self.assertEqual(Handler.seen[0][1], "stock-finder/1.0")

    def test_interrupted_download_leaves_nothing(self):
        dest = self.root / "clips" / "x.mp4"
        with self.assertRaises(SourceError):
            self.http.download("s", self.base + "/broken", dest)
        self.assertFalse(dest.exists())
        self.assertFalse(dest.with_suffix(".part").exists())

    def test_download_ok(self):
        dest = self.root / "clips" / "x.mp4"
        self.http.download("s", self.base + "/file", dest)
        self.assertEqual(dest.read_bytes(), b"x" * 100_000)
        self.assertFalse(dest.with_suffix(".part").exists())

    def test_incomplete_read_is_a_source_error(self):
        import http.client
        from unittest import mock
        err = http.client.IncompleteRead(b"x", 10)
        with mock.patch("http_client.urllib.request.urlopen", side_effect=err):
            with self.assertRaises(SourceError):
                self.http.get_json("s", self.base + "/json", {"q": "inc"})
            dest = self.root / "clips" / "y.mp4"
            with self.assertRaises(SourceError):
                self.http.download("s", self.base + "/file", dest)
        self.assertFalse(dest.with_suffix(".part").exists())

    def test_https_upgrade(self):
        from http_client import upgrade
        self.assertEqual(upgrade("http://images-assets.nasa.gov/a.mp4"), "https://images-assets.nasa.gov/a.mp4")
        self.assertEqual(upgrade("http://127.0.0.1:8000/a"), "http://127.0.0.1:8000/a")


if __name__ == "__main__":
    unittest.main()
