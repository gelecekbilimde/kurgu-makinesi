"""Row checks for the A/V script template (GÖRÜNTÜ | SES): bracketed type tags, required sources and
estimated on-screen duration.

Durations are "as written": SES words at the speaker's own reading pace (speakers.json). They are
computed only by the editor-side reader; the template has no duration column (decided 2026-11-11).
"""
import math
import re

MIN_S = 2           # below this a visual can't be read
SHOT_S = 7          # one stock shot lasts about 3-7 s
LONG_S = 15         # a single visual held longer goes stale
YAZI_WPS = 3        # on-screen text: 1 s per 3 words

TAGS = ("KAMERA", "STOK", "ARŞİV", "GRAFİK", "YAZI", "KAYNAK")
WARN = {
    "too_short": "çok kısa: komşu satırla birleştir",
    "many_shots": "birden fazla çekim gerekebilir",
    "long": "uzun: bölmeyi veya hareketli grafik kullanmayı düşün",
    "yazi_short": "yazı okunamayacak kadar kısa ekranda",
    "source_missing": "kaynak eksik",
    "no_tag": "TÜR seçilmedi",
}

_FOLD = str.maketrans({"Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
                       "Â": "A", "Î": "I", "Û": "U", "̇": None})
_ALIASES = {"STOCK": "STOK", "ARCHIVE": "ARŞİV", "GRAPHIC": "GRAFİK", "TEXT": "YAZI",
            "SOURCE": "KAYNAK", "CAMERA": "KAMERA"}
_QUOTED = re.compile(r"“([^”]*)”|\"([^\"]*)\"|‘([^’]*)’")


def fold(s):
    """Upper-case with Turkish letters folded to ASCII and whitespace collapsed."""
    return " ".join(s.upper().translate(_FOLD).split())


_BY_FOLD = {fold(t): t for t in TAGS}
_BY_FOLD.update({fold(a): t for a, t in _ALIASES.items()})


def normalize_tag(s):
    return _BY_FOLD.get(fold(s))


def split_visual(cell):
    """GÖRÜNTÜ cell -> (tags, unknown tags, visual text). Tags lead the cell in square brackets:
    "[STOK, YAZI] uçak" or "[STOK][YAZI] uçak" ("," "+" "/" separate tags). An empty cell is KAMERA."""
    text = cell.strip()
    if not text:
        return ["KAMERA"], [], ""
    tags, unknown = [], []
    m = re.match(r"\[([^\]]*)\]\s*", text)
    while m:
        for raw in re.split(r"[,+/\n]", m.group(1)):
            if raw.strip():
                t = normalize_tag(raw)
                (tags if t else unknown).append(t or raw.strip())
        text = text[m.end():]
        m = re.match(r"\[([^\]]*)\]\s*", text)
    return tags, unknown, text.strip()


def count_words(ses):
    """Spoken words: pronunciation hints in parentheses and punctuation-only tokens don't count."""
    return sum(1 for tok in re.sub(r"\([^)]*\)", " ", ses).split() if any(ch.isalnum() for ch in tok))


def estimate_s(words, rate):
    return math.floor(words / rate + 0.5)


def _yazi_text(tags, visual):
    quoted = [next(g for g in m.groups() if g is not None) for m in _QUOTED.finditer(visual)]
    if quoted:
        return " ".join(quoted)
    return visual if tags == ["YAZI"] else ""


def check_row(tags, visual, ses, rate):
    """{"seconds": int | None (silent row), "warnings": codes in WARN order}."""
    words = count_words(ses)
    seconds = estimate_s(words, rate) if words else None
    found = set()
    if seconds is not None:
        if seconds < MIN_S:
            found.add("too_short")
        if set(tags) & {"STOK", "ARŞİV"} and seconds > SHOT_S:
            found.add("many_shots")
        if any(t != "KAMERA" for t in tags) and seconds > LONG_S:
            found.add("long")
        if "YAZI" in tags and count_words(_yazi_text(tags, visual)) / YAZI_WPS > seconds:
            found.add("yazi_short")
    # a K3 reference contains a digit, so it counts as a source
    if "GRAFİK" in tags and not (re.search(r"[0-9]", visual) or "http" in visual):
        found.add("source_missing")
    if "KAYNAK" in tags and "http" not in visual:
        found.add("source_missing")
    if not tags:
        found.add("no_tag")
    return {"seconds": seconds, "warnings": [w for w in WARN if w in found]}


def format_total(seconds):
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
