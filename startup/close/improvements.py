"""improvements.md: what the Learning worker has learned, grouped by category.

    ## RECURRING_FIXED
    - [ACTIVE] I-001: Before copying the PO line rate, find the contract version in effect for the
      service period. If it differs, use the contract rate and raise DATA_MISMATCH.

One heading per category, one bullet per lesson, tagged [PROPOSED] or [ACTIVE]. Estimation reads only [ACTIVE]
bullets for the case's category. The file lives at state/improvements.md; a missing file means nothing learned yet.
"""
import re

BULLET = re.compile(r"^- \[(PROPOSED|ACTIVE)\]\s+(I-\d+):\s*(.*)$")


def path(ws):
    return ws.state_dir / "improvements.md"


def parse(text: str) -> list[dict]:
    lessons, category = [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            category = line[3:].strip()
        elif (m := BULLET.match(line)) and category:
            lessons.append({"id": m.group(2), "status": m.group(1), "category": category, "text": m.group(3).strip()})
        elif line.startswith((" ", "\t")) and line.strip() and lessons and lessons[-1]["category"] == category:
            lessons[-1]["text"] += " " + line.strip()  # a wrapped bullet
    return lessons


def load(ws) -> list[dict]:
    return parse(path(ws).read_text()) if path(ws).exists() else []


def active_lessons(ws, category: str) -> list[dict]:
    return [l for l in load(ws) if l["status"] == "ACTIVE" and l["category"] == category]
