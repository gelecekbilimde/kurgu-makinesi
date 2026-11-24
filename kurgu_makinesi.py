#!/usr/bin/env python3
"""Kurgu Makinesi - rough-cut project writer for Kdenlive, Shotcut, Adobe Premiere Pro and CapCut.

  kurgu_makinesi.py import cutplan.json [--script script.md] [--format kdenlive|shotcut|premiere|capcut|all]
                                        [--out DIR] [--name NAME]
  kurgu_makinesi.py list [DIR]

Cut plan format: see shared/timeline.py.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared import capcut, kdenlive, premiere, shotcut  # noqa: E402
from shared.script_parser import Script, find_script_files  # noqa: E402
from shared.timeline import PlanError, load_cutplan  # noqa: E402

WRITERS = {"kdenlive": kdenlive, "shotcut": shotcut, "premiere": premiere, "capcut": capcut}
NOTES = {
    "capcut": "EXPERIMENTAL: unverified against a real CapCut install; chapters are in chapters.txt, not markers",
    "kdenlive": "A/V pairs are not grouped; open once in Kdenlive to confirm and save",
}


def cmd_import(a) -> int:
    chapters = None
    if a.script:
        try:
            script = Script(a.script).load()
        except (OSError, UnicodeDecodeError) as err:
            print(f"Error: cannot read script {a.script}: {err}", file=sys.stderr)
            return 1
        chapters = script.titles
        print(script)
    try:
        tl, warnings = load_cutplan(a.cutplan, chapters)
    except PlanError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    if a.name:
        tl.name = a.name
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    names = list(WRITERS) if a.format == "all" else [a.format]
    print(f"{tl.name}: {len(tl.clips)} clips, {tl.total_frames} frames @ {float(tl.fps):g} fps, "
          f"{tl.width}x{tl.height}, {len(tl.markers())} chapter markers")
    for n in names:
        for path in WRITERS[n].write(tl, str(out)):
            print(f"  {n}: {path}")
        if n in NOTES:
            print(f"    note: {NOTES[n]}")
    return 0


def cmd_list(a) -> int:
    for p in find_script_files(a.directory):
        print(f"  {p}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kurgu_makinesi.py",
                                 description="Kurgu Makinesi - Rough Cutting Tool for Video Editors "
                                             "(Kdenlive, Shotcut, Premiere Pro, CapCut)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("import", help="write editor project file(s) from a cut plan")
    s.add_argument("cutplan")
    s.add_argument("--script", help="script (.md/.txt) whose '## ' headings name the chapters")
    s.add_argument("--format", choices=[*WRITERS, "all"], default="all")
    s.add_argument("--out", default=".", help="output directory (default: current)")
    s.add_argument("--name", help="project name (default: cut plan name)")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("list", help="list script files")
    s.add_argument("directory", nargs="?", default=".")
    s.set_defaults(fn=cmd_list)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
