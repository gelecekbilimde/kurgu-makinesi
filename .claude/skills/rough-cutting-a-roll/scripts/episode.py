"""Episode manifest helper (stdlib only: imported by the Resolve tools and the analysis tools).

An episode lives in one directory (e.g. episodes/cop31/) with episode.json:
{
  "prefix": "COP31",            # timeline name prefix
  "fps": 25, "language": "tr",
  "script": "script.txt",       # read-aloud script as text (templates/script/script_doc.py), relative to the episode dir
  "speaker": "Burak Cankaya",   # who is on camera; script_doc.py uses their pace (templates/script/speakers.json)
  "frozen": [],                 # signed-off chapters (1-based)
  "clips": [                    # in EPISODE ORDER; a clip that is fully replaced by a later one: "skip": "why"
    {"clip": "P1011087.MOV", "bin": "cop31",
     "camera": "/abs/P1011087.MOV", "recorder": "/abs/372 - 23 Oct 2026/Track2-Combo 2.wav",
     "wav_clip": "P1011087-rec.wav",           # recorder clip name in the media pool (set by ingest.py)
     "frames": 8520, "offset_f": 10,            # camera_frame = recorder_frame + offset_f (ingest.py)
     "offset_f_exact": 9.44, "offset_locked": false}
  ]
}
Derived files (all relative to the episode dir):
  transcripts/<stem>-wav-tr.json  transcripts/<stem>-cam-tr.json   (transcribe.py)
  plans/<stem>-plan.json          sections.json                     (plan_episode.py, sections.py)
  edits/<stem>-edits.json         timelines/<timeline>.json         (markers_to_edits.py, chapters.py)
"""
import json, os, re


def chapter_timeline_name(prefix, chapter_title, ch):
    """'COP31 ch1 Açılış' (ch is 0-based): Resolve refuses some characters in timeline names
    (CreateEmptyTimeline returned None for '§' / ':' / '?'), so: text before the first ':',
    letters, digits, spaces, ,'-"""
    title = re.sub(r"^\d+\.\s*", "", chapter_title).split(":")[0]
    title = re.sub(r"[^\w\s,'-]", "", title).strip()
    return f"{prefix} ch{ch + 1} {title}"[:80]


class Episode:
    def __init__(self, d):
        self.dir = os.path.abspath(d)
        self.file = os.path.join(self.dir, "episode.json")
        self.m = json.load(open(self.file, encoding="utf-8"))

    def save(self):
        json.dump(self.m, open(self.file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def path(self, *p):
        return os.path.join(self.dir, *p)

    @property
    def fps(self):
        return int(self.m.get("fps", 25))

    def clips(self, all_=False):
        return [c for c in self.m["clips"] if all_ or not c.get("skip")]

    @staticmethod
    def stem(c):
        return os.path.splitext(c["clip"])[0]

    def wav_clip(self, c):
        return c.get("wav_clip") or self.stem(c) + "-rec.wav"

    def wav_tr(self, c):
        return self.path(c.get("wav_transcript") or f"transcripts/{self.stem(c)}-wav-tr.json")

    def cam_tr(self, c):
        return self.path(c.get("cam_transcript") or f"transcripts/{self.stem(c)}-cam-tr.json")

    def plan(self, c):
        return self.path("plans", self.stem(c) + "-plan.json")

    def edits(self, c):
        return self.path("edits", self.stem(c) + "-edits.json")
