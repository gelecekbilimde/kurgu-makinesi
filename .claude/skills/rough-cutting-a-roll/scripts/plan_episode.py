"""Plan every clip of an episode with cutplan.py, in episode order.

Each clip: primary = recorder WAV transcript (+ offset_f), --second = camera-clip transcript,
--next = the next clip's WAV transcript (retakes that continue across a clip cut), --edits = the
editor's ranges (edits/<stem>-edits.json) when present. Writes plans/<stem>-plan.json.
Usage: .venv/bin/python scripts/plan_episode.py <episode dir>
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from episode import Episode

ep = Episode(sys.argv[1])
os.makedirs(ep.path("plans"), exist_ok=True)
clips = ep.clips()
for k, c in enumerate(clips):
    assert c.get("recorder") and "offset_f" in c, f"{c['clip']}: needs a synced recorder WAV (ingest.py)"
    cmd = [sys.executable, os.path.join(HERE, "cutplan.py"), ep.wav_tr(c), c["recorder"], c["clip"], ep.plan(c),
           str(c["offset_f"]), str(c["frames"]), str(ep.fps), "--second", ep.cam_tr(c), "0"]
    if k + 1 < len(clips):
        cmd += ["--next", ep.wav_tr(clips[k + 1]), str(clips[k + 1]["offset_f"])]
    if os.path.exists(ep.edits(c)):
        cmd += ["--edits", ep.edits(c)]
    res = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    if res.returncode:
        sys.exit(f"{c['clip']} FAILED:\n{res.stderr}")
    print(res.stdout, flush=True)
