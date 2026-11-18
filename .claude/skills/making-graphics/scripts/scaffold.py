"""Create a design or a template for editors: from the blank skeletons in scaffold/, or as a copy of another one."""
import json
import re
import shutil
from pathlib import Path

import designs

SKELETON = Path(__file__).resolve().parents[1] / "scaffold"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _check_name(name, kind):
    if not _NAME.match(name):
        raise designs.DesignError(f"{kind} adı '{name}' olamaz: küçük harf, rakam ve tire kullanın (örn. gece-2)")


def _fill(dir, name):
    for p in dir.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".html", ".md"):
            p.write_text(p.read_text(encoding="utf-8").replace("{name}", name), encoding="utf-8")


def new_design(root, name, from_=None):
    _check_name(name, "tasarım")
    dest = Path(root) / "designs" / name
    if dest.exists():
        raise designs.DesignError(f"tasarım '{name}' zaten var: {dest}")
    if from_:
        src = designs.design_dir(root, from_)
        shutil.copytree(src, dest, ignore=lambda d, names: [n for n in names if Path(d) == src and n == "reference"])
        (dest / "design.md").write_text(
            f"# {name} design\n\n'{from_}' tasarımından kopyalandı. Kararları tarih ve gerekçesiyle buraya yazın.\n\n"
            "## Decisions\n\n(empty)\n", encoding="utf-8")
    else:
        shutil.copytree(SKELETON / "design", dest)
        _fill(dest, name)
    return dest


def new_template(root, design, name, from_=None):
    _check_name(name, "şablon")
    designs.design_dir(root, design)
    dest = Path(root) / "templates" / design / name
    if dest.exists():
        raise designs.DesignError(f"şablon '{name}' zaten var: {dest}")
    if from_:
        src = designs.template_dir(root, design, from_)
        shutil.copytree(src, dest)
        meta = json.loads((dest / "template.json").read_text(encoding="utf-8"))
        meta.update(name=name, status="draft", version=1)
        (dest / "template.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        html = dest / "index.html"
        html.write_text(re.sub(r'(data-composition-id=")[^"]*(")', rf"\g<1>{name}\g<2>",
                               html.read_text(encoding="utf-8"), count=1), encoding="utf-8")
    else:
        shutil.copytree(SKELETON / "template", dest)
        _fill(dest, name)
    return dest
