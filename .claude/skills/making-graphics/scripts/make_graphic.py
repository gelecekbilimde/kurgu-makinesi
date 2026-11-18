"""Render a graphic from a template of the active design.

  python3 make_graphic.py <template> --set alan=değer [--set ...] [--fields-file F] [--variant V] [--vertical]
                          [--frames N] [--fps 25] [--resolution 4k|1080p] [--out DIR] [--code C] [--design D] [--fresh]
  python3 make_graphic.py --batch rows.json --out DIR   # [{"template", "code"?, "fields": {}, "variant"?, "vertical"?,
                                                        #   "frames"?}, ...]
  python3 make_graphic.py --list [--json]               # templates of the active design and their fields
  python3 make_graphic.py --reindex                     # rebuild assets/graphics/index.json from the archive
  python3 make_graphic.py --samples <template> [--out DIR]  # render the template's samples.json + contact.png

Repeat --set for a list field (--set bars="Mars=3,7" --set bars="Dünya=9,8"). Lengths are frames.
Exit codes: 0 rendered, 2 the request doesn't fit the template, 1 any other failure.
"""
import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import deliver  # noqa: E402
import designs  # noqa: E402
import hf  # noqa: E402
import manifest  # noqa: E402
import render  # noqa: E402
import review  # noqa: E402
import stage  # noqa: E402
from archive import Archive, render_id  # noqa: E402

DEFAULT_ROOT = hf.REPO_ROOT / "graphics"
DEFAULT_ARCHIVE = hf.REPO_ROOT / "assets" / "graphics"
POSTER_AT = 0.7


class UsageError(Exception):
    pass


