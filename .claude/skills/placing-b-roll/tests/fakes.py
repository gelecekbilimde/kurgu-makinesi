"""A fake subprocess.run for fetch/stills: records commands and writes plausible outputs instead of running
the stock finder, make_graphic.py, FFmpeg, fc-match, npx or Chrome."""
import json
import subprocess
from pathlib import Path

TEMPLATES = [
    {"name": "bar-chart", "output": "fullscreen", "frames": {"default": 175, "min": 100, "max": 375},
     "fields": [{"name": "line1", "type": "text", "required": True, "help": ""},
                {"name": "bars", "type": "list", "required": True, "help": ""},
                {"name": "source", "type": "source", "required": False, "help": ""}]},
    {"name": "name-line", "output": "overlay", "frames": {"default": 125, "min": 75, "max": 250},
     "fields": [{"name": "name", "type": "text", "required": True, "help": ""}]},
]


def _arg(cmd, flag):
    return cmd[cmd.index(flag) + 1]


class FakeRun:
    """stock: {code: [duration_s, ...]} candidates delivered per finder call (missing code = nothing found).
    graphic_fail: {code: problem} rows reported in notes instead of rendered.
    shot_size: bytes the fake Chrome writes (None = no file); shot_rc: Chrome's exit code."""

    def __init__(self, stock=None, stock_rc=None, graphic_fail=None, shot_size=50_000, shot_rc=0,
                 shot_timeout=False):
        self.calls = []
        self.batches = {}  # tool -> list of batch rows per call
        self.stock = stock or {}
        self.stock_rc = stock_rc
        self.graphic_fail = graphic_fail or {}
        self.shot_size, self.shot_rc, self.shot_timeout = shot_size, shot_rc, shot_timeout

    def tool_calls(self, name):
        return [c for c in self.calls if any(Path(x).name == name for x in c[:2])]

    def __call__(self, cmd, cwd=None, capture_output=False, text=False, timeout=None, env=None, check=False):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        name = Path(cmd[1]).name if len(cmd) > 1 else ""
        tool = Path(cmd[0]).name
        if name == "find_stock.py":
            return self._stock(cmd)
        if name == "make_graphic.py":
            if "--list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(TEMPLATES), "")
            return self._graphic(cmd)
        if tool == "fc-match":
            return subprocess.CompletedProcess(cmd, 0, "/usr/share/fonts/x/NotoSans[wght].ttf", "")
        if tool == "npx":
            return subprocess.CompletedProcess(cmd, 0, "/opt/chrome/chrome-headless-shell\n", "")
        if tool == "chrome-headless-shell":
            if self.shot_timeout:
                raise subprocess.TimeoutExpired(cmd, timeout)
            out = Path(next(c for c in cmd if c.startswith("--screenshot=")).split("=", 1)[1])
            if self.shot_size is not None:
                out.write_bytes(b"\x89PNG" + b"0" * self.shot_size)
            return subprocess.CompletedProcess(cmd, self.shot_rc, "", "")
        if tool == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"png")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected command {cmd}")

    def _stock(self, cmd):
        rows = json.loads(Path(_arg(cmd, "--batch")).read_text(encoding="utf-8"))
        self.batches.setdefault("stock", []).append(rows)
        out = Path(_arg(cmd, "--out"))
        out.mkdir(parents=True, exist_ok=True)
        rp = out / "results.json"
        res = json.loads(rp.read_text()) if rp.exists() else {"created": "t", "notes": [], "requests": []}
        any_new = False
        for r in rows:
            req = next((x for x in res["requests"] if x["code"] == r["code"]), None)
            if req is None:
                req = {"query": r["query"], "code": r["code"], "orientation": r["orientation"], "notes": [],
                       "candidates": []}
                res["requests"].append(req)
            n = len(req["candidates"]) + 1
            for d in self.stock.get(r["code"], []):
                f = f"{r['code']}-{n}_pixabay-{n}.mp4"
                (out / f).write_bytes(b"mp4")
                req["candidates"].append({"code": f"{r['code']}-{n}", "file": f, "source": "pixabay",
                                          "id": str(n), "credit": f"Pixabay / user{n}", "duration_s": d,
                                          "from_cache": n == 1})
                n += 1
                any_new = True
        rp.write_text(json.dumps(res))
        rc = self.stock_rc if self.stock_rc is not None else (0 if any_new else 2)
        return subprocess.CompletedProcess(cmd, rc, "", "")

    def _graphic(self, cmd):
        rows = json.loads(Path(_arg(cmd, "--batch")).read_text(encoding="utf-8"))
        self.batches.setdefault("graphic", []).append(rows)
        out = Path(_arg(cmd, "--out"))
        out.mkdir(parents=True, exist_ok=True)
        rp = out / "results.json"
        res = json.loads(rp.read_text()) if rp.exists() else {"created": "t", "notes": [], "renders": []}
        for r in rows:
            if r["code"] in self.graphic_fail:
                res["notes"].append(f"{r['code']}: {self.graphic_fail[r['code']]}")
                continue
            n = sum(1 for x in res["renders"] if x["code"].startswith(r["code"] + "-")) + 1
            ext = ".mp4" if r.get("background") else ".mov"
            f = f"{r['code']}-{n}{ext}"
            (out / f).write_bytes(b"video")
            res["renders"].append({"code": f"{r['code']}-{n}", "file": f, "template": r["template"],
                                   "frames": r["frames"], "output": "fullscreen" if r.get("background") else "overlay",
                                   "background": bool(r.get("background")),
                                   "sources": [v for k, v in r["fields"].items() if k == "source"],
                                   "from_archive": False})
        rp.write_text(json.dumps(res))
        return subprocess.CompletedProcess(cmd, 0, "", "")
