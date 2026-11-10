import DaVinciResolveScript as d, json
r=d.scriptapp("Resolve")
print(json.dumps(r.GetExtrasPackages(),indent=1,ensure_ascii=False)[:4000])
