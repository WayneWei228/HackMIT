"""Append-only event log: one line per agent step, for the UI's Agents panel."""

from __future__ import annotations

import json
import time
from pathlib import Path

from system.workspace import Workspace

_LOG_NAME = "events.jsonl"


def _log_path(ws: Workspace) -> Path:
    return ws.state_dir / _LOG_NAME


def log(ws: Workspace, agent: str, step: int, message: str, period: str | None = None) -> None:
    path = _log_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)

    n = 1
    if path.exists():
        with path.open() as f:
            n = sum(1 for _ in f) + 1

    record = {
        "n": n,
        "ts": time.time(),
        "agent": agent,
        "step": step,
        "period": period,
        "message": message,
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def read(ws: Workspace, since: int = 0) -> list[dict]:
    path = _log_path(ws)
    if not path.exists():
        return []
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record["n"] > since:
                records.append(record)
    return records
