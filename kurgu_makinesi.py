#!/usr/bin/env python3
"""Kurgu Makinesi Multi-Editor CLI (Kdenlive, Shotcut, Premiere Pro, CapCut).

Multi-editor project builder for gelecekbilimde/kurgu-makinesi.
Supports both the `import` subcommand and the `make` alias,
plus per-chapter generation with freeze/unfreeze state, vertical Shorts, and
round-trip marker feedback readback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from shared.capcut import write_capcut
from shared.kdenlive import write_kdenlive
from shared.markers_readback import read_markers, write_edits_json
from shared.premiere import write_premiere
from shared.script_parser import discover_scripts, parse_script
from shared.shotcut import write_shotcut
from shared.timeline import Timeline, load_cutplan

WRITERS: Dict[str, Callable[[Timeline, str | Path], Path]] = {
    "kdenlive": write_kdenlive,
    "shotcut": write_shotcut,
    "premiere": write_premiere,
    "capcut": write_capcut,
}

FREEZE_STATE_FILE = ".kurgu_frozen.json"


def _load_frozen(out_dir: Path) -> set[int]:
    state_path = out_dir / FREEZE_STATE_FILE
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return {int(x) for x in data.get("frozen_chapters", [])}
    except (OSError, json.JSONDecodeError, ValueError):
        return set()


def _save_frozen(out_dir: Path, frozen: set[int]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / FREEZE_STATE_FILE
    state_path.write_text(
        json.dumps({"frozen_chapters": sorted(frozen)}, indent=2), encoding="utf-8"
    )
    return state_path


def _resolve_formats(fmt: str) -> List[str]:
    if fmt == "all":
        return list(WRITERS.keys())
    if fmt not in WRITERS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(WRITERS)} or 'all'.")
    return [fmt]


def _export_timeline(
    tl: Timeline,
    formats: Sequence[str],
    out_dir: Path,
    chapters_mode: bool = False,
    extra_frozen: Optional[Sequence[int]] = None,
) -> List[Path]:
    written: List[Path] = []
    frozen = _load_frozen(out_dir) | set(tl.frozen_chapters) | set(extra_frozen or [])

    for fmt in formats:
        writer = WRITERS[fmt]
        target_dir = out_dir / fmt if len(formats) > 1 else out_dir
        master_path = writer(tl, target_dir)
        written.append(master_path)

        if chapters_mode:
            ch_dir = target_dir / "chapters"
            for ch_num, ch_title, ch_tl in tl.split_by_chapter():
                if ch_num in frozen:
                    print(f"  [SKIP frozen chapter {ch_num}: {ch_title}]")
                    continue
                ch_path = writer(ch_tl, ch_dir)
                written.append(ch_path)

    return written


def cmd_import(args: argparse.Namespace) -> int:
    tl = load_cutplan(
        args.cutplan,
        script_path=args.script,
        name_override=args.name,
        vertical_short=args.vertical,
    )
    formats = _resolve_formats(args.format)
    out_dir = Path(args.out)
    written = _export_timeline(
        tl,
        formats=formats,
        out_dir=out_dir,
        chapters_mode=args.chapters,
        extra_frozen=args.freeze,
    )
    for path in written:
        print(f"Wrote: {path}")
    if "capcut" in formats:
        print(
            "Note: CapCut draft_content.json targets CapCut Desktop 5.x (unencrypted); "
            "CapCut >= 6 encrypts new drafts (chapters.txt and .srt remain compatible)."
        )
    return 0


def cmd_make(args: argparse.Namespace) -> int:
    """Alias matching README.md syntax: `kurgu_makinesi.py make <editor> <cutplan.json>`."""
    args.format = args.editor
    return cmd_import(args)


def cmd_shorts(args: argparse.Namespace) -> int:
    tl = load_cutplan(
        args.plan,
        script_path=args.script,
        name_override=args.name,
        vertical_short=True,
    )
    formats = _resolve_formats(args.format)
    out_dir = Path(args.out)
    written = _export_timeline(tl, formats=formats, out_dir=out_dir, chapters_mode=False)
    for path in written:
        print(f"Wrote vertical short: {path}")
    return 0


def cmd_read_markers(args: argparse.Namespace) -> int:
    color = None if args.color.lower() == "all" else args.color
    if args.out:
        out_path = write_edits_json(
            args.project,
            args.out,
            editor=args.editor,
            color_filter=color,
            fps=args.fps,
        )
        print(f"Wrote edits JSON: {out_path}")
    else:
        markers = read_markers(args.project, editor=args.editor, color_filter=color, fps=args.fps)
        print(
            json.dumps(
                [
                    {
                        "frame": m.frame,
                        "duration_frames": m.duration_frames,
                        "name": m.name,
                        "color": m.color,
                        "note": m.note,
                    }
                    for m in markers
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    frozen = _load_frozen(out_dir)
    if args.action == "freeze":
        frozen.update(args.chapters)
    else:
        frozen.difference_update(args.chapters)
    state_path = _save_frozen(out_dir, frozen)
    print(f"Updated frozen chapters ({sorted(frozen)}) in {state_path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    scripts = discover_scripts(args.directory)
    if not scripts:
        print(f"No script files with ## chapters found in {args.directory}")
        return 0
    for sp in scripts:
        chapters = parse_script(sp)
        print(f"{sp} ({len(chapters)} chapters)")
        for ch in chapters:
            tag_summary = f" [{len(ch.tags)} B-roll/graphic tags]" if ch.tags else ""
            print(f"  {ch.index}. {ch.title}{tag_summary}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kurgu_makinesi.py",
        description="Kurgu Makinesi multi-editor builder (Kdenlive, Shotcut, Premiere Pro, CapCut).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # `import` subcommand (matches original kurgu_makinesi.py)
    p_imp = sub.add_parser("import", help="Build editor project files from a cut plan JSON.")
    p_imp.add_argument("cutplan", help="Path to cutplan.json")
    p_imp.add_argument("--script", default=None, help="Optional script (.md/.txt/.html) for chapter titles")
    p_imp.add_argument(
        "--format",
        default="all",
        choices=["kdenlive", "shotcut", "premiere", "capcut", "all"],
        help="Target editor format (default: all)",
    )
    p_imp.add_argument("--out", default="out", help="Output directory (default: out)")
    p_imp.add_argument("--name", default=None, help="Override project/timeline name")
    p_imp.add_argument("--chapters", action="store_true", help="Also emit per-chapter project files")
    p_imp.add_argument("--freeze", type=int, nargs="*", default=[], help="Chapter numbers to skip when rebuilding")
    p_imp.add_argument("--vertical", action="store_true", help="Force 1080x1920 vertical 9:16 profile")
    p_imp.set_defaults(func=cmd_import)

    # `make` subcommand (matches README.md syntax)
    p_make = sub.add_parser("make", help="Alias for `import`: make <editor> <cutplan.json>.")
    p_make.add_argument("editor", choices=["kdenlive", "shotcut", "premiere", "capcut", "all"])
    p_make.add_argument("cutplan", help="Path to cutplan.json")
    p_make.add_argument("--script", default=None, help="Optional script file")
    p_make.add_argument("--out", default="out", help="Output directory")
    p_make.add_argument("--name", default=None, help="Override project name")
    p_make.add_argument("--chapters", action="store_true", help="Also emit per-chapter project files")
    p_make.add_argument("--freeze", type=int, nargs="*", default=[], help="Chapter numbers to skip")
    p_make.add_argument("--vertical", action="store_true", help="Force 1080x1920 vertical profile")
    p_make.set_defaults(func=cmd_make)

    # `shorts` subcommand (vertical 9:16 shorts with face crop & captions)
    p_sh = sub.add_parser("shorts", help="Build 1080x1920 vertical Shorts projects with crop & captions.")
    p_sh.add_argument("plan", help="Path to shorts cutplan JSON")
    p_sh.add_argument("--script", default=None, help="Optional script file")
    p_sh.add_argument(
        "--format",
        default="all",
        choices=["kdenlive", "shotcut", "premiere", "capcut", "all"],
    )
    p_sh.add_argument("--out", default="out/shorts", help="Output directory")
    p_sh.add_argument("--name", default=None, help="Override short project name")
    p_sh.set_defaults(func=cmd_shorts)

    # `read-markers` subcommand (feedback readback -> edits JSON)
    p_rm = sub.add_parser("read-markers", help="Read Yellow (or all) markers back from an editor project.")
    p_rm.add_argument("project", help="Path to .kdenlive, .mlt, .xml, or CapCut draft directory")
    p_rm.add_argument("--editor", default=None, choices=["kdenlive", "shotcut", "premiere", "capcut"])
    p_rm.add_argument("--color", default="Yellow", help="Marker color to filter (default: Yellow, or 'all')")
    p_rm.add_argument("--fps", type=float, default=25.0, help="Fallback FPS (default: 25.0)")
    p_rm.add_argument("--out", default=None, help="Write edits JSON to this path instead of stdout")
    p_rm.set_defaults(func=cmd_read_markers)

    # `freeze` / `unfreeze` subcommands
    for act in ("freeze", "unfreeze"):
        p_fr = sub.add_parser(act, help=f"{act.capitalize()} signed-off chapter numbers in an output dir.")
        p_fr.add_argument("chapters", type=int, nargs="+", help="1-based chapter numbers")
        p_fr.add_argument("--out", default="out", help="Output directory holding .kurgu_frozen.json")
        p_fr.set_defaults(func=cmd_freeze, action=act)

    # `list` subcommand
    p_ls = sub.add_parser("list", help="List script files and chapters in a directory.")
    p_ls.add_argument("directory", nargs="?", default=".", help="Directory to scan")
    p_ls.set_defaults(func=cmd_list)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
