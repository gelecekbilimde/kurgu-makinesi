# Ingest camera/recorder pairs into one bin, waveform-sync each pair, report frames + offsets.
# Usage: ./rv.sh 16_ingest.py <bin> <MOV>:<recorder folder number> ...
# Offset: linked_audio "offset" is in samples; camera_frame = wav_frame + (-offset / samples_per_frame)
import DaVinciResolveScript as d, json, glob, sys
R = "/home/ssoysal/Projects/gelecek-bilimde/kurgu/demo/cop/raw/COP/"
BIN, pairs = sys.argv[1], [a.split(":") for a in sys.argv[2:]]
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
root = mp.GetRootFolder()
f = ([s for s in root.GetSubFolderList() if s.GetName() == BIN] or [mp.AddSubFolder(root, BIN)])[0]
mp.SetCurrentFolder(f)
fps = float(p.GetSetting("timelineFrameRate"))
have = {c.GetName(): c for c in f.GetClipList()}
res = {}
for mov, rec in pairs:
    wav = glob.glob(f"{R}{rec} - */Track2-Combo 2.wav")[0]
    wname = f"{rec}-Track2.wav"
    if mov not in have:
        mp.ImportMedia([R + mov])               # list form (dict form returns None in 21.2)
    if wname not in have:
        it = mp.ImportMedia([wav])[0]
        it.SetClipProperty("Clip Name", wname)  # all recorder tracks share one file name; make unique
    have = {c.GetName(): c for c in f.GetClipList()}
    v, a = have[mov], have[wname]
    assert float(v.GetClipProperty("FPS")) == fps, f"{mov} fps {v.GetClipProperty('FPS')} != project {fps}"
    ok = mp.AutoSyncAudio([v, a], {"syncMode": r.AUDIO_SYNC_WAVEFORM, "retainEmbeddedAudio": True})
    m = json.loads(v.GetAudioMapping())
    la = list(m.get("linked_audio", {}).values())
    off_samples = la[0]["offset"] if la else None
    spf = 48000 / fps
    res[mov] = dict(rec=rec, wav_clip=wname, wav_path=wav, synced=ok, frames=int(v.GetClipProperty("Frames")),
                    offset_samples=off_samples, offset_f_exact=(-off_samples / spf) if la else None,
                    linked=la[0]["path"] if la else None)
    print(mov, res[mov])
json.dump(res, open(sys.stdout.fileno(), "w") if False else open("/home/ssoysal/Projects/gelecek-bilimde/kurgu/docs/spike/out/ingest.json", "w"), indent=1)
