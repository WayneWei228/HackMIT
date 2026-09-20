"""Invoice Lookup agent: match PO lines to their AP invoices.

Only `find_invoice` is implemented in this task. `settle` (matching cases to
invoices/actuals for closeout) belongs to a later task.
"""

from __future__ import annotations

from system import store
from system.workspace import Workspace


def find_invoice(ws: Workspace, po_line_id: str, period: str) -> dict | None:
    """Return the `ap_invoices` row for `po_line_id` whose `Service_Period` is
    `period`, or None when there isn't one."""
    invoices = store.load_table(ws, "ap_invoices")
    for invoice in invoices:
        if invoice["PO_Line_ID"] == po_line_id and invoice.get("Service_Period") == period:
            return invoice
    return None
