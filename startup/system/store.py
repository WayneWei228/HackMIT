"""JSON table and state-file storage. All writes go through here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from system.workspace import Workspace

TABLES = [
    "vendors",
    "contracts",
    "po_headers",
    "po_lines",
    "ap_invoices",
    "card_statements",
    "activity",
    "documents",
]


def _table_path(ws: Workspace, name: str) -> Path:
    if name not in TABLES:
        raise ValueError(f"unknown table: {name!r}")
    return ws.db_dir / f"{name}.json"


def load_table(ws: Workspace, name: str) -> list[dict]:
    path = _table_path(ws, name)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save_table(ws: Workspace, name: str, rows: list[dict]) -> None:
    path = _table_path(ws, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))


def upsert(rows: list[dict], row: dict, key: tuple[str, ...]) -> None:
    """Replace the row matching `key` on `row`, or append it. Mutates `rows` in place."""
    row_key = tuple(row[k] for k in key)
    for i, existing in enumerate(rows):
        if tuple(existing[k] for k in key) == row_key:
            rows[i] = row
            return
    rows.append(row)


def _state_path(ws: Workspace, name: str) -> Path:
    return ws.state_dir / name


def load_state(ws: Workspace, name: str, default: Any) -> Any:
    path = _state_path(ws, name)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_state(ws: Workspace, name: str, obj: Any) -> None:
    path = _state_path(ws, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))
