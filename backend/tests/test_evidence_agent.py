import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from trueup.agents import evidence_agent, ingestion
from trueup.agents.evidence_agent import (
    DocumentFacts,
    EvidenceError,
    Fact,
    FactKey,
    card_type_for,
    collect_evidence,
    ungrounded_reason,
)
from trueup.agents.ingestion import FileDecision, ingest, load_universe
from trueup.gateway import llm
from trueup.ingest.readers import read_text
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.session import create_all, get_session, make_engine

SEED = Path(__file__).resolve().parents[1] / "seed"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
MINTLIFY = "CASE-MINTLIFY-2026-12"
AGREEMENT = "mintlify_master_subscription_agreement.pdf"
QUOTE = "shall increase from $1,200 to $1,400 per month"


@pytest.fixture(scope="module")
def universe():
    return load_universe(SEED)


def pick(*names):
    def judge(case, cards):
        return [
            FileDecision(file_id=c.entry.file_id, selected=c.entry.name in names, reason="test")
            for c in cards
        ]

    return judge


def fee_fact(**overrides):
    fields = dict(
        key=FactKey.MONTHLY_FEE,
        label="Monthly fee",
        value_text="$1,400 per month",
        number=Decimal("1400"),
        unit="USD",
        date="2026-12-01",
        quote=QUOTE,
    )
    return Fact(**{**fields, **overrides})


def returning(*facts, seen=None):
    def extractor(case, entry, text):
        if seen is not None:
            seen.append(entry.name)
        return DocumentFacts(vendor_name="Mintlify", service_period="2026-12", facts=list(facts))

    return extractor


def run(universe, facts, *, names=(AGREEMENT,), **kwargs):
    picked = ingest(universe, MINTLIFY, now=CLOSE, seed_dir=SEED, judge=pick(*names))
    return collect_evidence(
        universe, picked, now=CLOSE, seed_dir=SEED, extractor=returning(*facts), **kwargs
    )


def open_obligation(session):
    session.add(
        m.CompanyVendor(
            vendor_id="VEN-MINTLIFY",
            vendor_name="Mintlify",
            vendor_category=e.VendorCategory.SAAS,
            billing_cadence=e.BillingCadence.MONTHLY,
            default_currency="USD",
        )
    )
    session.add(
        m.TrueUpObligation(
            obligation_id="OBL-MINTLIFY-2026-12",
            vendor_id="VEN-MINTLIFY",
            period="2026-12",
            service_start_date=date(2026, 12, 1),
            service_end_date=date(2026, 12, 31),
            purchase_type=e.PurchaseType.USAGE_BASED,
            invoice_status=e.InvoiceStatus.NOT_SEARCHED,
            evidence_status=e.EvidenceStatus.NOT_COLLECTED,
            workflow_stage=e.WorkflowStage.GATHERING_EVIDENCE,
            next_action=e.NextAction.SEARCH_AP,
            accrual_status=e.AccrualStatus.NOT_STARTED,
            risk_level="LOW",
            opened_at=CLOSE,
            updated_at=CLOSE,
        )
    )
    session.flush()


def test_verbatim_fact_is_kept_and_invented_quote_is_dropped(universe):
    invented = fee_fact(key=FactKey.OTHER, quote="the fee doubles to $2,800 in January")
    result = run(universe, [fee_fact(), invented])
    assert [c.value_json["key"] for c in result.cards] == ["MONTHLY_FEE"]
    assert result.cards[0].source_excerpt == QUOTE
    assert result.cards[0].fact == "Monthly fee: $1,400 per month"
    assert [d.reason for d in result.dropped] == ["quote not found in the document"]
    assert any("Dropped OTHER" in u for u in result.uncertainties)
    assert (result.files[0].facts_kept, result.files[0].facts_dropped) == (1, 1)


def test_fact_whose_number_is_not_in_its_quote_is_dropped(universe):
    result = run(universe, [fee_fact(number=Decimal("1500"))])
    assert result.cards == []
    assert result.dropped[0].reason == "number not found in the quote or value text"


