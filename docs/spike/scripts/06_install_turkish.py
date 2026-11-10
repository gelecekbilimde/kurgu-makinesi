# Install Resolve's extended transcription language model (needed for Turkish) and wait for it.
import DaVinciResolveScript as d, time
PKG="Extended AI Transcription Language Support 2"
r=d.scriptapp("Resolve")
st=lambda:[x for x in r.GetExtrasPackages() if x["name"]==PKG][0]
if st()["status"]!="installed": print("queue:",r.InstallExtrasPackage(PKG))
t0=time.time();last=None
while True:
    s=st()
    if (s["status"],round(s["progress"],1))!=last: print("%4ds"%(time.time()-t0),s["status"],round(s["progress"],1),flush=True); last=(s["status"],round(s["progress"],1))
    if s["status"]=="installed": break
    if time.time()-t0>3000: raise SystemExit("timeout")
    time.sleep(10)
