import json, os, tempfile, unittest
import helpers  # noqa: F401
import plan

FPS = 25


def f(name, frames=None, credit=None, code=None):
    return {"file": f"/m/{name}", "code": code or name, "frames": frames, "credit": credit}


def asset(kind, files, track=2, tag="STOK", hold=None, hold_from=None, note=None, code="R1"):
    return {"tag": tag, "kind": kind, "request_hash": "h", "track": track, "files": files,
            "hold": hold, "hold_from": hold_from, "note": note, "code": code}


def fetched(**rows):
    return {"units": "frames", "rows": rows}


def spans(items):
    return [(i["track"], i["start"], i["end"], i["file"], i["src_in"], i["src_out"]) for i in items]


def item(id_, row, start, end, file, track=2, src_in=0, src_out=None, editor=False, deleted=False, uid=None,
         props=None):
    return {"id": id_, "row": row, "track": track, "start": start, "end": end, "file": file,
            "src_in": src_in, "src_out": end - start if src_out is None else src_out, "kind": "stock",
            "code": None, "editor": editor, "deleted": deleted, "uid": uid, "props": props or {}, "marker": None}


def seen_of(i, **change):
    s = {k: i[k] for k in ("uid", "track", "start", "end", "file", "src_in", "src_out", "props")}
    s.update(change)
    return s


class DesiredTest(unittest.TestCase):
    def test_stock_fill_three_candidates_last_trimmed(self):
        rows = {"k": {"id": "R5", "start": 100, "end": 100 + 17 * FPS}}  # 425 frames
        fe = fetched(k=[asset("stock", [f("a.mp4", 150), f("b.mp4", 200), f("c.mp4", 300), f("d.mp4", 90)])])
        items = plan.desired(rows, fe)
        self.assertEqual(spans(items), [(2, 100, 250, "/m/a.mp4", 0, 150),
                                        (2, 250, 450, "/m/b.mp4", 0, 200),
                                        (2, 450, 525, "/m/c.mp4", 0, 75)])
        self.assertEqual([i["id"] for i in items], ["R5#1", "R5#2", "R5#3"])
        self.assertEqual([i["code"] for i in items], ["a.mp4", "b.mp4", "c.mp4"])
        self.assertTrue(all(i["row"] == "k" and i["kind"] == "stock" and not i["editor"] and not i["deleted"]
                            and i["uid"] is None for i in items))
        self.assertEqual(plan.shortfalls(rows, fe), [])

    def test_stock_short_leaves_rest_empty_and_reports(self):
        rows = {"k": {"id": "R5", "start": 0, "end": 425}}
        fe = fetched(k=[asset("stock", [f("a.mp4", 100), f("b.mp4", 125)])])
        self.assertEqual(spans(plan.desired(rows, fe)), [(2, 0, 100, "/m/a.mp4", 0, 100),
                                                         (2, 100, 225, "/m/b.mp4", 0, 125)])
        lines = plan.shortfalls(rows, fe)
        self.assertEqual(len(lines), 1)
        self.assertIn("R5", lines[0])
        self.assertIn("stok yetmedi", lines[0])

    def test_unused_candidates(self):
        rows = {"k": {"id": "R5", "start": 0, "end": 200}}
        fe = fetched(k=[asset("stock", [f("a.mp4", 150), f("b.mp4", 200), f("c.mp4", 300)])])
        items = plan.desired(rows, fe)
        self.assertEqual(plan.unused_candidates(fe["rows"]["k"], items), ["/m/c.mp4"])

    def test_graphic_with_hold(self):
        rows = {"k": {"id": "R12", "start": 1000, "end": 1425}}
        g = asset("graphic", [f("G12-1.mp4", 375, code="G12-1")], tag="GRAFİK", hold="/m/G12-1-hold-262.png",
                  hold_from=262, code="G12")
        items = plan.desired(rows, fetched(k=[g]))
        self.assertEqual(spans(items), [(2, 1000, 1262, "/m/G12-1.mp4", 0, 262),
                                        (2, 1262, 1425, "/m/G12-1-hold-262.png", 0, 163)])
        self.assertEqual([i["code"] for i in items], ["G12-1", "G12-1"])

    def test_graphic_trimmed_to_coverage(self):
        rows = {"k": {"id": "R12", "start": 0, "end": 40}}
        g = asset("graphic", [f("n.mov", 75)], track=3, tag="YAZI")
        self.assertEqual(spans(plan.desired(rows, fetched(k=[g]))), [(3, 0, 40, "/m/n.mov", 0, 40)])

    def test_graphic_shorter_than_coverage_not_stretched(self):
        rows = {"k": {"id": "R12", "start": 0, "end": 100}}
        g = asset("graphic", [f("n.mov", 75)], track=3, tag="YAZI")
        self.assertEqual(spans(plan.desired(rows, fetched(k=[g]))), [(3, 0, 75, "/m/n.mov", 0, 75)])

    def test_kaynak_and_placeholder_still_over_coverage_with_marker(self):
        rows = {"k": {"id": "R7", "start": 50, "end": 150}}
        fe = fetched(k=[asset("kaynak", [f("R7.png", None, credit="https://x")], tag="KAYNAK"),
                        asset("placeholder", [f("R7-2-YAZI.png", code="R7")], track=3, tag="YAZI",
                              note="no template: iki satırlı alıntı kartı", code=None)])
        items = plan.desired(rows, fe, visuals={"k": "Alıntı: 'x'"})
        self.assertEqual(spans(items), [(2, 50, 150, "/m/R7.png", 0, 100),
                                        (3, 50, 150, "/m/R7-2-YAZI.png", 0, 100)])
        self.assertIsNone(items[0]["marker"])
        self.assertEqual(items[1]["marker"], "R7 YAZI: Alıntı: 'x' (no template: iki satırlı alıntı kartı)")
        self.assertEqual(items[1]["kind"], "placeholder")

    def test_placeholder_marker_without_visuals_or_note(self):
        rows = {"k": {"id": "R7", "start": 0, "end": 10}}
        fe = fetched(k=[asset("placeholder", [f("p.png")], tag="ARŞİV")])
        self.assertEqual(plan.desired(rows, fe)[0]["marker"], "R7 ARŞİV: ")

    def test_rows_not_found_or_not_fetched_are_skipped(self):
        rows = {"k": None, "j": {"id": "R2", "start": 0, "end": 10}}
        self.assertEqual(plan.desired(rows, fetched(k=[asset("kaynak", [f("x.png")])])), [])


