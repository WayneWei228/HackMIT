"""Reads of the time-gated world, writes of the canonical db tables and state files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from close.workspace import Workspace


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")


def normalise_ts(value: str) -> str:
    """A bare `YYYY-MM-DD` becomes `YYYY-MM-DDT00:00:00Z`; anything else is returned as is."""
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value + "T00:00:00Z"
    return value


def visible(rows: list[dict], as_of: str) -> list[dict]:
    """Rows a worker may see at `as_of`: no `available_at`, or one that has already passed."""
    now = normalise_ts(as_of)
    return [r for r in rows if r.get("available_at") is None or normalise_ts(r["available_at"]) <= now]


def world_raw(ws: Workspace, name: str) -> list[dict]:
    """Unfiltered world table. ONLY tests and ground-truth scoring may call this."""
    return _read_json(ws.world_dir / f"{name}.json", [])


def world(ws: Workspace, name: str) -> list[dict]:
    return visible(world_raw(ws, name), ws.as_of)


def company(ws: Workspace) -> dict:
    return _read_json(ws.world_dir / "company.json", {})


def document_text(ws: Workspace, file_name: str) -> str:
    path = ws.world_dir / "documents" / file_name
    return path.read_text() if path.exists() else ""


def load_table(ws: Workspace, name: str) -> list[dict]:
    return _read_json(ws.db_dir / f"{name}.json", [])


def save_table(ws: Workspace, name: str, rows: list[dict]) -> list[dict]:
    _write_json(ws.db_dir / f"{name}.json", rows)
    return rows


def upsert(rows: list[dict], row: dict, key: tuple[str, ...]) -> list[dict]:
    """Replace the row matching `row` on `key`, else append. Mutates and returns `rows`."""
    ident = tuple(row.get(k) for k in key)
    for i, existing in enumerate(rows):
        if tuple(existing.get(k) for k in key) == ident:
            rows[i] = row
            return rows
    rows.append(row)
    return rows


def load_state(ws: Workspace, name: str, default: Any = None) -> Any:
    return _read_json(ws.state_dir / f"{name}.json", [] if default is None else default)


def save_state(ws: Workspace, name: str, obj: Any) -> Any:
    _write_json(ws.state_dir / f"{name}.json", obj)
    return obj