def test_fact_whose_value_text_is_not_in_the_document_is_dropped(universe):
    result = run(universe, [fee_fact(value_text="about fourteen hundred a month")])
    assert result.cards == []
    assert result.dropped[0].reason == "value text not found in the document"


def test_date_absent_from_the_document_is_cleared_but_the_fact_is_kept(universe):
    result = run(universe, [fee_fact(date="2031-07-09")])
    assert len(result.cards) == 1
    assert result.cards[0].value_json["date"] is None
    assert any("Cleared date 2031-07-09" in u for u in result.uncertainties)


def test_grounded_date_survives(universe):
    assert run(universe, [fee_fact()]).cards[0].value_json["date"] == "2026-12-01"


def test_number_check_is_numeric_not_textual():
    text = "The fee is $1,600.00 per unit."
    fact = Fact(
        key=FactKey.UNIT_RATE,
        label="Unit price",
        value_text="$1,600.00",
        number=Decimal("1600"),
        quote="The fee is $1,600.00 per unit.",
    )
    assert ungrounded_reason(fact, text) is None


def test_only_selected_files_reach_the_extractor(universe):
    seen: list[str] = []
    picked = ingest(universe, MINTLIFY, now=CLOSE, seed_dir=SEED, judge=pick(AGREEMENT))
    collect_evidence(
        universe, picked, now=CLOSE, seed_dir=SEED, extractor=returning(fee_fact(), seen=seen)
    )
    assert seen == [AGREEMENT]
    assert picked.files_loaded == 10 and len(picked.selected) == 1


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("agreement", e.EvidenceCardType.CONTRACT_TERM),
        ("po", e.EvidenceCardType.PO_DETAIL),
        ("order", e.EvidenceCardType.PO_DETAIL),
        ("usage", e.EvidenceCardType.SERVICE_USAGE),
        ("receipt", e.EvidenceCardType.SERVICE_RECEIPT),
        ("delivery", e.EvidenceCardType.SERVICE_RECEIPT),
        ("invoice", e.EvidenceCardType.INVOICE),
        ("ap", e.EvidenceCardType.AP_SEARCH),
        ("gl", e.EvidenceCardType.GL_HISTORY),
        ("prior", e.EvidenceCardType.GL_HISTORY),
        ("email", e.EvidenceCardType.OUTREACH_RESPONSE),
        ("brief", e.EvidenceCardType.GL_HISTORY),
    ],
)
def test_card_type_follows_the_file_kind(kind, expected):
    assert card_type_for(kind) == expected


def test_cards_carry_decimal_strings_and_no_floats(universe):
    card = run(universe, [fee_fact()]).cards[0]
    assert card.evidence_type == e.EvidenceCardType.CONTRACT_TERM
    assert card.evidence_id == "EVD-MINTLIFY-2026-12-01"
    assert card.source_table == "document" and card.source_id.startswith("FILE-MINTLIFY-")
    assert card.confidence == Decimal("1.00") and card.status == e.EvidenceCardStatus.VERIFIED
    assert card.value_json["number"] == "1400"
    assert all(v is None or isinstance(v, str) for v in card.value_json.values())
    assert "1400.0" not in json.dumps(card.value_json)


def test_cards_are_stored_only_when_an_obligation_exists(universe):
    engine = make_engine()
    create_all(engine)
    with get_session(engine) as session:
        open_obligation(session)
        result = run(universe, [fee_fact()], session=session, obligation_id="OBL-MINTLIFY-2026-12")
    with get_session(engine) as session:
        row = session.scalars(select(m.TrueUpEvidence)).one()
    assert row.evidence_id == result.cards[0].evidence_id
    assert row.obligation_id == "OBL-MINTLIFY-2026-12"
    assert row.value_json["number"] == "1400" and row.confidence == Decimal("1.00")
    assert row.evidence_type == e.EvidenceCardType.CONTRACT_TERM

    other = make_engine()
    create_all(other)
    with get_session(other) as session:
        run(universe, [fee_fact()], session=session)
    with get_session(other) as session:
        assert session.scalars(select(m.TrueUpEvidence)).all() == []


