"""Read-only snapshot of the generated company as of a simulated time.

File builders read every number, date and name from this view so the documents always agree
with the database rows the agents will see.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, TypeVar

from trueup.simulator.scenario_models import (
    PRIMARY_KEYS,
    TABLE_MODELS,
    APInvoiceRecord,
    ContractRecord,
    GeneratedWorld,
    GLEntryRecord,
    PurchaseOrderRecord,
    ServiceEvidenceRecord,
    VendorRecord,
)

R = TypeVar("R")


class WorldView:
    def __init__(self, world: GeneratedWorld, as_of: datetime) -> None:
        self.as_of = as_of
        self._raw: dict[str, dict[str, dict[str, Any]]] = {t: {} for t in TABLE_MODELS}
        for table in TABLE_MODELS:
            pk = PRIMARY_KEYS[table]
            for record in getattr(world.static, table):
                data = record.model_dump(mode="json")
                self._raw[table][str(data[pk])] = data
        for event in sorted(world.events, key=lambda e: (e.available_at, e.event_id)):
            if event.available_at > as_of:
                continue
            pk = PRIMARY_KEYS[event.table]
            if event.operation == "INSERT":
                self._raw[event.table][str(event.record[pk])] = copy.deepcopy(event.record)
            else:
                assert event.key is not None
                self._raw[event.table][str(event.key[pk])].update(copy.deepcopy(event.record))

    def _rows(self, table: str, model: type[R]) -> list[R]:
        return [model.model_validate(raw) for raw in self._raw[table].values()]  # type: ignore[attr-defined]

    def vendor(self, name: str) -> VendorRecord:
        for vendor in self._rows("company_vendors", VendorRecord):
            if vendor.vendor_name.lower() == name.lower():
                return vendor
        raise KeyError(f"no vendor named {name}")

    def vendors(self) -> list[VendorRecord]:
        return self._rows("company_vendors", VendorRecord)

    def contracts(self, vendor_id: str) -> list[ContractRecord]:
        rows = [
            c for c in self._rows("company_contracts", ContractRecord) if c.vendor_id == vendor_id
        ]
        return sorted(rows, key=lambda c: (c.contract_id, c.contract_version))

    def pos(self, vendor_id: str) -> list[PurchaseOrderRecord]:
        rows = self._rows("company_purchase_orders", PurchaseOrderRecord)
        return sorted((p for p in rows if p.vendor_id == vendor_id), key=lambda p: p.po_id)

    def invoices(self, vendor_id: str) -> list[APInvoiceRecord]:
        rows = self._rows("company_ap_invoices", APInvoiceRecord)
        return sorted((i for i in rows if i.vendor_id == vendor_id), key=lambda i: i.invoice_date)

    def evidence(self, vendor_id: str) -> list[ServiceEvidenceRecord]:
        rows = self._rows("company_service_evidence", ServiceEvidenceRecord)
        return sorted(
            (e for e in rows if e.vendor_id == vendor_id),
            key=lambda e: (e.service_start_date, e.service_evidence_id),
        )

    def gl_entries(self) -> list[GLEntryRecord]:
        rows = self._rows("company_gl_entries", GLEntryRecord)
        return sorted(rows, key=lambda g: (g.posting_date, g.gl_entry_id))

    def config(self, key: str) -> Any:
        return self._raw["company_config"][key]["config_value_json"]

    def person(self, person_id: str) -> dict[str, str]:
        for person in self.config("people"):
            if person["person_id"] == person_id:
                return person
        raise KeyError(person_id)