class ReadbackTest(unittest.TestCase):
    def setUp(self):
        self.a = item("R1#1", "k", 0, 100, "/m/a.mp4", uid="u1", props={"ZoomX": 1.0})
        self.b = item("R1#2", "k", 100, 200, "/m/b.mp4", uid="u2", props={"ZoomX": 1.0})

    def test_unchanged_stays_ours(self):
        out = plan.readback([self.a, self.b], [seen_of(self.a), seen_of(self.b)])
        self.assertEqual(out, [self.a, self.b])

    def test_moved(self):
        out = plan.readback([self.a], [seen_of(self.a, start=10, end=110)])
        self.assertTrue(out[0]["editor"])
        self.assertEqual((out[0]["start"], out[0]["end"]), (10, 110))
        self.assertFalse(out[0]["deleted"])
        self.assertEqual(out[0]["id"], "R1#1")
        self.assertEqual(out[0]["row"], "k")

    def test_trimmed(self):
        out = plan.readback([self.a], [seen_of(self.a, end=80, src_out=80)])
        self.assertTrue(out[0]["editor"])
        self.assertEqual((out[0]["end"], out[0]["src_out"]), (80, 80))

    def test_property_changed(self):
        out = plan.readback([self.a], [seen_of(self.a, props={"ZoomX": 1.4})])
        self.assertTrue(out[0]["editor"])
        self.assertEqual(out[0]["props"], {"ZoomX": 1.4})

    def test_deleted(self):
        out = plan.readback([self.a, self.b], [seen_of(self.b)])
        self.assertEqual(out[0]["id"], "R1#1")
        self.assertTrue(out[0]["editor"] and out[0]["deleted"])
        self.assertIsNone(out[0]["file"])
        self.assertIsNone(out[0]["uid"])
        self.assertFalse(out[1]["editor"])

    def test_added(self):
        e = {"uid": "x9", "track": 2, "start": 300, "end": 350, "file": "/m/mine.mp4", "src_in": 5, "src_out": 55,
             "props": {}}
        old_e = item("E1", None, 500, 600, "/m/old.mp4", editor=True, uid="x1")
        out = plan.readback([self.a, old_e], [seen_of(self.a), seen_of(old_e), e])
        new = out[-1]
        self.assertEqual(new["id"], "E2")
        self.assertIsNone(new["row"])
        self.assertTrue(new["editor"])
        self.assertFalse(new["deleted"])
        self.assertEqual(spans([new]), [(2, 300, 350, "/m/mine.mp4", 5, 55)])
        self.assertEqual(new["uid"], "x9")

    def test_deleted_editor_entry_stays_deleted(self):
        d = item("R1#1", "k", 0, 100, None, editor=True, deleted=True)
        self.assertEqual(plan.readback([d], []), [d])

    def test_editor_added_then_deleted_is_dropped(self):
        old_e = item("E1", None, 500, 600, "/m/old.mp4", editor=True, uid="x1")
        self.assertEqual(plan.readback([old_e], []), [])


