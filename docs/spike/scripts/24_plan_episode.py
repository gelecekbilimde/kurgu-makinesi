"""Plan every clip of the COP31 episode with one planner, in episode order (spike driver).

Clip order and recorder mapping come from out/ingest.json (+ clip 087 from the first spike); offsets
are the ones of the v1 episode plans (out/episode/<clip>-plan.json).
Each clip gets --second (camera-clip transcript) and --next (next clip's transcript, for retakes
that continue across a clip boundary); --edits if out/<outdir>/edits/<clip>-edits.json exists.
Usage: .venv/bin/python 24_plan_episode.py <planner.py> <outdir>
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.normpath(os.path.join(HERE, "..", "out"))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
planner, outdir = sys.argv[1], os.path.join(OUT, sys.argv[2])
os.makedirs(outdir, exist_ok=True)
ing = json.load(open(os.path.join(OUT, "ingest.json"), encoding="utf-8"))
EP = os.path.join(OUT, "episode")
clips = [dict(clip="P1011087.MOV", tr=os.path.join(OUT, "372-track2-resolve-tr.json"),
              wav=os.path.join(ROOT, "demo/cop/raw/COP/372 - 23 Oct 2026/Track2-Combo 2.wav"),
              off=10, end=8520, second=os.path.join(OUT, "087-mov-resolve-tr.json"))]
for c in ["P1011088.MOV", "P1011089.MOV", "P1011090.MOV", "P1011091.MOV", "P1011094.MOV"]:
    i = ing[c]
    clips.append(dict(clip=c, tr=os.path.join(EP, i["rec"] + "-Track2-tr.json"), wav=i["wav_path"],
                      off=json.load(open(os.path.join(EP, c[5:8] + "-plan.json")))["offset_f"], end=i["frames"], second=os.path.join(EP, c[:8] + "-tr.json")))
for k, c in enumerate(clips):
    cmd = [sys.executable, os.path.join(HERE, planner), c["tr"], c["wav"], c["clip"],
           os.path.join(outdir, c["clip"][5:8] + "-plan.json"), str(c["off"]), str(c["end"]), "25",
           "--second", c["second"], "0"]
    if k + 1 < len(clips):
        cmd += ["--next", clips[k + 1]["tr"], str(clips[k + 1]["off"])]
    ed = os.path.join(outdir, "edits", c["clip"][:8] + "-edits.json")
    if os.path.exists(ed):
        cmd += ["--edits", ed]
    print(subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONIOENCODING="utf-8")).stdout
          or "FAILED " + c["clip"], flush=True)
