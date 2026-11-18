"""Editor-owned designs and templates under graphics/: the active design, variants, and the design hash.

graphics/config.json            {"design": "<name>"}
graphics/designs/<d>/           tokens.css, variants/<v>.css, fonts/, assets/, design.json, design.md, reference/
graphics/templates/<d>/<t>/     index.html, template.json, samples.json
"""
import hashlib
import json
from pathlib import Path

import manifest

DOC_PARTS = ("design.md", "reference")


class DesignError(Exception):
    """A design, variant or template that doesn't exist; the message lists what does."""


class Config:
    def __init__(self, root):
        path = Path(root) / "config.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        self.design = data.get("design", "starter")


def _names(dir, want_dir=True):
    if not dir.is_dir():
        return []
    return sorted(p.name for p in dir.iterdir() if p.is_dir() == want_dir and not p.name.startswith((".", "_")))


def design_dir(root, name):
    d = Path(root) / "designs" / name
    if not (d / "tokens.css").is_file():
        known = _names(Path(root) / "designs")
        raise DesignError(f"tasarım '{name}' yok; mevcut tasarımlar: {', '.join(known) or '(hiç yok)'}")
    return d


def variants(dir):
    vdir = Path(dir) / "variants"
    return sorted(p.stem for p in vdir.glob("*.css")) if vdir.is_dir() else []


def default_variant(dir):
    path = Path(dir) / "design.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("default_variant")


def check_variant(dir, variant):
    if variant is not None and variant not in variants(dir):
        raise DesignError(f"varyant '{variant}' yok; bu tasarımın varyantları: {', '.join(variants(dir)) or '(yok)'}")


def design_files(dir):
    dir = Path(dir)
    return sorted(p for p in dir.rglob("*") if p.is_file() and p.relative_to(dir).parts[0] not in DOC_PARTS)


def design_hash(dir):
    dir = Path(dir)
    h = hashlib.sha256()
    for p in design_files(dir):
        h.update(p.relative_to(dir).as_posix().encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def template_dir(root, design, name):
    d = Path(root) / "templates" / design / name
    if not (d / "template.json").is_file():
        known = [t.name for t in templates(root, design)]
        raise DesignError(f"şablon '{name}' yok ({design} tasarımında); mevcut şablonlar: "
                          f"{', '.join(known) or '(hiç yok)'}")
    return d


def templates(root, design):
    base = Path(root) / "templates" / design
    return [manifest.load(base / n) for n in _names(base) if (base / n / "template.json").is_file()]
