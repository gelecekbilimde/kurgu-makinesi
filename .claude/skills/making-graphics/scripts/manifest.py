"""template.json: what makes a HyperFrames composition a renderable template, and field validation.

Validation is generic and driven by the manifest. Every problem is collected and reported together, in Turkish, so
the editor fixes the request once instead of one error at a time.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FIELD_TYPES = ("text", "highlight", "number", "enum", "list", "source")
OUTPUTS = ("overlay", "fullscreen", "still")
REQUIRED_KEYS = ("name", "description", "version", "output", "canvas", "frames", "fields")
BASE_FPS = 25
_NUMBER = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(?:\^\s*(-?\d+))?\s*$")


class ManifestError(Exception):
    """template.json is missing or malformed (a template author's error)."""


class FieldError(Exception):
    """The request's fields don't fit the template. .problems holds one Turkish line per problem."""

    def __init__(self, problems):
        super().__init__(problems)
        self.problems = problems


@dataclass
class Field:
    name: str
    type: str
    required: bool = False
    max_len: int | None = None
    help: str = ""
    of: str | None = None
    values: list = field(default_factory=list)
    item: str = "text"
    numeric: bool = False
    min_items: int | None = None
    max_items: int | None = None
    one_of_labels: str | None = None


@dataclass
class Template:
    name: str
    dir: Path
    description: str
    version: int
    status: str
    output: str
    output_by: dict | None
    canvas: object
    vertical: bool
    frames: dict
    fields: list

    @property
    def fixed_canvas(self):
        return isinstance(self.canvas, dict)

    def field(self, name):
        return next((f for f in self.fields if f.name == name), None)


def load(dir):
    dir = Path(dir)
    path = dir / "template.json"
    if not path.is_file():
        raise ManifestError(f"{dir}: template.json yok")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ManifestError(f"{path}: geçersiz JSON ({err})") from None
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ManifestError(f"{path}: eksik anahtar: {', '.join(missing)}")
    if data["output"] not in OUTPUTS:
        raise ManifestError(f"{path}: output '{data['output']}' olamaz ({', '.join(OUTPUTS)})")
    canvas = data["canvas"]
    if canvas != "frame" and not (isinstance(canvas, dict) and {"width", "height"} <= set(canvas)):
        raise ManifestError(f"{path}: canvas \"frame\" ya da {{\"width\", \"height\"}} olmalı")
    frames = data["frames"]
    if not (isinstance(frames, dict) and {"default", "min", "max"} <= set(frames)
            and frames["min"] <= frames["default"] <= frames["max"]):
        raise ManifestError(f"{path}: frames {{default, min, max}} olmalı ve min <= default <= max")
    fields = []
    for raw in data["fields"]:
        if raw.get("type") not in FIELD_TYPES:
            raise ManifestError(f"{path}: alan '{raw.get('name')}' için bilinmeyen tür '{raw.get('type')}' "
                                f"({', '.join(FIELD_TYPES)})")
        known = set(Field.__dataclass_fields__)
        extra = set(raw) - known
        if extra:
            raise ManifestError(f"{path}: alan '{raw.get('name')}' için bilinmeyen anahtar: {', '.join(sorted(extra))}")
        fields.append(Field(**raw))
    names = {f.name for f in fields}
    for f in fields:
        if f.type == "highlight" and f.of not in names:
            raise ManifestError(f"{path}: highlight alanı '{f.name}' için 'of' bir alan adı olmalı")
        if f.one_of_labels and f.one_of_labels not in names:
            raise ManifestError(f"{path}: '{f.name}' için one_of_labels bir alan adı olmalı")
    out_by = data.get("output_by")
    if out_by and (out_by.get("field") not in names or not isinstance(out_by.get("map"), dict)
                   or not set(out_by["map"].values()) <= set(OUTPUTS)):
        raise ManifestError(f"{path}: output_by {{field, map}} geçersiz")
    return Template(name=data["name"], dir=dir, description=data["description"], version=int(data["version"]),
                    status=data.get("status", "draft"), output=data["output"], output_by=out_by, canvas=canvas,
                    vertical=bool(data.get("vertical", False)), frames=frames, fields=fields)


def _to_float(s):
    return float(s.replace(",", "."))


def _check_len(f, text, label, problems):
    if f.max_len is not None and len(text) > f.max_len:
        problems.append(f"{label}: en fazla {f.max_len} karakter olabilir ({len(text)} verildi)")


def _list_value(f, raw, problems):
    items = [raw] if isinstance(raw, str) else list(raw or [])
    out = []
    for i, item in enumerate(items, 1):
        label = f"{f.name} #{i}"
        item = str(item).strip()
        if f.item == "pair":
            if "=" not in item:
                problems.append(f"{label}: 'etiket=değer' biçiminde olmalı ('{item}' verildi)")
                continue
            lab, val = (x.strip() for x in item.split("=", 1))
            _check_len(f, lab, label, problems)
            if f.numeric:
                try:
                    val = _to_float(val)
                except ValueError:
                    problems.append(f"{label}: değer sayı olmalı ('{item}' verildi)")
                    continue
            out.append({"label": lab, "value": val})
        else:
            _check_len(f, item, label, problems)
            out.append(item)
    if items and f.min_items is not None and len(items) < f.min_items:
        problems.append(f"{f.name}: en az {f.min_items} öğe gerekli ({len(items)} verildi)")
    if f.max_items is not None and len(items) > f.max_items:
        problems.append(f"{f.name}: en fazla {f.max_items} öğe olabilir ({len(items)} verildi)")
    return out


def validate(t, raw):
    problems = []
    names = [f.name for f in t.fields]
    for k in raw:
        if k not in names:
            problems.append(f"bilinmeyen alan '{k}'; bu şablonun alanları: {', '.join(names)}")
    values = {}
    for f in t.fields:
        given = raw.get(f.name)
        empty = given is None or (isinstance(given, str) and not given.strip()) or given == []
        if empty:
            if f.required:
                problems.append(f"{f.name}: gerekli alan boş")
            values[f.name] = [] if f.type == "list" else (None if f.type == "number" else "")
            continue
        if f.type == "list":
            values[f.name] = _list_value(f, given, problems)
            continue
        text = str(given).strip()
        if f.type == "number":
            m = _NUMBER.match(text)
            if not m:
                problems.append(f"{f.name}: sayı olmalı, örneğin 3,7 ya da 10^67 ('{text}' verildi)")
                continue
            values[f.name] = {"base": m.group(1), "exp": m.group(2), "text": text}
            continue
        if f.type == "enum" and text not in f.values:
            problems.append(f"{f.name}: '{text}' olamaz; seçenekler: {', '.join(f.values)}")
            continue
        _check_len(f, text, f.name, problems)
        values[f.name] = text
    for f in t.fields:
        v = values.get(f.name)
        if f.type == "highlight" and v and v not in (values.get(f.of) or ""):
            problems.append(f"{f.name}: '{v}' metni {f.of} alanında geçmiyor")
        if f.one_of_labels and v:
            labels = [x["label"] if isinstance(x, dict) else x for x in values.get(f.one_of_labels) or []]
            if v not in labels:
                problems.append(f"{f.name}: '{v}' {f.one_of_labels} etiketlerinden biri olmalı ({', '.join(labels)})")
    if problems:
        raise FieldError(problems)
    return values


def output_for(t, values):
    if t.output_by:
        return t.output_by["map"].get(values.get(t.output_by["field"]), t.output)
    return t.output


def frame_limits(t, fps):
    scale = fps / BASE_FPS
    return tuple(round(t.frames[k] * scale) for k in ("default", "min", "max"))
