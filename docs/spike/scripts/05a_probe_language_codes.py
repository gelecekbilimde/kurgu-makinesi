import DaVinciResolveScript as d
r=d.scriptapp("Resolve");p=r.GetProjectManager().GetCurrentProject()
for c in ["en","de","tr","tr-TR","tr_TR","tur","Turkish","turkish","TR"]:
    print(c,p.SetSetting("transcriptionLanguage",c),p.GetSetting("transcriptionLanguage"))
print("ext=1:",p.SetSetting("transcriptionExtendedLanguageSupport","1"))
for c in ["tr","Turkish"]:
    print(c,p.SetSetting("transcriptionLanguage",c),p.GetSetting("transcriptionLanguage"))
p.SetSetting("transcriptionLanguage","auto")
