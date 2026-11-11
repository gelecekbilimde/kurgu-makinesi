"""Prepare the open Resolve project for an episode (run once per project, before any timeline exists).

- timeline frame rate = the manifest fps (Resolve defaults to 24; it can't be changed once a timeline
  exists, and AppendToTimeline would then resample the camera frames)
- transcription language = manifest language with extended language support; for languages outside
  Resolve's base set (Turkish is one) installs the "Extended AI Transcription Language Support 2"
  Extras package and waits for it (one-off per machine, ~1-2 GB)
Usage: scripts/rv.sh scripts/resolve_setup.py <episode dir>
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import DaVinciResolveScript as d
from episode import Episode

ep = Episode(sys.argv[1])
PKG = "Extended AI Transcription Language Support 2"
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject()
assert p, "open a project in Resolve first"
fps = str(ep.fps)
if float(p.GetSetting("timelineFrameRate")) != float(fps):
    ok = p.SetSetting("timelineFrameRate", fps)
    print(f"timelineFrameRate -> {fps}: {ok}" + ("" if ok else "  (a timeline exists already? set it in Project Settings)"))
pk = [x for x in (r.GetExtrasPackages() or []) if x["name"] == PKG]
if pk and pk[0]["status"] != "installed":
    print("installing", PKG, r.InstallExtrasPackage(PKG), flush=True)
    t0 = time.time()
    while [x for x in r.GetExtrasPackages() if x["name"] == PKG][0]["status"] != "installed":
        if time.time() - t0 > 3600:
            sys.exit("timeout installing " + PKG)
        time.sleep(15)
    print(f"installed after {time.time() - t0:.0f}s")
print("extended language support:", p.SetSetting("transcriptionExtendedLanguageSupport", "1"))
lang = ep.m.get("language", "tr")
print(f"transcriptionLanguage -> {lang}:", p.SetSetting("transcriptionLanguage", lang))
for k in ["timelineFrameRate", "transcriptionLanguage", "transcriptionExtendedLanguageSupport"]:
    print(f"  {k} = {p.GetSetting(k)!r}")
