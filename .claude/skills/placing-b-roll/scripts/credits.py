"""broll/kaynaklar.txt: the credits of what is on the B-roll timeline, ready for the video description."""
import json
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


def tool_credits(broll_dir):
    """file (canonical path) -> credit lines of everything the tools ever delivered into broll/stok and
    broll/grafik (their results.json), including candidates of an earlier request that fetched.json no longer
    lists: the editor may drag any of them from a row bin onto the timeline."""
    out = {}
    for sub, key in (("stok", "requests"), ("grafik", "renders")):
        path = os.path.join(broll_dir, sub, "results.json")
        try:
            with open(path, encoding="utf-8") as f:
                res = json.load(f)
        except (OSError, ValueError):
            continue
        for entry in res.get(key, []):
            for c in entry.get("candidates", []) if sub == "stok" else [entry]:
                lines = [c["credit"]] if sub == "stok" and c.get("credit") else \
                    [s.strip() for s in c.get("sources") or [] if s.strip()]
                if c.get("file") and lines:
                    out.setdefault(os.path.realpath(os.path.join(broll_dir, sub, c["file"])), lines)
    return out


def collect(items, fetched, tools=None):
    """One line per distinct credit of the non-deleted items on the timeline, in timeline order. A file fetch.json
    doesn't list falls back to tools (tool_credits); a file neither knows (an editor's own clip) has no known
    credit."""
    credits = dict(tools or {})
    credits.update(_by_file(fetched))
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
