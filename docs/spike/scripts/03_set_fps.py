import DaVinciResolveScript as d
r=d.scriptapp("Resolve");p=r.GetProjectManager().GetCurrentProject()
print("set 25:",p.SetSetting("timelineFrameRate","25"))
for k in ["timelineFrameRate","timelinePlaybackFrameRate","transcriptionLanguage","transcriptionExtendedLanguageSupport"]:print(k,repr(p.GetSetting(k)))
