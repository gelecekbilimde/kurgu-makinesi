"""broll/kaynaklar.txt: the credits of what is on the B-roll timeline, ready for the video description."""
import os


def _by_file(fetched):
    """file -> its credit lines. A graphic's credit is its sources joined by "; " (fetch.py): one line each.
    A graphic's hold still carries the graphic's credit; a KAYNAK screenshot's credit is its URL."""
    out = {}
    for assets in fetched.get("rows", {}).values():
        for a in assets:
            for c in a.get("files") or []:
                credit = c.get("credit")
                if not credit:
                    continue
                lines = [s.strip() for s in credit.split(";") if s.strip()] if a["kind"] == "graphic" else [credit]
                out.setdefault(c["file"], lines)
                if a.get("hold"):
                    out.setdefault(a["hold"], lines)
    return out


def collect(items, fetched):
    """One line per distinct credit of the non-deleted items on the timeline, in timeline order. Items whose
    file fetch never delivered (an editor's own clip) have no known credit."""
    credits = _by_file(fetched)
    out = []
    for i in sorted((i for i in items if not i.get("deleted") and i.get("file")),
                    key=lambda i: (i["start"], i["track"])):
        for line in credits.get(i["file"], []):
            if line not in out:
                out.append(line)
    return out


def write(path, lines):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in lines))
