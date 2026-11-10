import DaVinciResolveScript as d
R="/home/ssoysal/Projects/gelecek-bilimde/kurgu/demo/cop/raw/COP/"
r=d.scriptapp("Resolve");p=r.GetProjectManager().GetCurrentProject();mp=p.GetMediaPool()
f=[s for s in mp.GetRootFolder().GetSubFolderList() if s.GetName()=="spike-372"][0]; mp.SetCurrentFolder(f)
mp.ImportMedia([R+"P1011087.MOV"])
for it in f.GetClipList():
    pr=it.GetClipProperty()
    print(it.GetName(),{k:pr.get(k) for k in ["Type","Duration","FPS","Resolution","Video Codec","Audio Ch","Audio Codec","Sample Rate","Start TC","Bit Depth","Data Level"]})
