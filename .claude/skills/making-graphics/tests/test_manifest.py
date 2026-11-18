import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
import manifest

DEMO = helpers.FIXTURES / "templates" / "demo"


def load():
    return manifest.load(DEMO)


def errors(raw):
    with unittest.TestCase().assertRaises(manifest.FieldError) as cm:
        manifest.validate(load(), raw)
    return cm.exception.problems


class Load(unittest.TestCase):
    def test_load_reads_fields(self):
        t = load()
        self.assertEqual(t.name, "demo")
        self.assertEqual(t.dir, DEMO)
        self.assertEqual([f.name for f in t.fields][:3], ["value", "explanation", "highlight"])
        expl = t.fields[1]
        self.assertEqual((expl.type, expl.max_len, expl.required, expl.help), ("text", 40, False, "kısa açıklama"))
        self.assertEqual(t.frames, {"default": 150, "min": 75, "max": 375})

    def test_bad_manifest_names_the_key(self):
        with tempfile.TemporaryDirectory() as d:
            data = json.loads((DEMO / "template.json").read_text())
            del data["output"]
            (Path(d) / "template.json").write_text(json.dumps(data))
            with self.assertRaises(manifest.ManifestError) as cm:
                manifest.load(Path(d))
            self.assertIn("output", str(cm.exception))

    def test_unknown_field_type_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            data = json.loads((DEMO / "template.json").read_text())
            data["fields"][0]["type"] = "colour"
            (Path(d) / "template.json").write_text(json.dumps(data))
            with self.assertRaises(manifest.ManifestError) as cm:
                manifest.load(Path(d))
            self.assertIn("colour", str(cm.exception))

    def test_missing_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(manifest.ManifestError) as cm:
                manifest.load(Path(d))
            self.assertIn("template.json", str(cm.exception))


class Validate(unittest.TestCase):
    def test_required_missing(self):
        p = errors({})
        self.assertEqual(len(p), 1)
        self.assertIn("value", p[0])
        self.assertIn("gerekli", p[0])

    def test_text_over_max_len(self):
        p = errors({"value": "1", "explanation": "x" * 41})
        self.assertIn("40", p[0])

    def test_text_stripped(self):
        v = manifest.validate(load(), {"value": "1", "explanation": "  merhaba  "})
        self.assertEqual(v["explanation"], "merhaba")

    def test_highlight_must_be_substring(self):
        v = manifest.validate(load(), {"value": "1", "explanation": "bu çok uzun bir süre", "highlight": "çok uzun"})
        self.assertEqual(v["highlight"], "çok uzun")
        p = errors({"value": "1", "explanation": "bu çok uzun bir süre", "highlight": "kısa"})
        self.assertIn("highlight", p[0])
        self.assertIn("explanation", p[0])

    def test_number_parses_exponent(self):
        v = manifest.validate(load(), {"value": "10^67"})
        self.assertEqual(v["value"], {"base": "10", "exp": "67", "text": "10^67"})
        v = manifest.validate(load(), {"value": "3,7"})
        self.assertEqual(v["value"], {"base": "3,7", "exp": None, "text": "3,7"})
        v = manifest.validate(load(), {"value": "-1.5^-3"})
        self.assertEqual(v["value"]["exp"], "-3")
        self.assertIn("value", errors({"value": "abc"})[0])

    def test_number_accepts_turkish_thousands(self):
        v = manifest.validate(load(), {"value": "-1.234.567,89^-12"})
        self.assertEqual(v["value"], {"base": "-1.234.567,89", "exp": "-12", "text": "-1.234.567,89^-12"})
        self.assertEqual(manifest.validate(load(), {"value": "384.400"})["value"]["base"], "384.400")
        self.assertIn("value", errors({"value": "1.23.4"})[0])

    def test_enum_rejects_unknown(self):
        p = errors({"value": "1", "state": "flying"})
        self.assertIn("static", p[0])
        self.assertIn("moving", p[0])

    def test_list_pairs_numeric(self):
        v = manifest.validate(load(), {"value": "1", "bars": ["Mars=3,7", "Dünya=9.8"]})
        self.assertEqual(v["bars"], [{"label": "Mars", "value": 3.7}, {"label": "Dünya", "value": 9.8}])
        self.assertIn("Mars=x", errors({"value": "1", "bars": ["Mars=x", "Dünya=9.8"]})[0])
        self.assertIn("2", errors({"value": "1", "bars": ["Mars=1"]})[0])
        self.assertIn("8", errors({"value": "1", "bars": [f"a{i}=1" for i in range(9)]})[0])
        self.assertTrue(errors({"value": "1", "bars": ["Mars 3", "Dünya=1"]}))

    def test_list_text_items(self):
        v = manifest.validate(load(), {"value": "1", "steps": ["bir", "iki"]})
        self.assertEqual(v["steps"], ["bir", "iki"])
        self.assertIn("10", errors({"value": "1", "steps": ["x" * 11]})[0])

    def test_single_string_for_list_becomes_one_item(self):
        v = manifest.validate(load(), {"value": "1", "steps": "bir"})
        self.assertEqual(v["steps"], ["bir"])

    def test_unknown_field_rejected(self):
        p = errors({"value": "1", "colour": "red"})
        self.assertIn("colour", p[0])
        self.assertIn("explanation", p[0])

    def test_all_errors_reported_together(self):
        self.assertEqual(len(errors({"value": "abc", "state": "x"})), 2)

    def test_optional_absent_fields_are_empty(self):
        v = manifest.validate(load(), {"value": "1"})
        self.assertEqual(v["explanation"], "")
        self.assertEqual(v["bars"], [])
        self.assertEqual(v["source"], "")

    def test_one_of_labels(self):
        with tempfile.TemporaryDirectory() as d:
            data = json.loads((DEMO / "template.json").read_text())
            data["fields"].append({"name": "hand_bar", "type": "text", "one_of_labels": "bars"})
            (Path(d) / "template.json").write_text(json.dumps(data))
            t = manifest.load(Path(d))
            ok = manifest.validate(t, {"value": "1", "bars": ["Mars=1", "Dünya=2"], "hand_bar": "Mars"})
            self.assertEqual(ok["hand_bar"], "Mars")
            with self.assertRaises(manifest.FieldError) as cm:
                manifest.validate(t, {"value": "1", "bars": ["Mars=1", "Dünya=2"], "hand_bar": "Venüs"})
            self.assertIn("Dünya", cm.exception.problems[0])

    def test_output_by_maps_enum(self):
        t = load()
        self.assertEqual(manifest.output_for(t, {"state": "static"}), "still")
        self.assertEqual(manifest.output_for(t, {"state": "moving"}), "fullscreen")
        self.assertEqual(manifest.output_for(t, {}), "fullscreen")

    def test_frame_limits_scale_with_fps(self):
        t = load()
        self.assertEqual(manifest.frame_limits(t, 25), (150, 75, 375))
        self.assertEqual(manifest.frame_limits(t, 50), (300, 150, 750))
        self.assertEqual(manifest.frame_limits(t, 30), (180, 90, 450))


if __name__ == "__main__":
    unittest.main()
