import DaVinciResolveScript as d
r=d.scriptapp("Resolve")
print("version",r.GetVersionString())
p=r.GetProjectManager().GetCurrentProject()
print("project",p.GetName())
for k in ["timelineFrameRate","timelineResolutionWidth","timelineResolutionHeight"]:print(k,p.GetSetting(k))
mp=p.GetMediaPool();root=mp.GetRootFolder()
def walk(f,ind=0):
    print(" "*ind+"["+f.GetName()+"]")
    for c in f.GetClipList() or []:
        print(" "*ind+"  ",c.GetName(),c.GetClipProperty("Duration"),c.GetClipProperty("FPS"),c.GetClipProperty("Resolution"),c.GetClipProperty("File Path"))
    for s in f.GetSubFolderList() or []: walk(s,ind+2)
walk(root)
print("timelines",p.GetTimelineCount())
