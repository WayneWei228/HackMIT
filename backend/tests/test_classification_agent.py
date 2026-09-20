from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select

from tests.support import bare_obligation
from trueup.agents import classification_agent as ca
from trueup.agents.classification_agent import (
    ClassificationOpinion,
    StructuralFacts,
    classify,
    classify_structure,
)
from trueup.close_orchestrator import NO_EVIDENCE, walk_to
from trueup.gateway import llm
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
PERIOD = "2026-12"
P = e.PurchaseType
EXPECTED = {
    "VEN-MINTLIFY": P.FIXED_RECURRING,
    "VEN-OPENAI": P.USAGE_BASED,
    "VEN-ASUS": P.RECEIPT_BASED,
    "VEN-META": P.MILESTONE_BASED,
    "VEN-NOTABILITY": P.PREPAID,
}


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def sim(world):
    return Simulator.from_world(world)


@pytest.fixture
def session(sim):
    with sim.session() as s:
        yield s


def open_for(session, vendor_id):
    return walk_to(session, vendor_id, PERIOD, now=NOW, settings=NO_EVIDENCE)


def opinion(kind, reason="from the text"):
    return lambda _text: ClassificationOpinion(purchase_type=kind, reason=reason)


def clone(session, row, **overrides):
    columns = {a.key: getattr(row, a.key) for a in inspect(row).mapper.column_attrs}
    new = type(row)(**{**columns, **overrides})
    session.add(new)
    session.flush()
    return new


def clone_vendor(session, source_id, new_id, name):
    """Copy a demo vendor's structure under a new id and name."""
    clone(session, session.get(m.CompanyVendor, source_id), vendor_id=new_id, vendor_name=name)
    for i, contract in enumerate(
        session.scalars(select(m.CompanyContract).where(m.CompanyContract.vendor_id == source_id))
    ):
        clone(
            session,
            contract,
            contract_row_id=f"{new_id}-C{i}",
            contract_id=f"CON-{new_id}",
            vendor_id=new_id,
        )
    for po in session.scalars(
        select(m.CompanyPurchaseOrder)
        .where(m.CompanyPurchaseOrder.vendor_id == source_id)
        .order_by(m.CompanyPurchaseOrder.po_id)
        .limit(1)
    ):
        clone(
            session,
            po,
            po_id=f"PO-{new_id}",
            po_number=f"PO-{new_id}",
            vendor_id=new_id,
            contract_id=f"CON-{new_id}" if po.contract_id else None,
        )


@pytest.mark.parametrize(("vendor_id", "expected"), EXPECTED.items())
def test_demo_shapes_classify_from_real_seed_rows(session, vendor_id, expected):
    obligation = open_for(session, vendor_id)
    result = classify(session, obligation.obligation_id, now=NOW)
    assert result.purchase_type == expected
    assert result.signals and all(s.points_to for s in result.signals)
    assert (result.routed_stage, result.next_action) == (
        e.WorkflowStage.ESTIMATING,
        e.NextAction.ESTIMATE,
    )
    assert obligation.purchase_type == expected
    assert obligation.assigned_agent == "classification"
    assert result.cross_check == "not_requested" and result.uncertainties == []


def test_classification_is_stable_after_late_evidence_arrives(sim):
    sim.advance_to("2026-12-31T23:00:00Z")
    with sim.session() as session:
        for vendor_id, expected in EXPECTED.items():
            obligation = open_for(session, vendor_id)
            result = classify(session, obligation.obligation_id, now=NOW)
            assert result.purchase_type == expected, vendor_id
            assert result.next_action == e.NextAction.ESTIMATE, vendor_id


@pytest.mark.parametrize(("source_id", "expected"), EXPECTED.items())
def test_an_unseen_vendor_with_the_same_structure_gets_the_same_type(session, source_id, expected):
    clone_vendor(session, source_id, "VEN-ZORBLAX", "Zorblax Labs")
    obligation = open_for(session, "VEN-ZORBLAX")
    assert classify(session, obligation.obligation_id, now=NOW).purchase_type == expected