def test_run_is_logged_with_uncertainties(universe):
    engine = make_engine()
    create_all(engine)
    with get_session(engine) as session:
        open_obligation(session)
        result = run(
            universe,
            [fee_fact(), fee_fact(key=FactKey.OTHER, quote="not in the document at all")],
            session=session,
            obligation_id="OBL-MINTLIFY-2026-12",
        )
    with get_session(engine) as session:
        log = session.scalars(select(m.TrueUpAgentRun)).one()
    assert log.agent_name == "evidence" and log.action == "extract_facts"
    assert log.obligation_id == "OBL-MINTLIFY-2026-12"
    assert log.output_record_ids_json == [c.evidence_id for c in result.cards]
    assert len(log.input_record_ids_json) == 1
    assert "1 grounded facts" in log.decision_summary and "dropped 1" in log.decision_summary
    assert any("Dropped OTHER" in u for u in log.uncertainties_json)


def test_run_without_an_obligation_logs_that_nothing_was_stored(universe):
    engine = make_engine()
    create_all(engine)
    with get_session(engine) as session:
        run(universe, [fee_fact()], session=session)
    with get_session(engine) as session:
        log = session.scalars(select(m.TrueUpAgentRun)).one()
    assert log.obligation_id is None and log.output_record_ids_json == []
    assert "not stored" in log.output_summary


def test_a_failing_extraction_is_contained_and_reported(universe):
    def broken(case, entry, text):
        raise llm.LLMError("boom")

    picked = ingest(universe, MINTLIFY, now=CLOSE, seed_dir=SEED, judge=pick(AGREEMENT))
    result = collect_evidence(universe, picked, now=CLOSE, seed_dir=SEED, extractor=broken)
    assert result.cards == []
    assert any("Extraction failed" in u for u in result.uncertainties)


def test_no_model_and_no_extractor_is_a_clear_error(universe):
    picked = ingest(universe, MINTLIFY, now=CLOSE, seed_dir=SEED, judge=pick(AGREEMENT))
    with pytest.raises(EvidenceError, match="No language model"):
        collect_evidence(universe, picked, now=CLOSE, seed_dir=SEED)


def test_llm_extractor_sends_the_document_and_no_answer_key(universe, monkeypatch):
    seen = {}

    def fake_complete_json(prompt, schema, **kwargs):
        seen["prompt"] = prompt
        return DocumentFacts(facts=[fee_fact()])

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    picked = ingest(universe, MINTLIFY, now=CLOSE, seed_dir=SEED, judge=pick(AGREEMENT))
    result = collect_evidence(universe, picked, now=CLOSE, seed_dir=SEED)
    assert result.extractor == "llm_extractor" and len(result.cards) == 1
    prompt = seen["prompt"]
    assert "Mintlify" in prompt and QUOTE in " ".join(prompt.split())
    for leak in ("SUPPORTS_", "HARD_NEGATIVE", "relevance_truth"):
        assert leak not in prompt


def test_ingestion_output_flows_into_evidence_on_the_real_seed(universe):
    picked = ingest(universe, MINTLIFY, now=CLOSE, seed_dir=SEED, judge=ingestion.rule_judge)
    assert picked.selected

    def echo_start_of_document(case, entry, text):
        line = " ".join(text.split())[:60]
        return DocumentFacts(
            facts=[
                Fact(
                    key=FactKey.OTHER,
                    label="Opening line",
                    value_text=line[:20],
                    quote=line,
                )
            ]
        )

    result = collect_evidence(
        universe, picked, now=CLOSE, seed_dir=SEED, extractor=echo_start_of_document
    )
    assert [c.source_id for c in result.cards] == picked.selected
    assert result.dropped == []
    for card in result.cards:
        name = card.value_json["file"]
        path = next(f.path for f in universe.files if f.file_id == card.source_id)
        assert " ".join(read_text(SEED / path).split()).startswith(card.source_excerpt), name


def test_evidence_module_is_wired_to_the_ingest_layer_only():
    source = Path(evidence_agent.__file__).read_text()
    assert "trueup.simulator" not in source
