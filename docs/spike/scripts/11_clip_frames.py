import DaVinciResolveScript as d
r=d.scriptapp("Resolve");mp=r.GetProjectManager().GetCurrentProject().GetMediaPool()
f=[s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName()=="spike-372"][0]
for c in f.GetClipList(): print(c.GetName(),"Frames=",c.GetClipProperty("Frames"),"Duration=",c.GetClipProperty("Duration"))
