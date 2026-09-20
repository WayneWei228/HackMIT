"""Load the static company seed into the 13-table store and bridge fixture records to ORM rows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter
from sqlalchemy.orm import Session

from trueup.simulator.scenario_models import PRIMARY_KEYS, TABLE_MODELS, Row, StaticCompanyData
from trueup.store import models as m

ORM_MODELS: dict[str, type[m.Base]] = {
    "company_vendors": m.CompanyVendor,
    "company_contracts": m.CompanyContract,
    "company_purchase_orders": m.CompanyPurchaseOrder,
    "company_service_evidence": m.CompanyServiceEvidence,
    "company_non_po_spend": m.CompanyNonPOSpend,
    "company_ap_invoices": m.CompanyAPInvoice,
    "company_gl_entries": m.CompanyGLEntry,
    "company_config": m.CompanyConfig,
}
LOAD_ORDER = tuple(ORM_MODELS)
JSON_COLUMNS = frozenset({"line_items_json", "lines_json", "config_value_json"})
_ANY = TypeAdapter(Any)
_FUTURE_STAMPS = ("created_at", "updated_at", "received_at")


class SeedError(ValueError):
    """The static seed is malformed or already contains future data."""


def column_value(name: str, value: Any) -> Any:
    """JSON columns hold plain JSON (money as strings); every other value passes through."""
    if name in JSON_COLUMNS:
        return _ANY.dump_python(value, mode="json")
    return value


def record_to_row(table: str, data: Row | dict[str, Any]) -> m.Base:
    """Validate a fixture record against its pydantic shape and build the ORM row."""
    model_cls = TABLE_MODELS[table]
    model = data if isinstance(data, model_cls) else model_cls.model_validate(data)
    values = {name: column_value(name, getattr(model, name)) for name in model_cls.model_fields}
    return ORM_MODELS[table](**values)


def field_values(table: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Validate a partial record (an UPDATE payload) into ORM attribute values."""
    model_cls = TABLE_MODELS[table]
    out: dict[str, Any] = {}
    for name, raw in fields.items():
        if name not in model_cls.model_fields:
            raise SeedError(f"{table} has no column {name!r}")
        adapter = TypeAdapter(model_cls.model_fields[name].annotation)
        out[name] = column_value(name, adapter.validate_python(raw))
    return out


def read_static(path: str | Path) -> StaticCompanyData:
    return StaticCompanyData.model_validate_json(Path(path).read_text())


def simulation_start(static: StaticCompanyData) -> datetime:
    return datetime.fromisoformat(static.meta["simulation_start"])


def load_static(session: Session, source: str | Path | StaticCompanyData) -> dict[str, int]:
    """Insert the day-one company. Refuses a seed that carries rows stamped after day one."""
    static = source if isinstance(source, StaticCompanyData) else read_static(source)
    start = simulation_start(static)
    counts: dict[str, int] = {}
    for table in LOAD_ORDER:
        records: list[BaseModel] = getattr(static, table)
        for record in records:
            _assert_not_future(table, record, start)
            session.add(record_to_row(table, record))
        counts[table] = len(records)
    session.flush()
    return counts


def _assert_not_future(table: str, record: BaseModel, start: datetime) -> None:
    pk = PRIMARY_KEYS[table]
    for stamp in _FUTURE_STAMPS:
        value = getattr(record, stamp, None)
        if value is not None and value > start:
            raise SeedError(
                f"{table} {getattr(record, pk)} has {stamp}={value.isoformat()} after the "
                f"simulation start {start.isoformat()}; future rows belong in scenario events"
            )
