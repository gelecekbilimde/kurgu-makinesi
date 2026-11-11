"""Transcribe every clip twice with Resolve (word timings): the recorder WAV (primary) and the synced
camera clip (second opinion), in the manifest language. Resumable: existing JSON files are kept.

Resolve runs ONE transcription job at a time: while one runs, TranscribeAudio() on another clip
returns None (it is not queued). So: start one, poll until done, then the next. ~2-3 min per 10 min
of audio on a decent GPU.
Usage: scripts/rv.sh scripts/transcribe.py <episode dir>
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import DaVinciResolveScript as d
from episode import Episode

ep = Episode(sys.argv[1])
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
assert p.SetSetting("transcriptionExtendedLanguageSupport", "1")
assert p.SetSetting("transcriptionLanguage", ep.m.get("language", "tr")), "language rejected: run resolve_setup.py"
bins = {s.GetName(): s for s in mp.GetRootFolder().GetSubFolderList()}
os.makedirs(ep.path("transcripts"), exist_ok=True)
jobs = []
for c in ep.clips():
    if c.get("recorder"):
        jobs.append((c["bin"], ep.wav_clip(c), ep.wav_tr(c)))
    jobs.append((c["bin"], c["clip"], ep.cam_tr(c)))
t0 = time.time()
for b, name, out in jobs:
    if os.path.exists(out):
        print(f"skip {name} (exists)", flush=True); continue
    clip = {x.GetName(): x for x in bins[b].GetClipList()}[name]
    clip.ClearTranscription()
    while not clip.TranscribeAudio(False):           # wait until Resolve accepts the job
        time.sleep(10)
    t1 = time.time()
    while True:
        tr = clip.GetTranscription()
        if tr and tr.get("segments"):
            break
        if time.time() - t1 > 3600:
            sys.exit(f"timeout on {name}")
        time.sleep(5)
    json.dump(tr, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    words = sum(len(s.get("words", [])) for s in tr["segments"])
    print(f"{time.time() - t0:5.0f}s {name}: {time.time() - t1:.0f}s, lang={tr.get('language')}, "
          f"{len(tr['segments'])} segments, {words} words -> {os.path.relpath(out, ep.dir)}", flush=True)
