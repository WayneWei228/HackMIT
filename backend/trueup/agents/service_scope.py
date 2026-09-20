"""Which service-evidence rows belong to an obligation.

A vendor can have more than one open order in a period. A receipt recorded against one order
must never be read as evidence for another, so an obligation that names its purchase order sees
only that order's rows and the rows tied to no order at all.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, or_

from trueup.store import models as m


def service_evidence_of(obligation: m.TrueUpObligation) -> ColumnElement[bool]:
    row = m.CompanyServiceEvidence
    own_vendor = row.vendor_id == obligation.vendor_id
    if obligation.po_id is None:
        return own_vendor
    return own_vendor & or_(row.po_id.is_(None), row.po_id == obligation.po_id)
