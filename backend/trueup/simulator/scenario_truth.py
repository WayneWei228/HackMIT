"""Hidden truth: what the vendor will actually bill. Never exposed to agents or stored in the DB."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from trueup.simulator.fixtures import money
from trueup.simulator.scenario_models import (
    CloseStatus,
    ContractRecord,
    HistoricalTruth,
    RootCause,
)


def contract_in_force(
    contracts: list[ContractRecord], contract_id: str, on: date
) -> ContractRecord | None:
    """The contract version whose effective dates cover `on`, whatever its status flag says."""
    for row in sorted(contracts, key=lambda c: c.contract_version):
        if row.contract_id != contract_id or row.effective_start_date > on:
            continue
        if row.effective_end_date is None or row.effective_end_date >= on:
            return row
    return None


def effective_rate(contract: ContractRecord, on: date) -> Decimal:
    assert contract.base_rate is not None
    percent, since = contract.escalator_percent, contract.escalator_effective_date
    if percent is not None and since is not None and since <= on:
        return contract.base_rate * (Decimal(100) + percent) / Decimal(100)
    return contract.base_rate


def billed_amount(quantity: Decimal, rate: Decimal) -> Decimal:
    return money(quantity * rate)


class TruthBook:
    def __init__(self) -> None:
        self.entries: list[HistoricalTruth] = []

    def add(
        self,
        period: str,
        vendor_id: str,
        scenario: str,
        invoice_id: str | None,
        actual: Decimal,
        arrival: datetime,
        root_cause: RootCause | None = None,
        baseline: Decimal | None = None,
        close_status: CloseStatus | None = None,
    ) -> None:
        self.entries.append(
            HistoricalTruth(
                period=period,
                vendor_id=vendor_id,
                scenario=scenario,
                invoice_id=invoice_id,
                expected_actual_amount=actual,
                expected_root_cause=root_cause,
                invoice_arrival_time=arrival,
                expected_baseline_accrual=baseline,
                expected_close_status=close_status,
            )
        )