def test_no_structure_at_all_is_unknown_and_goes_to_the_controller(session):
    session.add(
        m.CompanyVendor(**_vendor_columns(session, "VEN-MINTLIFY", "VEN-BLANK", "Blank Co"))
    )
    session.flush()
    obligation = bare_obligation(session, "VEN-BLANK", PERIOD, now=NOW)
    result = classify(session, obligation.obligation_id, now=NOW)
    assert result.purchase_type == P.UNKNOWN
    assert (result.routed_stage, result.next_action) == (
        e.WorkflowStage.AWAITING_CONTROLLER,
        e.NextAction.CONTROLLER_REVIEW,
    )
    assert obligation.purchase_type == P.UNKNOWN
    run = _only_run(session)
    assert run.status == e.AgentRunStatus.ESCALATED
    assert any("could not decide" in u for u in run.uncertainties_json)


def _vendor_columns(session, source_id, new_id, name):
    row = session.get(m.CompanyVendor, source_id)
    columns = {a.key: getattr(row, a.key) for a in inspect(row).mapper.column_attrs}
    return {**columns, "vendor_id": new_id, "vendor_name": name}


def _only_run(session):
    return session.scalars(
        select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "classification")
    ).one()


def test_llm_disagreement_routes_to_the_controller_and_keeps_the_rules_type(session):
    obligation = open_for(session, "VEN-MINTLIFY")
    result = classify(
        session, obligation.obligation_id, now=NOW, cross_check=opinion(P.USAGE_BASED)
    )
    assert result.cross_check == "disagreed"
    assert result.purchase_type == P.FIXED_RECURRING == obligation.purchase_type
    assert result.next_action == e.NextAction.CONTROLLER_REVIEW
    assert any("USAGE_BASED" in u and "FIXED_RECURRING" in u for u in result.uncertainties)
    assert _only_run(session).status == e.AgentRunStatus.ESCALATED


def test_llm_agreement_advances_and_records_the_opinion(session):
    obligation = open_for(session, "VEN-OPENAI")
    result = classify(
        session, obligation.obligation_id, now=NOW, cross_check=opinion(P.USAGE_BASED, "per call")
    )
    assert result.cross_check == "agreed" and result.opinion.reason == "per call"
    assert result.next_action == e.NextAction.ESTIMATE
    assert _only_run(session).status == e.AgentRunStatus.COMPLETED


def test_an_unknown_opinion_is_inconclusive_and_does_not_reroute(session):
    obligation = open_for(session, "VEN-META")
    result = classify(session, obligation.obligation_id, now=NOW, cross_check=opinion(P.UNKNOWN))
    assert result.cross_check == "inconclusive"
    assert result.next_action == e.NextAction.ESTIMATE
    assert result.uncertainties


def test_cross_check_is_skipped_and_logged_when_no_model_is_configured(session):
    assert not llm.available()
    obligation = open_for(session, "VEN-ASUS")
    result = classify(session, obligation.obligation_id, now=NOW, cross_check=True)
    assert result.cross_check == "skipped_no_model"
    assert result.next_action == e.NextAction.ESTIMATE
    assert "no model" in _only_run(session).uncertainties_json[0]


def test_default_cross_check_masks_dollar_amounts_in_the_prompt(session, monkeypatch):
    seen = {}

    def fake_complete_json(prompt, schema, **_):
        seen["prompt"] = prompt
        return schema(purchase_type="FIXED_RECURRING", reason="flat monthly fee")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    obligation = open_for(session, "VEN-MINTLIFY")
    result = classify(session, obligation.obligation_id, now=NOW, cross_check=True)
    assert result.cross_check == "agreed"
    assert "[amount]" in seen["prompt"]
    assert "$1,400" not in seen["prompt"] and "$1,200" not in seen["prompt"]


def test_a_failed_cross_check_is_recorded_and_does_not_reroute(session):
    def broken(_text):
        raise llm.LLMError("boom")

    obligation = open_for(session, "VEN-NOTABILITY")
    result = classify(session, obligation.obligation_id, now=NOW, cross_check=broken)
    assert result.cross_check == "failed" and result.next_action == e.NextAction.ESTIMATE
    assert "boom" in result.uncertainties[0]


def test_evidence_that_contradicts_the_rules_goes_to_the_controller(session):
    usage = session.scalars(
        select(m.CompanyServiceEvidence).where(m.CompanyServiceEvidence.vendor_id == "VEN-OPENAI")
    ).first()
    clone(session, usage, service_evidence_id="USE-ODD-1", vendor_id="VEN-MINTLIFY", po_id=None)
    obligation = open_for(session, "VEN-MINTLIFY")
    result = classify(session, obligation.obligation_id, now=NOW)
    assert result.purchase_type == P.FIXED_RECURRING
    assert result.next_action == e.NextAction.CONTROLLER_REVIEW
    assert any("System usage" in u for u in result.uncertainties)


