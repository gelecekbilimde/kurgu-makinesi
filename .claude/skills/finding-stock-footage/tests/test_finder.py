import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from helpers import cand
from fakes import FakeHttp
from cache import Cache  # noqa: E402
from finder import Request, find  # noqa: E402
from model import SourceError  # noqa: E402

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


class FakeSource:
    def __init__(self, slug, items, priority=1, fail=None):
        self.slug, self.items, self.priority, self.fail = slug, items, priority, fail
        self.pulled = 0

    def search(self, query, orientation):
        for c in self.items:
            self.pulled += 1
            yield c
        if self.fail:
            raise SourceError(self.slug, self.fail)


def A(i, **kw):
    return cand(source="a", id=f"a{i}", **kw)


def B(i, **kw):
    return cand(source="b", id=f"b{i}", **kw)


class Finder(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Cache(Path(tmp.name) / "stock")
        self.http = FakeHttp()

    def ids(self, picks):
        return [p.entry["id"] for p in picks]

    def run_find(self, sources, **kw):
        req = Request(query=kw.pop("query", "rocket"), code=kw.pop("code", "R1"), **kw)
        return find(req, sources, self.cache, self.http, NOW)

    def test_round_robin(self):
        picks, notes = self.run_find([FakeSource("a", [A(1), A(2), A(3)]), FakeSource("b", [B(1), B(2)])], count=4)
        self.assertEqual(self.ids(picks), ["a1", "b1", "a2", "b2"])
        self.assertEqual(notes, [])

    def test_round_robin_skips_filtered_within_a_turn(self):
        a = FakeSource("a", [A(1, duration_s=200), A(2), A(3)])
        picks, _ = self.run_find([a, FakeSource("b", [B(1), B(2)])], count=3)
        self.assertEqual(self.ids(picks), ["a2", "b1", "a3"])

    def test_vertical_first_then_fill(self):
        a = FakeSource("a", [A(1), A(2, width=1080, height=1920), A(3)])
        picks, _ = self.run_find([a], orientation="vertical", count=3)
        self.assertEqual(self.ids(picks), ["a2", "a1", "a3"])

    def test_filters(self):
        a = FakeSource("a", [A(1, duration_s=3), A(2, duration_s=200), A(3, width=1000, height=562), A(4)])
        picks, _ = self.run_find([a], count=3)
        self.assertEqual(self.ids(picks), ["a4"])

    def test_local_match_avoids_api(self):
        for i in range(3):
            self.cache.clip_path("a", f"a{i}").parent.mkdir(parents=True, exist_ok=True)
            self.cache.clip_path("a", f"a{i}").write_bytes(b"v")
            self.cache.write_sidecar(A(i, keywords=["rocket", "launch"]), "rocket launch", NOW)
        self.cache.write_index()
        src = FakeSource("b", [B(1)])
        picks, _ = self.run_find([src], query="rocket launch", count=3)
        self.assertEqual(src.pulled, 0)
        self.assertEqual(len(picks), 3)
        self.assertTrue(all(p.from_cache for p in picks))
        self.assertEqual(self.http.downloads, [])

    def test_fresh_skips_local_match(self):
        self.cache.clip_path("a", "a0").parent.mkdir(parents=True, exist_ok=True)
        self.cache.clip_path("a", "a0").write_bytes(b"v")
        self.cache.write_sidecar(A(0), "rocket", NOW)
        self.cache.write_index()
        src = FakeSource("b", [B(1)])
        picks, _ = self.run_find([src], count=1, fresh=True)
        self.assertEqual(src.pulled, 1)
        self.assertEqual(self.ids(picks), ["b1"])

    def test_local_picks_rank_before_api(self):
        self.cache.clip_path("a", "a0").parent.mkdir(parents=True, exist_ok=True)
        self.cache.clip_path("a", "a0").write_bytes(b"v")
        self.cache.write_sidecar(A(0), "rocket", NOW)
        self.cache.write_index()
        picks, _ = self.run_find([FakeSource("b", [B(1), B(2)])], count=2)
        self.assertEqual(self.ids(picks), ["a0", "b1"])

    def test_cached_clip_not_redownloaded(self):
        self.cache.clip_path("a", "a1").parent.mkdir(parents=True, exist_ok=True)
        self.cache.clip_path("a", "a1").write_bytes(b"v")
        self.cache.write_sidecar(A(1), "something else", NOW)
        picks, _ = self.run_find([FakeSource("a", [A(1)])], query="moon", count=1)
        self.assertEqual(self.http.downloads, [])
        self.assertTrue(picks[0].from_cache)

    def test_exclude(self):
        picks, _ = self.run_find([FakeSource("a", [A(1), A(2)])], count=2, exclude={("a", "a1")})
        self.assertEqual(self.ids(picks), ["a2"])

    def test_source_error_noted(self):
        picks, notes = self.run_find([FakeSource("a", [], fail="istek sınırı aşıldı (429)"),
                                      FakeSource("b", [B(1)])], count=1)
        self.assertEqual(self.ids(picks), ["b1"])
        self.assertIn("a: istek sınırı aşıldı (429)", notes)

    def test_failed_download_replaced(self):
        self.http.fail_downloads = {A(1).download_url}
        picks, notes = self.run_find([FakeSource("a", [A(1), A(2), A(3)])], count=2)
        self.assertEqual(self.ids(picks), ["a2", "a3"])
        self.assertTrue(any(n.startswith("a: ") for n in notes))
        self.assertFalse(self.cache.has_clip("a", "a1"))

    def test_short_note(self):
        picks, notes = self.run_find([FakeSource("a", [A(1)])], count=3)
        self.assertEqual(len(picks), 1)
        self.assertIn("R1: 1/3 aday bulundu", notes)

    def test_inspects_at_most_20_per_source(self):
        a = FakeSource("a", [A(i, duration_s=1) for i in range(50)])
        self.run_find([a], count=3)
        self.assertLessEqual(a.pulled, 20)

    def test_stops_early_when_enough(self):
        a = FakeSource("a", [A(i) for i in range(20)])
        self.run_find([a], count=3)
        self.assertLess(a.pulled, 20)

    def test_sidecar_and_index_written(self):
        picks, _ = self.run_find([FakeSource("a", [A(1)])], query="rocket launch", count=1)
        entries = self.cache.read_index()
        self.assertEqual([e["id"] for e in entries], ["a1"])
        self.assertIn("rocket launch", entries[0]["keywords"])
        self.assertEqual(picks[0].path, self.cache.clip_path("a", "a1"))
        self.assertTrue(picks[0].path.is_file())


if __name__ == "__main__":
    unittest.main()
