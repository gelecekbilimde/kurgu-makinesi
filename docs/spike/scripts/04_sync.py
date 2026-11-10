# Waveform-sync the host-mic WAV to the camera clip.
import DaVinciResolveScript as d, json
r=d.scriptapp("Resolve");p=r.GetProjectManager().GetCurrentProject();mp=p.GetMediaPool()
f=[s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName()=="spike-372"][0]
clips={c.GetName():c for c in f.GetClipList()}
v,a=clips["P1011087.MOV"],clips["Track2-Combo 2.wav"]
print("audio mapping before:",v.GetAudioMapping())
ok=mp.AutoSyncAudio([v,a],{"syncMode":r.AUDIO_SYNC_WAVEFORM,"retainEmbeddedAudio":True})
print("AutoSyncAudio:",ok)
print("audio mapping after:",v.GetAudioMapping())
pr=v.GetClipProperty(); print({k:pr.get(k) for k in ["Audio Ch","Synced Audio","Sync Audio","Audio Offset"] if k in pr})
