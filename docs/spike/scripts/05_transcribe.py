# Transcribe a clip in Turkish with Resolve's built-in AI; dump words to JSON.
# Usage: ./rv.sh 05_transcribe.py <bin> <clip name> <out.json>
# Attempt 1 (log section 7) ran without the extended model and with language left on 'auto'.
import DaVinciResolveScript as d, json, time, sys
BIN, CLIP, OUT = sys.argv[1:4]
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
if p.GetSetting("transcriptionExtendedLanguageSupport") != "1":
    assert p.SetSetting("transcriptionExtendedLanguageSupport", "1"), "extended language model not installed"
assert p.SetSetting("transcriptionLanguage", "tr"), "could not set Turkish"
print("lang:", p.GetSetting("transcriptionLanguage"), "ext:", p.GetSetting("transcriptionExtendedLanguageSupport"))
f = [s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName() == BIN][0]
a = {c.GetName(): c for c in f.GetClipList()}[CLIP]
a.ClearTranscription()
t0 = time.time()
print("TranscribeAudio:", a.TranscribeAudio(False))
while True:
    tr = a.GetTranscription()
    if tr and tr.get("segments"):
        break
    if time.time() - t0 > 1800:
        sys.exit("timeout")
    time.sleep(5)
print("done in %.0fs" % (time.time() - t0), "lang:", tr.get("language"), "segments:", len(tr["segments"]))
json.dump(tr, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
