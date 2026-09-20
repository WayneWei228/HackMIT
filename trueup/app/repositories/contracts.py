"""Contract-version selection.

Selecting by status == 'ACTIVE' is the classic bug: it silently picks today's
version when replaying a close from eight months ago. Always select by
effective-window overlap with the service period.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyContract


def effective_version(
    session: Session,
    contract_id: str,
    service_start: dt.date,
    service_end: dt.date,
) -> CompanyContract | None:
    stmt = select(CompanyContract).where(CompanyContract.contract_id == contract_id)
    candidates = [
        c
        for c in session.scalars(stmt)
        if c.effective_start_date <= service_end
        and (c.effective_end_date is None or c.effective_end_date >= service_start)
        and c.status not in ("DRAFT", "CANCELLED")
    ]
    if not candidates:
        return None
    # Latest version whose window overlaps — handles mid-period amendments.
    return sorted(candidates, key=lambda c: (c.effective_start_date, c.contract_version))[-1]


def all_versions(session: Session, contract_id: str) -> list[CompanyContract]:
    stmt = select(CompanyContract).where(CompanyContract.contract_id == contract_id)
    return sorted(session.scalars(stmt), key=lambda c: c.contract_version)
