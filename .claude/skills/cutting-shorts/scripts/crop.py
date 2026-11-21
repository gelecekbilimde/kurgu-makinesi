"""Face box -> Resolve transform of a camera item on the vertical timeline (pure).

Resolve facts (reference.md, "Resolve API facts" 2), for a source that fits the timeline by width (16:9 into
1080x1920): s = (W / SW) * Zoom; source pixel (sx, sy) lands at x = W/2 + (sx - SW/2)*s + Pan and
y = H/2 + (sy - SH/2)*s - Tilt*k, with k = (SH * W / SW) / H (one Tilt unit, in timeline pixels)."""

EXTRA = 1.15      # zoom past the height fill, so the face can be framed without an edge showing
FACE_Y = 1 / 3    # the face centre's height on the frame, from the top


def _geometry(src_w, src_h, tl_w, tl_h):
    fit = tl_w / src_w
    zoom = (tl_h / src_h) / fit * EXTRA
    return zoom, fit * zoom, src_h * fit / tl_h  # zoom, source scale, pixels per Tilt unit


def transform(face, src_w, src_h, tl_w=1080, tl_h=1920):
    """{"ZoomX","ZoomY","Pan","Tilt"}: the face centre ({"cx","cy","h"} in source pixels) horizontally centred
    and at FACE_Y of the frame height, both clamped so no edge of the image shows; face None -> centre crop."""
    zoom, s, k = _geometry(src_w, src_h, tl_w, tl_h)
    pan = tilt = 0.0
    if face is not None:
        pan_max = (src_w * s - tl_w) / 2
        tilt_max = (src_h * s - tl_h) / 2 / k
        pan = max(-pan_max, min(pan_max, -(face["cx"] - src_w / 2) * s))
        tilt = max(-tilt_max, min(tilt_max, (tl_h / 2 - tl_h * FACE_Y + (face["cy"] - src_h / 2) * s) / k))
    return {"ZoomX": round(zoom, 6), "ZoomY": round(zoom, 6), "Pan": round(pan, 3), "Tilt": round(tilt, 3)}


def window(t, src_w, src_h, tl_w=1080, tl_h=1920):
    """(x, y, w, h): the source rectangle transform t shows on the whole timeline frame, in source pixels."""
    fit = tl_w / src_w
    s, k = fit * t["ZoomX"], src_h * fit / tl_h
    return (src_w / 2 + (-tl_w / 2 - t["Pan"]) / s, src_h / 2 + (-tl_h / 2 + t["Tilt"] * k) / s,
            tl_w / s, tl_h / s)
