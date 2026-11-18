"""A fake for hf.run: records commands and writes plausible outputs instead of rendering."""
import subprocess
from pathlib import Path


class FakeRun:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def renders(self):
        return [c for c in self.calls if "render" in c[1:2]]

    def __call__(self, cmd, cwd, runner=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if self.fail:
            return subprocess.CompletedProcess(cmd, 1, "", "Error: Chrome Headless Shell not found\n")
        if cmd[1:2] == ["render"]:
            out = Path(cmd[cmd.index("-o") + 1])
            fmt = cmd[cmd.index("--format") + 1]
            if fmt == "png-sequence":
                out.mkdir(parents=True, exist_ok=True)
                (out / "frame_000001.png").write_bytes(b"png")
            else:
                out.write_bytes(b"video " + fmt.encode())
        elif Path(cmd[0]).name == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"poster")
        return subprocess.CompletedProcess(cmd, 0, "", "")
