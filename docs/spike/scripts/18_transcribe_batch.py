# Transcribe many clips in one bin (Turkish), ONE AT A TIME, dumping each to JSON.
# Resolve runs a single transcription job at a time: while one is running, TranscribeAudio()
# on another clip returns None (not queued). So: start one, poll until done, then the next.
# Clips whose output JSON already exists are skipped (resumable).
# Usage: ./rv.sh 18_transcribe_batch.py <bin> <outdir> <clip name> [<clip name> ...]
import DaVinciResolveScript as d, json, time, sys, os
BIN, OUT, names = sys.argv[1], sys.argv[2], sys.argv[3:]
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
assert p.GetSetting("transcriptionExtendedLanguageSupport") == "1" or p.SetSetting("transcriptionExtendedLanguageSupport", "1")
assert p.SetSetting("transcriptionLanguage", "tr"), "could not set Turkish"
f = [s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName() == BIN][0]
clips = {c.GetName(): c for c in f.GetClipList()}
t0 = time.time()
for n in names:
    path = os.path.join(OUT, os.path.splitext(n)[0] + "-tr.json")
    if os.path.exists(path):
        print(f"skip {n} (exists)", flush=True); continue
    c = clips[n]
    c.ClearTranscription()
    started = None
    while not started:                       # wait until Resolve accepts the job
        started = c.TranscribeAudio(False)
        if not started:
            time.sleep(10)
    t1 = time.time()
    while True:
        tr = c.GetTranscription()
        if tr and tr.get("segments"):
            break
        if time.time() - t1 > 1800:
            sys.exit(f"timeout on {n}")
        time.sleep(5)
    json.dump(tr, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    words = sum(len(s.get("words", [])) for s in tr["segments"])
    print(f"{time.time() - t0:5.0f}s done {n} in {time.time() - t1:.0f}s: lang={tr.get('language')} "
          f"segments={len(tr['segments'])} words={words}", flush=True)
