"""The run log: one JSON line per thing a worker did."""

from __future__ import annotations

import json

from close.workspace import Workspace

FILE = "events.jsonl"


def log(ws: Workspace, worker: str, message: str, period: str | None = None) -> dict:
    entry = {"at": ws.as_of, "worker": worker, "period": period, "message": message}
    path = ws.state_dir / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def read(ws: Workspace) -> list[dict]:
    path = ws.state_dir / FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
