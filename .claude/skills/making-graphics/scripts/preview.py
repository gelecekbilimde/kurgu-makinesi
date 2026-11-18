"""Preview a template in HyperFrames Studio: stage it with sample values baked in as defaults and start a background
preview server. The editor watches and scrubs it in the browser before rendering."""
import json
import re
import urllib.request
from pathlib import Path

import hf
import manifest
import stage


def _http_ok(url):
    try:
        with urllib.request.urlopen(url.split("#")[0], timeout=10) as r:
            return r.status == 200
    except OSError:
        return False


def preview(t, design, variant, vertical, fields, dest, port=None, run=hf.run, http_ok=_http_ok):
    values = manifest.validate(t, fields)
    frames = manifest.frame_limits(t, manifest.BASE_FPS)[0]
    if manifest.output_for(t, values) == "still":
        frames = manifest.BASE_FPS
    staged = stage.stage(t, design, variant, values, vertical, frames, manifest.BASE_FPS, dest)
    stage.bake_defaults(staged)
    cmd = hf.hf_cmd("preview", staged, "--background", "--no-open", "--json", *(["--port", str(port)] if port else []))
    r = run(cmd, staged)
    if r.returncode != 0:
        raise hf.ToolError(f"önizleme başlatılamadı: {hf.last_line(r.stderr) or hf.last_line(r.stdout)}")
    url = None
    try:
        data = json.loads(r.stdout)
        res = data.get("result") or data
        url = res.get("studioUrl") or res.get("serverUrl") or res.get("url")
    except (ValueError, AttributeError):
        m = re.search(r"https?://localhost:\d+[^\s]*", r.stdout)
        url = m.group(0) if m else None
    if not url:
        raise hf.ToolError("önizleme adresi okunamadı")
    if "#project/" not in url:
        url = url.rstrip("/") + "/#project/" + Path(staged).name
    if not http_ok(url):
        raise hf.ToolError(f"önizleme sunucusu yanıt vermiyor: {url}")
    return url


def stop(dest, run=hf.run):
    return run(hf.hf_cmd("preview", dest, "--stop"), dest)
