"""Realism checks on a generated world. Each validator returns a list of violations.

`snapshot` replays events up to a timestamp, which is also how the leakage checks prove that
nothing after a close cutoff is visible to an agent standing at that cutoff.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from trueup.simulator.fixtures import close_cutoff, money, period_of
from trueup.simulator.scenario_models import (
    PRIMARY_KEYS,
    TABLE_MODELS,
    ContractRecord,
    GeneratedWorld,
    ScenarioEvent,
)
from trueup.simulator.scenario_truth import contract_in_force, effective_rate

REQUIRED_CONFIG_KEYS = (
    "people",
    "ownership_map",
    "accounting_periods",
    "approval_thresholds",
    "policy_rules",
    "allowed_gl_accounts",
)
DYNAMIC_TABLES = ("company_service_evidence", "company_non_po_spend", "company_ap_invoices")
MISMATCH_SCENARIOS = {"wrong_invoice_amount"}
OUTREACH_ROLES = {
    "AP_OWNER",
    "SERVICE_OWNER",
    "PO_OWNER",
    "PROCUREMENT_OWNER",
    "CARDHOLDER",
    "VENDOR_BILLING",
    "CONTROLLER",
}
ADVANCE_FREQUENCIES = {"MONTHLY_IN_ADVANCE", "QUARTERLY", "ANNUAL"}
VERIFIED = {"SYSTEM_VERIFIED", "OWNER_CONFIRMED"}

State = dict[str, dict[str, dict[str, Any]]]


class WorldValidationError(ValueError):
    pass


def _initial_state(world: GeneratedWorld) -> State:
    dumped = world.static.model_dump(mode="json")
    return {
        table: {row[PRIMARY_KEYS[table]]: row for row in dumped[table]} for table in TABLE_MODELS
    }


def _ordered(events: Iterable[ScenarioEvent]) -> list[ScenarioEvent]:
    return sorted(events, key=lambda e: (e.available_at, e.event_id))


def _apply(state: State, event: ScenarioEvent) -> str | None:
    pk, table = PRIMARY_KEYS[event.table], state[event.table]
    if event.operation == "INSERT":
        key = event.record.get(pk)
        if key in table:
            return f"{event.event_id}: INSERT duplicates {event.table}.{key}"
        table[key] = copy.deepcopy(event.record)
        return None
    target = table.get((event.key or {}).get(pk, ""))
    if target is None:
        return f"{event.event_id}: UPDATE target {event.key} does not exist yet"
    target.update(event.record)
    return None


def snapshot(world: GeneratedWorld, as_of: datetime | None = None) -> State:
    state = _initial_state(world)
    for event in _ordered(world.events):
        if as_of is not None and event.available_at > as_of:
            break
        _apply(state, event)
    return state


def _typed(state: State, problems: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for table, rows in state.items():
        out[table] = {}
        for key, raw in rows.items():
            try:
                out[table][key] = TABLE_MODELS[table].model_validate(raw)
            except ValidationError as exc:
                problems.append(f"{table}.{key}: invalid record: {exc.errors()[0]['msg']}")
    return out


def _final(world: GeneratedWorld, problems: list[str]) -> dict[str, dict[str, Any]]:
    return _typed(snapshot(world), problems)


def _config(models: dict[str, dict[str, Any]], key: str) -> Any:
    record = models["company_config"].get(key)
    return record.config_value_json if record is not None else None


def _all_contracts(models: dict[str, dict[str, Any]]) -> list[ContractRecord]:
    return list(models["company_contracts"].values())


def _all_evidence(world: GeneratedWorld, models: dict[str, dict[str, Any]]) -> list[Any]:
    rows = list(models["company_service_evidence"].values())
    rows += [
        o.service_evidence_on_response for o in world.outreach if o.service_evidence_on_response
    ]
    return rows


def validate_referential_integrity(world: GeneratedWorld) -> list[str]:
    problems: list[str] = []
    static = world.static.model_dump(mode="json")
    for table, pk in PRIMARY_KEYS.items():
        keys = [row[pk] for row in static[table]]
        problems += [
            f"static {table}: duplicate key {k}" for k in sorted(set(keys)) if keys.count(k) > 1
        ]
    models = _final(world, problems)
    vendors = set(models["company_vendors"])
    contracts = {c.contract_id for c in _all_contracts(models)}
    pos, invoices = set(models["company_purchase_orders"]), set(models["company_ap_invoices"])
    people = {p["person_id"] for p in _config(models, "people") or []}
    for key in REQUIRED_CONFIG_KEYS:
        if _config(models, key) is None:
            problems.append(f"company_config missing required key {key}")
    accounts = {a["account_code"] for a in _config(models, "allowed_gl_accounts") or []}

    def check(label: str, value: str | None, valid: set[str]) -> None:
        if value is not None and value not in valid:
            problems.append(f"{label}: unknown reference {value}")

    for c in models["company_contracts"].values():
        check(f"contract {c.contract_row_id} vendor", c.vendor_id, vendors)
        check(f"contract {c.contract_row_id} service owner", c.service_owner_id, people)
        check(f"contract {c.contract_row_id} procurement owner", c.procurement_owner_id, people)
    for po in models["company_purchase_orders"].values():
        check(f"PO {po.po_id} vendor", po.vendor_id, vendors)
        check(f"PO {po.po_id} contract", po.contract_id, contracts)
        check(f"PO {po.po_id} owner", po.po_owner_id, people)
        check(f"PO {po.po_id} gl", po.gl_account, accounts)
        for line in po.line_items_json:
            check(f"PO line {line.po_line_id} gl", line.gl_account_code, accounts)
    for e in _all_evidence(world, models):
        check(f"evidence {e.service_evidence_id} vendor", e.vendor_id, vendors)
        check(f"evidence {e.service_evidence_id} contract", e.contract_id, contracts)
        check(f"evidence {e.service_evidence_id} po", e.po_id, pos)
        check(f"evidence {e.service_evidence_id} person", e.confirmed_by_person_id, people)
    for row in models["company_non_po_spend"].values():
        check(f"non-PO {row.non_po_spend_id} vendor", row.vendor_id, vendors)
        check(f"non-PO {row.non_po_spend_id} cardholder", row.cardholder_id, people)
        check(f"non-PO {row.non_po_spend_id} invoice", row.ap_invoice_id, invoices)
        check(f"non-PO {row.non_po_spend_id} gl", row.gl_account, accounts)
    for inv in models["company_ap_invoices"].values():
        check(f"invoice {inv.invoice_id} vendor", inv.vendor_id, vendors)
        check(f"invoice {inv.invoice_id} po", inv.po_id, pos)
        check(f"invoice {inv.invoice_id} contract", inv.contract_id, contracts)
    for entry in models["company_gl_entries"].values():
        check(f"GL {entry.gl_entry_id} vendor", entry.vendor_id, vendors)
        for line in entry.lines_json:
            check(f"GL {entry.gl_entry_id} account", line.account_code, accounts)
    for t in world.truth:
        check(f"truth {t.period}/{t.vendor_id} vendor", t.vendor_id, vendors)
        check(f"truth {t.period}/{t.vendor_id} invoice", t.invoice_id, invoices)
    for o in world.outreach:
        if o.recipient_role not in OUTREACH_ROLES:
            problems.append(f"outreach {o.outreach_key}: unknown role {o.recipient_role}")
    for vid, owners in ((_config(models, "ownership_map") or {}).get("vendors") or {}).items():
        check(f"ownership_map {vid}", vid, vendors)
        for role, person in owners.items():
            check(f"ownership_map {vid} {role}", person, people)
    return problems


def _quantity(evidence: list[Any], vendor_id: str, start: date, end: date) -> Decimal | None:
    for row in evidence:
        if (
            row.vendor_id == vendor_id
            and row.service_start_date == start
            and row.service_end_date == end
            and row.confirmation_status in VERIFIED
            and row.evidence_type != "GOODS_RECEIPT"
            and row.quantity is not None
        ):
            return row.quantity
    return None


def _months(contract: ContractRecord) -> int:
    end = contract.effective_end_date
    assert end is not None
    return (
        (end.year - contract.effective_start_date.year) * 12
        + end.month
        - (contract.effective_start_date.month)
        + 1
    )


def _expected_invoice(
    models: dict[str, dict[str, Any]], evidence: list[Any], inv: Any
) -> Decimal | None:
    """Independent recomputation of what a vendor should bill, or None if not derivable."""
    start, end = inv.service_start_date, inv.service_end_date
    if inv.contract_id is not None and end is not None:
        contract = contract_in_force(_all_contracts(models), inv.contract_id, end)
        if contract is None or contract.base_rate is None:
            return None
        if contract.billing_model == "FIXED_FEE":
            if contract.billing_frequency == "ANNUAL":
                return money(contract.base_rate * _months(contract))
            return money(effective_rate(contract, end))
        quantity = _quantity(evidence, inv.vendor_id, start, end)
        if quantity is None:
            return None
        return money(quantity * effective_rate(contract, end))
    if inv.po_id is None or start is None or end is None:
        return None
    po = models["company_purchase_orders"].get(inv.po_id)
    if po is None:
        return None
    total = Decimal(0)
    found = False
    for row in evidence:
        if row.po_id != inv.po_id or row.service_end_date < start or row.service_start_date > end:
            continue
        if row.evidence_type == "GOODS_RECEIPT" and row.quantity is not None:
            total += money(row.quantity * po.line_items_json[0].unit_price)
            found = True
        elif row.evidence_type == "MILESTONE_ACCEPTANCE" and row.accepted_amount is not None:
            total += row.accepted_amount
            found = True
    return total if found else None


def validate_accounting_logic(world: GeneratedWorld) -> list[str]:
    problems: list[str] = []
    models = _final(world, problems)
    evidence = _all_evidence(world, models)
    for entry in models["company_gl_entries"].values():
        debit = sum((line.debit for line in entry.lines_json), Decimal(0))
        credit = sum((line.credit for line in entry.lines_json), Decimal(0))
        if debit != credit or debit <= 0:
            problems.append(f"GL {entry.gl_entry_id} is unbalanced: debit {debit} credit {credit}")
    for inv in models["company_ap_invoices"].values():
        if not inv.credit_flag and inv.amount <= 0:
            problems.append(f"invoice {inv.invoice_id}: non-positive amount {inv.amount}")
        if inv.line_items_json is not None:
            total = sum(
                (Decimal(i["quantity"]) * Decimal(i["unit_price"]) for i in inv.line_items_json),
                Decimal(0),
            )
            if money(total) != inv.amount:
                problems.append(f"invoice {inv.invoice_id}: lines {money(total)} != amount")
    for row in evidence:
        if row.quantity is not None and row.quantity <= 0:
            problems.append(f"evidence {row.service_evidence_id}: non-positive quantity")
    for row in models["company_non_po_spend"].values():
        refund = row.description.startswith("Refund")
        if row.amount < 0 and not refund:
            problems.append(f"non-PO {row.non_po_spend_id}: negative amount is not a refund")
        if refund and row.amount >= 0:
            problems.append(f"non-PO {row.non_po_spend_id}: refund must be negative")
        if row.month != period_of(row.transaction_date):
            problems.append(f"non-PO {row.non_po_spend_id}: month does not match date")
    for po in models["company_purchase_orders"].values():
        billed = sum(
            (
                i.amount
                for i in models["company_ap_invoices"].values()
                if i.po_id == po.po_id and i.status not in ("VOIDED", "REJECTED")
            ),
            Decimal(0),
        )
        if billed > po.approved_total:
            problems.append(
                f"PO {po.po_id}: invoiced {billed} exceeds approved {po.approved_total}"
            )
        for line in po.line_items_json:
            if line.quantity_ordered is not None and line.item_category == "MATERIAL":
                if money(line.quantity_ordered * line.unit_price) != po.approved_total:
                    problems.append(f"PO {po.po_id}: quantity x price != approved total")
    for t in world.truth:
        inv = models["company_ap_invoices"].get(t.invoice_id) if t.invoice_id else None
        if t.invoice_id is not None:
            if inv is None:
                problems.append(f"truth {t.period}/{t.vendor_id}: invoice {t.invoice_id} missing")
                continue
            if inv.amount != t.expected_actual_amount:
                problems.append(
                    f"invoice {inv.invoice_id}: {inv.amount} != truth {t.expected_actual_amount}"
                )
            expected = _expected_invoice(models, evidence, inv)
            if t.expected_root_cause == "UNKNOWN" or t.scenario in MISMATCH_SCENARIOS:
                if expected is not None and expected == inv.amount:
                    problems.append(f"invoice {inv.invoice_id}: mismatch case agrees with evidence")
            elif expected is not None and expected != inv.amount:
                problems.append(f"invoice {inv.invoice_id}: recomputed {expected} != {inv.amount}")
        if t.expected_root_cause == "MISSED_ESCALATOR" and inv is not None and inv.contract_id:
            contract = contract_in_force(
                _all_contracts(models), inv.contract_id, inv.service_end_date
            )
            stale, effective = t.expected_baseline_accrual, inv.amount
            if contract is None or contract.escalator_percent is None or stale is None:
                problems.append(
                    f"truth {t.period}/{t.vendor_id}: escalator case lacks escalator data"
                )
            elif money(stale * (100 + contract.escalator_percent) / 100) != effective:
                problems.append(
                    f"truth {t.period}/{t.vendor_id}: escalated amount is not stale x rate"
                )
    return problems


def validate_timeline(world: GeneratedWorld) -> list[str]:
    problems: list[str] = []
    static = world.static.model_dump(mode="json")
    start = datetime.fromisoformat(world.static.meta["simulation_start"])
    for table in DYNAMIC_TABLES:
        for row in static[table]:
            stamp = row.get("received_at") or row.get("created_at")
            if stamp and datetime.fromisoformat(stamp) > start:
                problems.append(f"static data holds future-dated rows in {table}")
                break
    for entry in world.static.company_gl_entries:
        if entry.created_at > start or entry.posting_date > start.date():
            problems.append(f"static GL {entry.gl_entry_id} is dated after the simulation start")
    ids = [e.event_id for e in world.events]
    problems += [f"duplicate event id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    state = _initial_state(world)
    for event in _ordered(world.events):
        if event.available_at < start:
            problems.append(f"{event.event_id}: available before the simulation start")
        error = _apply(state, event)
        if error:
            problems.append(error)
            continue
        model = TABLE_MODELS[event.table]
        if event.operation == "INSERT":
            try:
                model.model_validate(event.record)
            except ValidationError as exc:
                problems.append(f"{event.event_id}: invalid record: {exc.errors()[0]['msg']}")
        else:
            extra = set(event.record) - set(model.model_fields)
            if extra or PRIMARY_KEYS[event.table] in event.record:
                problems.append(f"{event.event_id}: bad update fields {sorted(extra)}")
        stamp = event.record.get("created_at") or event.record.get("received_at")
        if (
            event.operation == "INSERT"
            and stamp
            and datetime.fromisoformat(stamp) != event.available_at
        ):
            problems.append(f"{event.event_id}: record timestamp differs from available_at")
        link = event.record.get("ap_invoice_id")
        if link and link not in state["company_ap_invoices"]:
            problems.append(f"{event.event_id}: links to invoice {link} before it exists")
        if event.table == "company_contracts" and event.operation == "INSERT":
            if event.available_at.date() >= date.fromisoformat(
                event.record["effective_start_date"]
            ):
                problems.append(f"{event.event_id}: contract version appears after it is usable")
    models = _final(world, problems)
    contracts = _all_contracts(models)
    static_invoices = {i.invoice_id for i in world.static.company_ap_invoices}
    events_by_id = {
        e.record["invoice_id"]: e
        for e in world.events
        if e.table == "company_ap_invoices" and e.operation == "INSERT"
    }
    for inv in models["company_ap_invoices"].values():
        if inv.service_end_date is None:
            continue
        contract = (
            contract_in_force(contracts, inv.contract_id, inv.service_end_date)
            if inv.contract_id
            else None
        )
        advance = contract is not None and contract.billing_frequency in ADVANCE_FREQUENCIES
        if not advance and inv.invoice_date < inv.service_end_date:
            problems.append(f"invoice {inv.invoice_id}: dated before its service ended")
        if inv.received_at.date() < inv.invoice_date:
            problems.append(f"invoice {inv.invoice_id}: received before it was issued")
        cutoff = close_cutoff(period_of(inv.service_end_date))
        if not advance and inv.received_at <= cutoff:
            problems.append(f"invoice {inv.invoice_id}: arrives before close")
        if inv.invoice_id not in static_invoices:
            event = events_by_id.get(inv.invoice_id)
            if event is None or event.available_at != inv.received_at:
                problems.append(f"invoice {inv.invoice_id}: no insert event at its received time")
        needs_evidence = contract is not None and contract.billing_model != "FIXED_FEE"
        needs_evidence = needs_evidence or (inv.contract_id is None and inv.po_id is not None)
        if needs_evidence and not any(
            row.vendor_id == inv.vendor_id
            and row.created_at <= cutoff
            and row.service_end_date >= inv.service_start_date
            and row.service_start_date <= inv.service_end_date
            for row in models["company_service_evidence"].values()
        ):
            problems.append(f"invoice {inv.invoice_id}: no service evidence available by close")
    problems += _leakage(world)
    for t in world.truth:
        if t.invoice_id in models["company_ap_invoices"]:
            if models["company_ap_invoices"][t.invoice_id].received_at != t.invoice_arrival_time:
                problems.append(f"truth {t.invoice_id}: arrival differs from received_at")
    for o in world.outreach:
        record = o.service_evidence_on_response
        if o.available_at < start or (record and record.created_at != o.available_at):
            problems.append(f"outreach {o.outreach_key}: bad availability")
    return problems


def _leakage(world: GeneratedWorld) -> list[str]:
    problems: list[str] = []
    for period in world.static.meta["live_periods"]:
        cutoff = close_cutoff(period)
        visible = _typed(snapshot(world, cutoff), problems)
        for inv in visible["company_ap_invoices"].values():
            if inv.received_at > cutoff:
                problems.append(f"{period}: invoice {inv.invoice_id} leaks past the cutoff")
        for row in visible["company_service_evidence"].values():
            if row.created_at > cutoff:
                problems.append(
                    f"{period}: evidence {row.service_evidence_id} leaks past the cutoff"
                )
        for row in visible["company_non_po_spend"].values():
            if row.created_at > cutoff:
                problems.append(f"{period}: spend {row.non_po_spend_id} leaks past the cutoff")
        for t in world.truth:
            if (
                t.period == period
                and t.invoice_arrival_time > cutoff
                and t.invoice_id in visible["company_ap_invoices"]
            ):
                problems.append(f"{period}: truth invoice {t.invoice_id} is visible at close")
    return problems


def validate_scenario_coverage(world: GeneratedWorld) -> list[str]:
    problems: list[str] = []
    meta = world.static.meta
    truth = world.truth
    models = _final(world, problems)
    historical = set(meta["historical_periods"])
    first_live = meta["live_periods"][0]

    def need(ok: bool, what: str) -> None:
        if not ok:
            problems.append(f"missing scenario coverage: {what}")

    need(
        any(
            t.scenario.startswith("clean_fixed")
            and t.expected_baseline_accrual == t.expected_actual_amount
            for t in truth
        ),
        "zero-variance accrual",
    )
    need(
        any(t.expected_root_cause == "MISSED_ESCALATOR" and t.period in historical for t in truth),
        "historical missed escalator",
    )
    need(any(t.expected_root_cause == "USAGE_VARIANCE" for t in truth), "usage variance")
    need(
        any(
            t.scenario in MISMATCH_SCENARIOS and t.expected_root_cause == "SOURCE_DATA_ERROR"
            for t in truth
        ),
        "wrong-amount invoice",
    )
    need(any(t.scenario == "prepaid_wrong_treatment" for t in truth), "prepaid wrong treatment")
    need(
        any(t.expected_actual_amount > Decimal(25000) for t in truth),
        "case above the Controller threshold",
    )
    statuses = {t.expected_close_status for t in truth if t.expected_close_status}
    need(statuses >= {"DONE", "WAITING", "BLOCKED", "NEEDS_REVIEW"}, "all four close statuses")
    need(len(historical) >= 3 and bool(meta["live_periods"]), "period cycles")

    at_close = _typed(snapshot(world, close_cutoff(first_live)), problems)
    need(
        any(
            line.item_category == "MATERIAL"
            and line.quantity_ordered is not None
            and 0 < line.quantity_received < line.quantity_ordered
            for po in at_close["company_purchase_orders"].values()
            for line in po.line_items_json
        ),
        "partial receipt accrual",
    )
    pos = models["company_purchase_orders"]
    need(
        any(
            e.evidence_type == "MILESTONE_ACCEPTANCE"
            and e.accepted_amount is not None
            and e.po_id in pos
            and e.accepted_amount < pos[e.po_id].approved_total
            for e in models["company_service_evidence"].values()
        ),
        "delivered amount below the budget",
    )
    contracts = _all_contracts(models)
    need(
        any(c.contract_version > 1 for c in contracts)
        and any(c.status == "SUPERSEDED" for c in contracts),
        "contract amendment that supersedes the prior version",
    )
    period_end = date.fromisoformat(meta["live_periods"][0] + "-28")
    need(
        any(
            (contract := contract_in_force(contracts, po.contract_id, period_end)) is not None
            and contract.billing_model == "FIXED_FEE"
            and contract.base_rate is not None
            and line.unit_price != contract.base_rate
            for po in pos.values()
            if po.contract_id
            for line in po.line_items_json
        ),
        "stale PO price that disagrees with the active contract",
    )
    lines = [line for po in pos.values() for line in po.line_items_json]
    need(any(line.useful_life_months for line in lines), "fixed-asset support (useful life)")
    need(
        any(
            e.entry_type == "MANUAL_ADJUSTMENT" and e.lines_json[0].account_code == "610100"
            for e in models["company_gl_entries"].values()
        ),
        "manual adjustment that expenses a prepaid in full",
    )
    partial = {
        e.record["vendor_id"]
        for e in world.events
        if e.table == "company_service_evidence" and e.record["confirmation_status"] == "PENDING"
    }
    need(
        any(
            o.service_evidence_on_response is not None
            and o.service_evidence_on_response.vendor_id in partial
            for o in world.outreach
        ),
        "outreach-required case with a completing reply",
    )
    need(any(o.parsed_truth.get("resolved") is False for o in world.outreach), "insufficient reply")
    return problems


def validate_all(world: GeneratedWorld) -> None:
    problems = [
        *validate_referential_integrity(world),
        *validate_accounting_logic(world),
        *validate_timeline(world),
        *validate_scenario_coverage(world),
    ]
    if problems:
        raise WorldValidationError("\n".join(problems))


__all__ = [
    "WorldValidationError",
    "snapshot",
    "validate_accounting_logic",
    "validate_all",
    "validate_referential_integrity",
    "validate_scenario_coverage",
    "validate_timeline",
]