class ActionsTest(unittest.TestCase):
    ROWS = {"k": {"id": "R1", "start": 0, "end": 200}, "j": {"id": "R2", "start": 200, "end": 300}}

    def fe(self, k_files):
        return fetched(k=[asset("stock", k_files)], j=[asset("kaynak", [f("R2.png")])])

    def placed(self, items):
        return [dict(i, uid=f"u{n}", props={}) for n, i in enumerate(items)]

    def test_unchanged_row_kept(self):
        desired = plan.desired(self.ROWS, self.fe([f("a.mp4", 120), f("b.mp4", 120)]))
        current = self.placed(desired)
        keep, remove, add = plan.actions(current, desired)
        self.assertEqual(keep, current)
        self.assertEqual((remove, add), ([], []))

    def test_changed_fetch_removes_and_adds(self):
        current = self.placed(plan.desired(self.ROWS, self.fe([f("a.mp4", 120), f("b.mp4", 120)])))
        desired = plan.desired(self.ROWS, self.fe([f("a.mp4", 120), f("c.mp4", 120)]))
        keep, remove, add = plan.actions(current, desired)
        self.assertEqual(spans(keep), spans(current[:1]) + spans(current[2:]))
        self.assertEqual(spans(remove), [(2, 120, 200, "/m/b.mp4", 0, 80)])
        self.assertEqual(spans(add), [(2, 120, 200, "/m/c.mp4", 0, 80)])
        self.assertEqual(keep[0]["uid"], "u0")

    def test_row_with_editor_item_is_left_whole(self):
        current = self.placed(plan.desired(self.ROWS, self.fe([f("a.mp4", 120), f("b.mp4", 120)])))
        current[0] = dict(current[0], editor=True, start=5, end=125)
        desired = plan.desired(self.ROWS, self.fe([f("x.mp4", 120), f("y.mp4", 120)]))
        keep, remove, add = plan.actions(current, desired)
        self.assertEqual([i["row"] for i in remove + add], [])
        self.assertEqual(keep, current)

    def test_deleted_editor_entry_never_readded(self):
        desired = plan.desired(self.ROWS, self.fe([f("a.mp4", 300)]))
        current = self.placed(desired)
        current[0] = dict(current[0], editor=True, deleted=True, file=None, uid=None)
        keep, remove, add = plan.actions(current, desired)
        self.assertEqual((remove, add), ([], []))
        self.assertEqual(keep, current)

    def test_editor_added_entries_kept(self):
        desired = plan.desired(self.ROWS, self.fe([f("a.mp4", 300)]))
        e = item("E1", None, 0, 50, "/m/mine.mp4", track=3, editor=True, uid="x")
        keep, remove, add = plan.actions(self.placed(desired) + [e], desired)
        self.assertIn(e, keep)
        self.assertEqual((remove, add), ([], []))

    def test_editor_entry_of_vanished_row_kept_and_reported(self):
        gone_ours = item("R9#1", "gone", 400, 500, "/m/g.mp4", uid="g1")
        gone_ed = item("R9#2", "gone", 500, 600, "/m/h.mp4", uid="g2", editor=True)
        other_ours = item("R8#1", "gone2", 600, 700, "/m/i.mp4", uid="g3")
        desired = plan.desired(self.ROWS, self.fe([f("a.mp4", 300)]))
        current = self.placed(desired) + [gone_ours, gone_ed, other_ours]
        keep, remove, add = plan.actions(current, desired)
        self.assertIn(gone_ed, keep)
        self.assertIn(gone_ours, keep)  # same row as an editor entry: left whole
        self.assertEqual(remove, [other_ours])
        self.assertEqual(add, [])
        self.assertEqual(plan.lost(keep, self.ROWS), ["R9: satırı kayboldu (1 düzenleyici öğesi)"])

    def test_new_row_added(self):
        desired = plan.desired(self.ROWS, self.fe([f("a.mp4", 300)]))
        keep, remove, add = plan.actions([], desired)
        self.assertEqual((keep, remove), ([], []))
        self.assertEqual(add, desired)


class PlanFileTest(unittest.TestCase):
    def test_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "broll", "plan.json")
            self.assertEqual(plan.load(p), {"units": "frames", "chapters": {}})
            data = {"units": "frames", "chapters": {"2": {"timeline": "T ch2 B-roll",
                                                          "items": [item("R1#1", "k", 0, 10, "/m/ı.mp4")]}}}
            plan.save(p, data)
            self.assertEqual(plan.load(p), data)
            with open(p, encoding="utf-8") as fh:
                self.assertIn("ı.mp4", fh.read())


if __name__ == "__main__":
    unittest.main()
