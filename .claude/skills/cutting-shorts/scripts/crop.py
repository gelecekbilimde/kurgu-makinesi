"""Face box -> Resolve transform of a camera item on the vertical timeline (pure).

Resolve facts (reference.md, "Resolve API facts" 2), for a source that fits the timeline by width (16:9 into
1080x1920): s = (W / SW) * Zoom; source pixel (sx, sy) lands at x = W/2 + (sx - SW/2)*s + Pan and
y = H/2 + (sy - SH/2)*s - Tilt*k, with k = (SH * W / SW) / H (one Tilt unit, in timeline pixels)."""

EXTRA = 1.0  # Ruling 6: exact height fill; Tilt stays 0, so the camera's own vertical framing is kept


def _geometry(src_w, src_h, tl_w, tl_h):
    fit = tl_w / src_w
    zoom = (tl_h / src_h) / fit * EXTRA
    return zoom, fit * zoom  # zoom, source scale


def transform(face, src_w, src_h, tl_w=1080, tl_h=1920):
    """{"ZoomX","ZoomY","Pan","Tilt"}: the image filling the frame height, the face centre ({"cx","cy","h"} in
    source pixels) centred horizontally, Pan clamped so no edge of the image shows; Tilt 0 (at exact fill any
    Tilt shows an edge). face None -> centre crop."""
    zoom, s = _geometry(src_w, src_h, tl_w, tl_h)
    pan = 0.0
    if face is not None:
        pan_max = (src_w * s - tl_w) / 2
        pan = max(-pan_max, min(pan_max, -(face["cx"] - src_w / 2) * s))
    return {"ZoomX": round(zoom, 6), "ZoomY": round(zoom, 6), "Pan": round(pan, 3), "Tilt": 0.0}


def window(t, src_w, src_h, tl_w=1080, tl_h=1920):
    """(x, y, w, h): the source rectangle transform t shows on the whole timeline frame, in source pixels."""
    fit = tl_w / src_w
    s, k = fit * t["ZoomX"], src_h * fit / tl_h
    return (src_w / 2 + (-tl_w / 2 - t["Pan"]) / s, src_h / 2 + (-tl_h / 2 + t["Tilt"] * k) / s,
            tl_w / s, tl_h / s)
