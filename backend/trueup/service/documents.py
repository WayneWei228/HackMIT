"""The bytes of one document the close can read, for the Documents screen's viewer.

The list of documents is the report at `/api/reports/documents`; this route only hands over the
file a row names. Read-only. The client sends a file id and gets bytes back: the path is resolved
server-side from the agent-visible manifest, so a file's location on disk never leaves this
process, and a file the simulator's clock has not released yet does not exist for the client.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from trueup.ingest.manifest import FileEntry
from trueup.service import demo_state as demo

NOT_FOUND = "No such document."
# What a browser should do with each format the manifest carries.
MEDIA_TYPES = {
    "PDF": "application/pdf",
    "TXT": "text/plain; charset=utf-8",
    "EML": "message/rfc822",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
OCTET_STREAM = "application/octet-stream"


def register(app: FastAPI) -> None:
    """Add the read-only file route to the live API."""

    @app.get("/api/documents/{file_id}/content")
    def document_content(file_id: str) -> FileResponse:
        entry = next((f for f in demo.universe().files if f.file_id == file_id), None)
        if entry is None:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        with demo.locked():
            now = _aware(demo.current().sim.now())
        if _aware(entry.available_at) > now:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        path = _resolve(entry)
        return FileResponse(
            path,
            media_type=MEDIA_TYPES.get(entry.format, OCTET_STREAM),
            filename=path.name,
            content_disposition_type="inline",
        )


def _resolve(entry: FileEntry) -> Path:
    """The manifest's own path, checked to still be a file inside the root before it is served."""
    root = Path(demo.SEED_DIR).resolve()
    path = (root / entry.path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return path


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
