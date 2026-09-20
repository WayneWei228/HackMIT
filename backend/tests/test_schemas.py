import pytest
from pydantic import ValidationError

from trueup.schemas import Evidence, JELine, ProposedJE


def _je(**overrides):
    base = dict(
        lines=[JELine(account="6100", debit_cents=500), JELine(account="2100", credit_cents=500)],
        evidence=[Evidence(source_table="po_lines", row_id="PO-1-001")],
        rule="fixed_contract",
        reason="test",
        status="auto_approved",
    )
    return ProposedJE(**{**base, **overrides})


def test_balanced_entry_with_evidence_is_valid():
    assert _je().status == "auto_approved"


def test_entry_without_evidence_is_rejected():
    with pytest.raises(ValidationError):
        _je(evidence=[])


def test_unbalanced_entry_is_rejected_exactly():
    lines = [JELine(account="6100", debit_cents=500), JELine(account="2100", credit_cents=499)]
    with pytest.raises(ValidationError):
        _je(lines=lines)
