"""Fakes for the media prep: a subprocess.run that writes plausible outputs instead of running FFmpeg, ffprobe,
make_graphic.py or shorts_media.py, a face detector and a speaker segmenter."""
import json
import re
import subprocess
from pathlib import Path

TEMPLATES = [
    {"name": "bar-chart", "output": "fullscreen", "vertical": False,
     "frames": {"default": 175, "min": 100, "max": 375}, "fields": []},
    {"name": "number", "output": "fullscreen", "vertical": True,
     "frames": {"default": 150, "min": 75, "max": 375}, "fields": []},
    {"name": "watermark", "output": "overlay", "vertical": False,
     "frames": {"default": 150, "min": 25, "max": 500}, "fields": [{"name": "state", "type": "enum"}]},
]


def _arg(cmd, flag):
    return cmd[cmd.index(flag) + 1]


class FakeRun:
    """Records every command. ffmpeg writes its output (an image sequence pattern gets `-frames:v` files);
    ffprobe answers 3840x2160; make_graphic.py lists `templates` and renders each batch row as <code>-1.<ext>;
    shorts_media.py faces/matte writes crop.json / the cut-out files of its job."""

    def __init__(self, templates=None):
        self.calls = []
        self.templates = TEMPLATES if templates is None else templates

    def commands(self, name):
        return [c for c in self.calls if any(Path(x).name == name for x in c[:2])]

    def __call__(self, cmd, cwd=None, capture_output=False, text=False, timeout=None, env=None, check=False):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        tool = Path(cmd[0]).name
        script = Path(cmd[1]).name if len(cmd) > 1 else ""
        if tool == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, '{"streams": [{"width": 3840, "height": 2160}]}', "")
        if tool == "ffmpeg":
            out = cmd[-1]
            if "%" in out:
                n = int(_arg(cmd, "-frames:v"))
                for i in range(n):
                    p = Path(re.sub(r"%0?(\d*)d", lambda m: f"{i:0{m.group(1) or 1}d}", out))
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"png")
            else:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_bytes(b"x")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if tool == "fc-match":
            return subprocess.CompletedProcess(cmd, 0, "/usr/share/fonts/x/Sans.ttf", "")
        if script == "make_graphic.py":
            if "--list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(self.templates), "")
            return self._graphic(cmd)
        if script == "shorts_media.py":
            return self._media(cmd)
        raise AssertionError(f"unexpected command {cmd}")

    def _graphic(self, cmd):
        rows = json.loads(Path(_arg(cmd, "--batch")).read_text(encoding="utf-8"))
        out = Path(_arg(cmd, "--out"))
        out.mkdir(parents=True, exist_ok=True)
        rp = out / "results.json"
        res = json.loads(rp.read_text()) if rp.exists() else {"created": "t", "notes": [], "renders": []}
        for r in rows:
            n = 1 + sum(1 for x in res["renders"] if re.fullmatch(re.escape(r["code"]) + r"-\d+", x["code"]))
            still = r.get("fields", {}).get("state") == "static"
            name = f"{r['code']}-{n}" + (".png" if still else ".mp4")
            (out / name).write_bytes(b"x")
            res["renders"].append({"code": f"{r['code']}-{n}", "file": name, "template": r["template"],
                                   "vertical": bool(r.get("vertical")), "frames": 1 if still else r.get("frames", 150),
                                   "output": "still" if still else "fullscreen", "background": r.get("background")})
        rp.write_text(json.dumps(res), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def _media(self, cmd):
        job_path = Path(cmd[-1])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        if cmd[2] == "faces":
            items = [dict(it, face=None, src_size=[3840, 2160],
                          transform={"ZoomX": 3.6346, "ZoomY": 3.6346, "Pan": 0.0, "Tilt": 0.0})
                     for it in job["items"]]
            (job_path.parent / "crop.json").write_text(json.dumps({"units": "frames", "items": items}))
        else:
            for c in job["cutouts"]:
                Path(c["file"]).write_bytes(b"mov")
        return subprocess.CompletedProcess(cmd, 0, "", "")


class FakeDetect:
    """detect(png) -> the next face of `faces` (a list of dict|None), recording the paths it was given."""

    def __init__(self, faces):
        self.faces, self.seen = list(faces), []

    def __call__(self, png):
        self.seen.append(str(png))
        return self.faces[len(self.seen) - 1]


class FakeSegment:
    """segment(png) -> a mask file written next to it, recording the paths it was given."""

    def __init__(self):
        self.seen = []

    def __call__(self, png):
        self.seen.append(str(png))
        out = Path(png).with_name(Path(png).stem + "-mask.png")
        out.write_bytes(b"mask")
        return str(out)
