# Dump an existing Resolve transcription of a clip to JSON (no re-transcribe).
# Usage: ./rv.sh 05b_dump_transcript.py <bin> <clip name> <out.json>
import DaVinciResolveScript as d, json, sys
BIN, CLIP, OUT = sys.argv[1:4]
r = d.scriptapp("Resolve"); mp = r.GetProjectManager().GetCurrentProject().GetMediaPool()
f = [s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName() == BIN][0]
tr = {c.GetName(): c for c in f.GetClipList()}[CLIP].GetTranscription()
json.dump(tr, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("lang:", tr.get("language"), "segments:", len(tr["segments"]))