class RequestError(Exception):
    """The request doesn't fit (bad fields, unknown template/variant, length out of range); .problems lists why."""

    def __init__(self, problems):
        super().__init__(problems)
        self.problems = problems


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def parse(argv):
    p = Parser(prog="make_graphic.py", description=__doc__.split("\n\n")[0])
    p.add_argument("template", nargs="?")
    p.add_argument("--set", action="append", default=[], metavar="ALAN=DEĞER")
    p.add_argument("--fields-file")
    p.add_argument("--variant")
    p.add_argument("--vertical", action="store_true")
    p.add_argument("--frames", type=int)
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--resolution", choices=["4k", "1080p"], default="4k")
    p.add_argument("--out")
    p.add_argument("--code")
    p.add_argument("--design")
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--batch")
    p.add_argument("--list", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--reindex", action="store_true")
    p.add_argument("--samples", metavar="ŞABLON")
    p.add_argument("--root", default=str(DEFAULT_ROOT))
    p.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    a = p.parse_args(argv)
    modes = [a.template is not None, a.batch is not None, a.list, a.reindex, a.samples is not None]
    if sum(modes) != 1:
        raise UsageError("bir şablon adı, --batch, --list, --reindex veya --samples verin (yalnızca biri)")
    if a.batch and not a.out:
        raise UsageError("--batch için --out gerekli")
    return a


def fields_from_args(sets, fields_file):
    fields = {}
    if fields_file:
        with open(fields_file, encoding="utf-8") as f:
            fields.update(json.load(f))
    given = {}
    for item in sets:
        if "=" not in item:
            raise RequestError([f"--set '{item}': 'alan=değer' biçiminde olmalı"])
        k, v = item.split("=", 1)
        given.setdefault(k.strip(), []).append(v)
    for k, vs in given.items():
        fields[k] = vs[0] if len(vs) == 1 else vs
    return fields


@dataclass
class Context:
    root: Path
    archive: Archive
    run: object
    out: Path | None
    results: dict | None = None
    design: str | None = None
    fps: int = 25
    resolution: str = "4k"
    fresh: bool = False
    home: Path = field(default_factory=Path.home)


def _first_text(t, values):
    return next((values[f.name] for f in t.fields if f.type == "text" and values.get(f.name)), "")


def resolve(row, ctx):
    """Validate one request row; returns everything a render needs, or raises RequestError."""
    try:
        design = row.get("design") or ctx.design or designs.Config(ctx.root).design
        ddir = designs.design_dir(ctx.root, design)
        t = manifest.load(designs.template_dir(ctx.root, design, row["template"]))
        values = manifest.validate(t, row.get("fields") or {})
        variant = row.get("variant") or designs.default_variant(ddir)
        designs.check_variant(ddir, variant)
    except (designs.DesignError, manifest.ManifestError) as err:
        raise RequestError([str(err)]) from None
    except manifest.FieldError as err:
        raise RequestError(err.problems) from None
    output = manifest.output_for(t, values)
    fps = int(row.get("fps") or ctx.fps)
    default, lo, hi = manifest.frame_limits(t, fps)
    frames = int(row.get("frames") or default)
    if output == "still":
        frames = 1
    elif not lo <= frames <= hi:
        raise RequestError([f"uzunluk {frames} kare olamaz; {fps} fps için {lo} ile {hi} kare arası "
                            f"(varsayılan {default})"])
    vertical = bool(row.get("vertical"))
    if t.fixed_canvas:
        vertical, resolution = False, "native"
    else:
        resolution = row.get("resolution") or ctx.resolution
        if vertical and not t.vertical:
            raise RequestError([f"'{t.name}' şablonunun dikey (9:16) sürümü yok"])
    return dict(t=t, design=design, ddir=ddir, values=values, variant=variant, output=output, fps=fps,
                frames=frames, vertical=vertical, resolution=resolution)


def render_row(row, ctx):
    """Render (or reuse from the archive) one request row and deliver it into ctx.out; returns its results entry."""
    r = resolve(row, ctx)
    t = r["t"]
    dhash = designs.design_hash(r["ddir"])
    id = render_id(template=t.name, template_version=t.version, design=r["design"], design_hash=dhash,
                   variant=r["variant"], vertical=r["vertical"], frames=r["frames"], fps=r["fps"],
                   resolution=r["resolution"], output=r["output"], values=r["values"])
    sources = [r["values"][f.name] for f in t.fields if f.type == "source" and r["values"].get(f.name)]
    entry = dict(template=t.name, version=t.version, design=r["design"], variant=r["variant"],
                 vertical=r["vertical"], frames=r["frames"], fps=r["fps"], resolution=r["resolution"],
                 output=r["output"], values=r["values"], sources=sources, archive_id=id)
    existing = None if (ctx.fresh or row.get("fresh")) else ctx.archive.lookup(t.name, id)
    if existing:
        return deliver.add(ctx.out, ctx.results, row.get("code") or t.name, {**entry, "from_archive": True},
                           existing)
    with tempfile.TemporaryDirectory(prefix="grafik-") as tmp:
        tmp = Path(tmp)
        staged = stage.stage(t, r["ddir"], r["variant"], r["values"], r["vertical"], r["frames"], r["fps"],
                             tmp / "project")
        out_file = render.render(staged, r["output"], r["resolution"], t.fixed_canvas, r["vertical"], r["fps"],
                                 tmp / ("render" + render.EXT[r["output"]]), run=ctx.run)
        if r["output"] == "still":
            poster = out_file
        else:
            poster = render.poster(out_file, round(r["frames"] * POSTER_AT), tmp / "poster.png", run=ctx.run)
        vars = dict(entry, engine=f"hyperframes {_engine_version()}", design_hash=dhash,
                    created=datetime.now().astimezone().isoformat())
        vars.pop("archive_id")
        archived = ctx.archive.store(t.name, id, vars, out_file, poster)
    return deliver.add(ctx.out, ctx.results, row.get("code") or t.name, {**entry, "from_archive": False}, archived)


def _engine_version():
    try:
        pkg = hf.SKILL_DIR / "node_modules" / "hyperframes" / "package.json"
        return json.loads(pkg.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "?"


def _summary(e):
    size = "sabit tuval" if e["resolution"] == "native" else (e["resolution"] + (" dikey" if e["vertical"] else ""))
    line = f"{e['code']}  {e['file']}  {e['template']}  {e['frames']} kare  {size}"
    return line + ("  arşivden" if e["from_archive"] else "")


def list_templates(ctx, as_json):
    design = ctx.design or designs.Config(ctx.root).design
    designs.design_dir(ctx.root, design)
    ts = designs.templates(ctx.root, design)
    if as_json:
        data = [{"name": t.name, "description": t.description, "output": t.output, "vertical": t.vertical,
                 "frames": t.frames,
                 "fields": [{"name": f.name, "type": f.type, "required": f.required, "help": f.help}
                            for f in t.fields]} for t in ts]
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    print(f"Tasarım: {design}" + ("  (başlangıç örneği)" if design == "starter" else ""))
    for t in ts:
        fs = ", ".join(f.name + ("*" if f.required else "") for f in t.fields)
        print(f"  {t.name}  [{t.output}, {t.status}]  {t.description}\n      alanlar: {fs}")
    return 0


def main(argv, env=os.environ, run=hf.run, now=None):
    try:
        a = parse(argv)
    except UsageError as err:
        print(f"Kullanım hatası: {err}", file=sys.stderr)
        return 1
    now = now or datetime.now().astimezone()
    ctx = Context(root=Path(a.root), archive=Archive(a.archive), run=run, out=None, design=a.design, fps=a.fps,
                  resolution=a.resolution, fresh=a.fresh, home=Path(env.get("HOME") or Path.home()))
    try:
        if a.reindex:
            print(f"{len(ctx.archive.write_index())} grafik dizinlendi")
            return 0
        if a.list:
            return list_templates(ctx, a.json)
        if a.samples:
            return run_samples(a.samples, ctx, Path(a.out) if a.out else None, now)
        if a.batch:
            with open(a.batch, encoding="utf-8") as f:
                rows = json.load(f)
            return run_batch(rows, ctx, Path(a.out), now)
        row = {"template": a.template, "code": a.code, "fields": fields_from_args(a.set, a.fields_file),
               "variant": a.variant, "vertical": a.vertical, "frames": a.frames}
        return run_single(row, ctx, Path(a.out) if a.out else None, now)
    except RequestError as err:
        print("Geçersiz istek:", file=sys.stderr)
        for p in err.problems:
            print(f"  - {p}", file=sys.stderr)
        return 2
    except designs.DesignError as err:
        print(f"Geçersiz istek: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # noqa: BLE001  (one clear line for the editor)
        print(f"Hata: {err}", file=sys.stderr)
        return 1


def run_single(row, ctx, out, now):
    r = resolve(row, ctx)
    if out is None:
        slug = deliver.slugify(_first_text(r["t"], r["values"])) if _first_text(r["t"], r["values"]) else ""
        out = ctx.home / "Downloads" / "grafik" / (r["t"].name + (f"-{slug}" if slug else ""))
    ctx.out, ctx.results = out, deliver.load_results(out)
    e = render_row(row, ctx)
    deliver.save(out, ctx.results, [], now)
    _report([e], out)
    return 0


def run_batch(rows, ctx, out, now):
    ctx.out, ctx.results = out, deliver.load_results(out)
    done, notes = [], []
    try:
        for i, row in enumerate(rows, 1):
            label = row.get("code") or f"satır {i}"
            try:
                done.append(render_row(row, ctx))
            except RequestError as err:
                notes += [f"{label}: {p}" for p in err.problems]
            except hf.ToolError as err:
                notes.append(f"{label}: {err}")
    finally:
        if done or notes:
            deliver.save(out, ctx.results, notes, now)
    for n in notes:
        print(f"Not: {n}", file=sys.stderr)
    if not done:
        print("Hiç grafik üretilemedi.", file=sys.stderr)
        return 2 if rows else 1
    _report(done, out)
    return 0


def run_samples(name, ctx, out, now):
    design = ctx.design or designs.Config(ctx.root).design
    t = manifest.load(designs.template_dir(ctx.root, design, name))
    path = t.dir / "samples.json"
    if not path.is_file():
        raise RequestError([f"'{name}' şablonunun samples.json dosyası yok"])
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = out or ctx.home / "Downloads" / "grafik" / "_samples" / name
    ctx.out, ctx.results = out, deliver.load_results(out)
    try:
        entries = review.samples(name, rows, lambda row: render_row(row, ctx))
    finally:
        deliver.save(out, ctx.results, [], now)
    posters = [ctx.archive.root / name / e["archive_id"] / "poster.png" for e in entries]
    sheet = review.contact_sheet(posters, out / "contact.png", run=ctx.run)
    _report(entries, out)
    print(f"Temas sayfası: {sheet}")
    return 0


def _report(entries, out):
    for e in entries:
        print(_summary(e))
    print(f"Klasör: {out}")
    if any(e["sources"] for e in entries):
        print(f"Kaynaklar: {out / 'kaynaklar.txt'}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