def test_wrong_stage_raises_and_writes_nothing(session):
    obligation = open_for(session, "VEN-MINTLIFY")
    classify(session, obligation.obligation_id, now=NOW)
    before_runs = len(session.scalars(select(m.TrueUpAgentRun)).all())
    with pytest.raises(IllegalTransitionError):
        classify(session, obligation.obligation_id, now=NOW)
    assert len(session.scalars(select(m.TrueUpAgentRun)).all()) == before_runs


def test_unknown_obligation_raises(session):
    with pytest.raises(LookupError):
        classify(session, "OBL-NOPE", now=NOW)


def test_run_log_records_signals_inputs_and_output(session):
    obligation = open_for(session, "VEN-ASUS")
    card = m.TrueUpEvidence(
        evidence_id="EVD-ASUS-01",
        obligation_id=obligation.obligation_id,
        evidence_type=e.EvidenceCardType.PO_DETAIL,
        source_table="document",
        source_id="FILE-ASUS-02",
        fact="Ordered quantity: 25",
        value_json={"key": "ORDERED_QUANTITY", "number": "25"},
        source_excerpt="25 laptops",
        confidence=1,
        status=e.EvidenceCardStatus.VERIFIED,
        created_by_agent="evidence",
        created_at=NOW,
    )
    session.add(card)
    session.flush()
    classify(session, obligation.obligation_id, now=NOW)
    run = _only_run(session)
    assert (run.agent_name, run.action) == ("classification", "classify_purchase")
    assert run.status == e.AgentRunStatus.COMPLETED
    assert run.obligation_id == obligation.obligation_id
    assert {"po.item_category", "po.receipt_required"} <= {f["name"] for f in run.facts_used_json}
    assert "PO-ASUS-2026" in run.input_record_ids_json
    assert "EVD-ASUS-01" in run.input_record_ids_json
    assert run.output_record_ids_json == [obligation.obligation_id]
    assert run.uncertainties_json is None


def test_prepaid_round_trips_through_the_store(session, sim):
    obligation = open_for(session, "VEN-NOTABILITY")
    classify(session, obligation.obligation_id, now=NOW)
    session.commit()
    with sim.session() as other:
        assert other.get(m.TrueUpObligation, obligation.obligation_id).purchase_type == P.PREPAID
    assert e.PurchaseType("PREPAID") is P.PREPAID


def test_rules_read_structure_only_and_never_a_vendor():
    import inspect as pyinspect

    source = pyinspect.getsource(ca.classify_structure) + pyinspect.getsource(ca._facts)
    for needle in ("vendor_id", "vendor_name", "VEN-", "Mintlify", "OpenAI", "ASUS", "Meta"):
        assert needle not in source


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (StructuralFacts(contract_billing_model="SEAT_BASED"), P.USAGE_BASED),
        (StructuralFacts(contract_billing_model="MILESTONE_BASED"), P.MILESTONE_BASED),
        (
            StructuralFacts(
                contract_billing_model="FIXED_FEE", contract_billing_frequency="QUARTERLY"
            ),
            P.FIXED_RECURRING,
        ),
        (
            StructuralFacts(
                po_present=True,
                po_order_type="STANDARD",
                line_categories=("SERVICE",),
                po_window_months=12,
            ),
            P.FIXED_RECURRING,
        ),
        (StructuralFacts(non_po_sources=("CORPORATE_CARD",)), P.NON_PO_CARD_SPEND),
        (StructuralFacts(non_po_sources=("DIRECT_NON_PO_INVOICE",)), P.NON_PO_DIRECT_SPEND),
        (StructuralFacts(contract_billing_model="TIME_AND_MATERIALS"), P.UNKNOWN),
        (StructuralFacts(), P.UNKNOWN),
    ],
)
def test_rule_table(facts, expected):
    assert classify_structure(facts)[0] == expected


def test_a_material_line_without_receipts_is_not_receipt_based():
    facts = StructuralFacts(
        po_present=True,
        po_order_type="STANDARD",
        line_categories=("MATERIAL",),
        receipt_required=False,
    )
    assert classify_structure(facts)[0] == P.UNKNOWN
    assert classify_structure(replace(facts, receipt_required=True))[0] == P.RECEIPT_BASED
