"""Candidates file (shorts/candidates.json): load/save, boundary snapping to word gaps, validation."""
import copy
import json
import os
import re

# The rough cutter's boundary padding (rough-cutting-a-roll/scripts/cutplan.py), in frames.
PRE_F = 2
POST_F = 3

PASSAGE_S = (30, 45)
TEASER_S = (1.5, 3.5)


def load(path):
    if not os.path.exists(path):
        return {"units": "frames", "candidates": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def snap(start, end, words):
    """Snap [start, end) to word gaps on one chapter's words [(start, end, ...)] -> (start, end, moved).
    A start inside a word moves forward to the gap after it, an end inside a word back to the gap before it;
    boundaries already in a gap are padded the same way: start = max(gap middle, next word start - PRE_F),
    end = min(gap middle, previous word end + POST_F). moved: a boundary was inside a word."""
    moved = False
    new_start, new_end = start, end
    inside = next((w for w in words if w[0] < start < w[1]), None)
    if inside:
        moved, prev_end = True, inside[1]
    else:
        prev_end = max((w[1] for w in words if w[1] <= start), default=None)
    nxt = next((w[0] for w in words if w[0] >= (inside[1] if inside else start)), None)
    if nxt is not None:
        new_start = nxt - PRE_F if prev_end is None else max((prev_end + nxt) // 2, nxt - PRE_F)
    elif inside:
        new_start = inside[1]
    inside = next((w for w in words if w[0] < end < w[1]), None)
    if inside:
        moved = True
    lim = inside[0] if inside else end
    prev_end = max((w[1] for w in words if w[1] <= lim), default=None)
    nxt = next((w[0] for w in words if w[0] >= lim), None)
    if prev_end is not None:
        new_end = prev_end + POST_F if nxt is None else min((prev_end + nxt) // 2, prev_end + POST_F)
    return new_start, new_end, moved


def _next_id(cands):
    nums = [int(m.group(1)) for c in cands if (m := re.fullmatch(r"c(\d+)", str(c.get("id", ""))))]
    return max(nums, default=0) + 1


def _s(frames, fps):
    return f"{frames / fps:.1f}".replace(".", ",")


def check(data, words_by_ch, eligible, fps):
    """Validate and snap candidates -> (data, notes, errors). Assigns missing ids (c1, c2, ...), snaps every
    piece and the teaser to word gaps (chapters without words are left as they are). errors: {id: [message]}."""
    data = copy.deepcopy(data)
    notes, errors = [], {}
    cands = data.get("candidates", [])
    n = _next_id(cands)
    for c in cands:
        if not c.get("id"):
            c["id"] = f"c{n}"
            n += 1
    lo, hi = round(PASSAGE_S[0] * fps), round(PASSAGE_S[1] * fps)
    tlo, thi = round(TEASER_S[0] * fps), round(TEASER_S[1] * fps)
    if not 5 <= len(cands) <= 8:
        notes.append(f"{len(cands)} aday var (5–8 olmalı)")
    for c in cands:
        errs = errors.setdefault(c["id"], [])

        def snap_range(r, what):
            words = words_by_ch.get(r["chapter"])
            if not words:
                return
            s, e, moved = snap(r["start"], r["end"], words)
            if (s, e) != (r["start"], r["end"]):
                if moved:
                    notes.append(f"{c['id']}: {what} kelime içindeydi, [{r['start']}, {r['end']}) -> [{s}, {e})")
                r["start"], r["end"] = s, e

        pieces = c.get("pieces") or []
        if not pieces:
            errs.append("pasaj parçası yok")
        for p in pieces:
            if p["chapter"] not in eligible:
                errs.append(f"bölüm {p['chapter']} imzalı değil (A-roll ve B-roll dondurulmuş olmalı)")
            else:
                snap_range(p, f"bölüm {p['chapter']} parçası")
                if p["end"] <= p["start"]:
                    errs.append(f"bölüm {p['chapter']} parçası boş: [{p['start']}, {p['end']})")
        t = c.get("teaser")
        if t:
            if t["chapter"] in eligible:
                snap_range(t, "teaser")
            dur = t["end"] - t["start"]
            if not tlo <= dur <= thi:
                errs.append(f"teaser {_s(dur, fps)} s ({_s(tlo, fps)}–{_s(thi, fps)} s olmalı)")
            if not any(p["chapter"] == t["chapter"] and p["start"] <= t["start"] and t["end"] <= p["end"]
                       for p in pieces):
                errs.append("teaser pasajın dışında")
        else:
            errs.append("teaser yok")
        total = sum(p["end"] - p["start"] for p in pieces)
        if pieces and not lo <= total <= hi:
            errs.append(f"pasaj {_s(total, fps)} s ({PASSAGE_S[0]}–{PASSAGE_S[1]} s olmalı)")
    return data, notes, {k: v for k, v in errors.items() if v}


def timeline_name(prefix, rank, title):
    """'<prefix> short <rank> <title>', sanitised like episode.chapter_timeline_name (Resolve refuses some
    characters): title text before the first ':', then only letters, digits, spaces and , ' -"""
    title = re.sub(r"[^\w\s,'-]", "", str(title).split(":")[0]).strip()
    return f"{prefix} short {rank} {title}".strip()[:80]
