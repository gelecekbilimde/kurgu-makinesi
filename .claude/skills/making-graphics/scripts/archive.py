"""The graphics archive: assets/graphics/<template>/<id>/{vars.json, render.<ext>, poster.png}.

vars.json is the source of truth; index.json is derived from them (--reindex). The id is a content hash of
everything that decides the pixels, so a repeated request reuses its render and any design change re-renders.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path


def render_id(template, template_version, design, design_hash, variant, vertical, frames, fps, resolution, output,
              values):
    parts = dict(template=template, template_version=template_version, design=design, design_hash=design_hash,
                 variant=variant, vertical=vertical, frames=frames, fps=fps, resolution=resolution, output=output,
                 values=values)
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class Archive:
    def __init__(self, root):
        self.root = Path(root)

    def _entry(self, template, id):
        return self.root / template / id

    def lookup(self, template, id):
        d = self._entry(template, id)
        if not (d / "vars.json").is_file():
            return None
        renders = sorted(d.glob("render.*"))
        return renders[0] if renders else None

    def store(self, template, id, vars, file, poster):
        final = self._entry(template, id)
        tmp = final.with_name(id + ".tmp")
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        shutil.copy2(file, tmp / ("render" + Path(file).suffix))
        shutil.copy2(poster, tmp / "poster.png")
        (tmp / "vars.json").write_text(json.dumps(vars, ensure_ascii=False, indent=1), encoding="utf-8")
        if final.exists():
            shutil.rmtree(final)
        os.replace(tmp, final)
        self.write_index()
        return self.lookup(template, id)

    def entries(self):
        out = []
        for vars_path in sorted(self.root.glob("*/*/vars.json")):
            d = vars_path.parent
            if d.name.endswith(".tmp"):
                continue
            render = self.lookup(d.parent.name, d.name)
            entry = json.loads(vars_path.read_text(encoding="utf-8"))
            entry.update(id=d.name, file=render.relative_to(self.root).as_posix() if render else None,
                         poster=(d / "poster.png").relative_to(self.root).as_posix())
            out.append(entry)
        return out

    def write_index(self):
        entries = self.entries()
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / "index.json.tmp"
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.root / "index.json")
        return entries
