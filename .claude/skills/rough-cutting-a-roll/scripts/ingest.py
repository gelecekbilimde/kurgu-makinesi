"""Import every camera clip + its recorder WAV, waveform-sync them, store frames and offsets.

For each clip in the manifest (skipped ones too, so they can be inspected): imports the camera file
and the recorder WAV into the clip's bin, renames the WAV clip to a unique name (all recorder
tracks share file names like "Track2-Combo 2.wav"), checks the camera fps equals the manifest fps,
runs AutoSyncAudio (waveform) and writes back to episode.json:
  frames          camera clip length in frames
  offset_f_exact  camera_frame = recorder_frame + offset (from the linked audio offset in samples)
  offset_f        rounded, used by the planner (kept as is when "offset_locked": true)
Verify the offsets independently with sync_check.py before trusting them.
Usage: scripts/rv.sh scripts/ingest.py <episode dir>
"""
import json, os, sys, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import DaVinciResolveScript as d
from episode import Episode

ep = Episode(sys.argv[1])
r = d.scriptapp("Resolve"); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
root = mp.GetRootFolder()
fps = float(p.GetSetting("timelineFrameRate"))
assert fps == ep.fps, f"project fps {fps} != manifest fps {ep.fps}: run resolve_setup.py first"
for c in ep.clips(all_=True):
    bins = {s.GetName(): s for s in root.GetSubFolderList()}
    f = bins.get(c["bin"]) or mp.AddSubFolder(root, c["bin"])
    mp.SetCurrentFolder(f)
    have = {x.GetName(): x for x in f.GetClipList()}
    wname = ep.wav_clip(c)
    if c["clip"] not in have:
        mp.ImportMedia([c["camera"]])                    # list form (the dict form returns None in 21.2)
    if c.get("recorder") and wname not in have:
        it = mp.ImportMedia([c["recorder"]])[0]
        it.SetClipProperty("Clip Name", wname)
    have = {x.GetName(): x for x in f.GetClipList()}
    v = have[c["clip"]]
    assert float(v.GetClipProperty("FPS")) == fps, f"{c['clip']} is {v.GetClipProperty('FPS')} fps, project {fps}"
    c["frames"] = int(v.GetClipProperty("Frames")); c["wav_clip"] = wname
    if not c.get("recorder"):
        print(f"{c['clip']}: no recorder WAV (camera audio only)"); continue
    ok = mp.AutoSyncAudio([v, have[wname]], {"syncMode": r.AUDIO_SYNC_WAVEFORM, "retainEmbeddedAudio": True})
    la = list(json.loads(v.GetAudioMapping()).get("linked_audio", {}).values())
    if not la:
        print(f"{c['clip']}: SYNC FAILED (no linked audio) - wrong recorder file, or it is silent?"); continue
    sr = wave.open(c["recorder"]).getframerate()
    c["offset_f_exact"] = round(-la[0]["offset"] / (sr / fps), 3)
    if not c.get("offset_locked"):
        c["offset_f"] = round(c["offset_f_exact"])
    print(f"{c['clip']}: {c['frames']} f, synced {ok}, offset {c['offset_f_exact']:+.2f} f -> {c['offset_f']:+d}")
ep.save()
print("written", ep.file)
