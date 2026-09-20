#!/usr/bin/env python3
"""Run the API. Seeds the database first if it is empty."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from app.db.session import init_db, session_scope
from app.models import CompanyVendor
from app.services.simulator.seed import seed_all

if __name__ == "__main__":
    init_db()
    with session_scope() as s:
        if s.query(CompanyVendor).count() == 0:
            print("empty database - seeding the synthetic company")
            seed_all(s)
    uvicorn.run("app.api.main:app", host="127.0.0.1", port=8000, reload=False)
