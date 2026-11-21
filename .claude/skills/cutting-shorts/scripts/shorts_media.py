#!/usr/bin/env python3
"""Face crop and teaser cut-out of one short (run with the repo's .venv/bin/python: needs requirements.txt: mediapipe, numpy, opencv-contrib).
Usage: shorts_media.py faces JOB | matte JOB      (JOB = episodes/<ep>/shorts/<id>/media.json, from shorts.py prepare)

JOB: {"units": "frames", "fps", "items": [{"rec","clip","camera","src_in","src_out","segment"}],
      "cutouts": [{"item": <index into items>, "file": <abs .mov>}]}
faces: writes crop.json beside JOB: {"units", "timeline": [1080, 1920], "items": [item + "src_size", "face", "transform"]}
       (one crop per piece and camera clip: face = median {"cx","cy","h"} of 9 sampled frames of each of its
       items, in source pixels, None -> centre crop).
matte: writes each cut-out (ProRes 4444 + alpha) from crop.json's item.

Models (mediapipe Tasks API; the bundled `mediapipe.solutions` is gone from mediapipe 0.10.3x+): downloaded on first
use into the skill's gitignored .cache/models/ (MODELS below)."""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

os.environ.setdefault("GLOG_minloglevel", "2")       # mediapipe/LiteRT start-up chatter
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import crop  # noqa: E402
import faces  # noqa: E402
import matte  # noqa: E402

CACHE = HERE.parent / ".cache" / "models"
MODELS = {
    "face": ("blaze_face_short_range.tflite", "https://storage.googleapis.com/mediapipe-models/face_detector/"
             "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"),
    "segment": ("selfie_segmenter.tflite", "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
                "selfie_segmenter/float16/latest/selfie_segmenter.tflite"),
}


def model(kind):
    name, url = MODELS[kind]
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"model indiriliyor: {name}", file=sys.stderr)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, path)
    return str(path)


def src_size(video, runner=subprocess.run):
    p = runner(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "json", str(video)], capture_output=True, text=True)
    if p.returncode != 0:
        raise faces.MediaError(f"{video}: ffprobe okuyamadı")
    s = json.loads(p.stdout)["streams"][0]
    return [int(s["width"]), int(s["height"])]


class Detector:
    """mediapipe face detection: the largest face of the image as {"cx","cy","h"} in its pixels, or None."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp = mp
        self.d = vision.FaceDetector.create_from_options(
            vision.FaceDetectorOptions(base_options=BaseOptions(model_asset_path=model("face"))))

    def __call__(self, png):
        dets = self.d.detect(self.mp.Image.create_from_file(png)).detections
        if not dets:
            return None
        b = max((x.bounding_box for x in dets), key=lambda b: b.width * b.height)
        return {"cx": b.origin_x + b.width / 2, "cy": b.origin_y + b.height / 2, "h": b.height}

    def close(self):
        self.d.close()


GUIDE_RADIUS, GUIDE_EPS = 8, 1e-3


class Segmenter:
    """mediapipe selfie segmentation: a grey mask PNG beside the frame (white = speaker, soft edges)."""

    def __init__(self):
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import BaseOptions, vision
        self.mp, self.np, self.cv2 = mp, np, cv2
        self.s = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=model("segment")),
            output_confidence_masks=True, output_category_mask=False))

    def __call__(self, png):
        np, cv2 = self.np, self.cv2
        img = self.mp.Image.create_from_file(png)
        conf = self.s.segment(img).confidence_masks[0].numpy_view().astype(np.float32).reshape(img.height, img.width)
        # the model's 256x256 mask comes back upscaled with stair-step edges: an edge-aware guided filter with the
        # frame as guide smooths them along the speaker's outline (hair, ears)
        conf = cv2.ximgproc.guidedFilter(cv2.imread(png), conf, GUIDE_RADIUS, GUIDE_EPS)
        mask = np.clip(conf * 255.0 + 0.5, 0, 255).astype(np.uint8)
        out = png[:-4] + "-mask.png"
        self.cv2.imwrite(out, mask)
        return out

    def close(self):
        self.s.close()


def crop_items(items, detect, runner=subprocess.run, *, fps, workdir):
    """items + "src_size", "face", "transform": one crop per (piece, camera clip) (Ruling 11): the face is the
    median of the samples of every camera item of that clip inside that piece (segment), so the framing doesn't
    jump at the A-roll cuts inside a piece; a piece that reaches into another camera file gets a crop of its own
    there."""
    items, sizes, groups = [dict(it) for it in items], {}, {}
    for it in items:
        groups.setdefault((it["segment"], it["clip"]), []).append(it)
    for mine in groups.values():
        camera = mine[0]["camera"]
        if camera not in sizes:
            sizes[camera] = src_size(camera, runner)
        f = faces.pooled_face(camera, [[it["src_in"], it["src_out"]] for it in mine], detect, runner,
                              fps=fps, workdir=workdir)
        t = crop.transform(f, *sizes[camera], *matte.TL)
        for it in mine:
            it.update(src_size=sizes[camera], face=f, transform=t)
    return items


def cmd_faces(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    detect = Detector()
    try:
        with tempfile.TemporaryDirectory(prefix="faces-", dir=Path(job_path).parent) as tmp:
            items = crop_items(job["items"], detect, fps=job["fps"], workdir=tmp)
    finally:
        detect.close()
    out = Path(job_path).with_name("crop.json")
    out.write_text(json.dumps({"units": "frames", "timeline": list(matte.TL), "items": items},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    missing = sum(1 for it in items if it["face"] is None)
    print(f"{len(items)} kamera parçası, {missing} parçada yüz bulunamadı (ortadan kırpıldı) -> {out}", file=sys.stderr)


def cmd_matte(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    cropped = json.loads(Path(job_path).with_name("crop.json").read_text(encoding="utf-8"))["items"]
    seg = Segmenter()
    try:
        for c in job["cutouts"]:
            it = cropped[c["item"]]
            matte.cutout(it["camera"], [it["src_in"], it["src_out"]], it["transform"], c["file"], seg,
                         src_size=it["src_size"], fps=job["fps"])
            print(f"kesik konuşmacı -> {c['file']}", file=sys.stderr)
    finally:
        seg.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("faces", "matte"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        (cmd_faces if argv[0] == "faces" else cmd_matte)(argv[1])
    except faces.MediaError as err:
        print(f"Hata: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
