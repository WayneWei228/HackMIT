from trueup.agents import classifier
from trueup.db import POHeader, POLine, get_session
from trueup.gateway import jev
from trueup.schemas import Classification


def _classify(engine, line_id, **kwargs):
    with get_session(engine) as s:
        return classifier.classify_line(s, line_id, **kwargs)


def test_rules_cover_the_four_fee_patterns(world):
    expected = {
        "PO-2026-1001-001": ("fixed", "recurring"),  # Mintlify
        "PO-2026-1002-001": ("dynamic", "recurring"),  # OpenAI
        "PO-2026-1003-001": ("fixed", "one_time"),  # ASUS
        "PO-2026-1004-001": ("dynamic", "one_time"),  # Meta
    }
    for line_id, (amount_type, cadence) in expected.items():
        result = _classify(world, line_id)
        assert (result.final.amount_type, result.final.cadence) == (amount_type, cadence), line_id
        assert not result.needs_human


def test_jev_disagreement_flags_a_human_and_suggests_a_value(world, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")

    def fake(state, questions):
        return {
            "amount_type": jev.JevAnswer(choice="dynamic", confidence=0.95, probabilities={}),
            "cadence": jev.JevAnswer(choice="recurring", confidence=0.95, probabilities={}),
        }

    monkeypatch.setattr(jev, "classify", fake)
    result = _classify(world, "PO-2026-1001-001")  # rules say fixed
    assert result.needs_human and not result.agreed
    assert result.final == Classification(amount_type="fixed", cadence="recurring")
    assert result.suggested == Classification(amount_type="dynamic", cadence="recurring")


def test_low_confidence_disagreement_flags_but_does_not_suggest(world, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    monkeypatch.setattr(
        jev,
        "classify",
        lambda state, questions: {
            "amount_type": jev.JevAnswer(choice="dynamic", confidence=0.4, probabilities={}),
            "cadence": jev.JevAnswer(choice="recurring", confidence=0.9, probabilities={}),
        },
    )
    result = _classify(world, "PO-2026-1001-001")
    assert result.needs_human and result.suggested is None


def test_jev_result_is_cached_by_row_hash(world, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    calls = []

    def fake(state, questions):
        calls.append(state)
        return {
            "amount_type": jev.JevAnswer(choice="fixed", confidence=0.9, probabilities={}),
            "cadence": jev.JevAnswer(choice="recurring", confidence=0.9, probabilities={}),
        }

    monkeypatch.setattr(jev, "classify", fake)
    _classify(world, "PO-2026-1001-001")
    _classify(world, "PO-2026-1001-001")
    assert len(calls) == 1
    with get_session(world) as s:
        s.get(POLine, "PO-2026-1001-001").line_description = "changed text"
    _classify(world, "PO-2026-1001-001")
    assert len(calls) == 2


def test_jev_outage_falls_back_to_rules(world, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")

    def boom(state, questions):
        raise jev.JevError("down")

    monkeypatch.setattr(jev, "classify", boom)
    result = _classify(world, "PO-2026-1003-001")
    assert result.jev is None and not result.needs_human


def test_contradictory_columns_are_caught_without_any_model(world):
    with get_session(world) as s:
        line = s.get(POLine, "PO-2026-1002-001")
        header = s.get(POHeader, line.po_number)
        line.valid_from = None
        line.valid_to = None
        found = classifier.find_contradictions(header, line)
    assert "blanket item category has no validity dates" in found
    assert "framework order has no validity dates" in found


def test_columns_say_fixed_but_description_says_usage(world, monkeypatch):
    """Twilio-style trap from the startup-output branch: clean columns, usage-based description."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    with get_session(world) as s:
        s.add(
            POHeader(
                po_number="PO-2026-1005",
                vendor_id="V-TWIL",
                order_type="NB",
                created_date="2026-11-01",
                status="Open",
                total_amount_cents=500_000,
            )
        )
        s.add(
            POLine(
                po_line_id="PO-2026-1005-001",
                po_number="PO-2026-1005",
                item_category="",
                gl_account_code="610400",
                quantity_ordered=1,
                unit_price_cents=500_000,
                quantity_received=1,
                quantity_billed=0,
                line_description="Monthly SMS usage charges billed per message sent",
            )
        )

    def fake(state, questions):
        return {
            "amount_type": jev.JevAnswer(choice="dynamic", confidence=0.92, probabilities={}),
            "cadence": jev.JevAnswer(choice="recurring", confidence=0.9, probabilities={}),
        }

    monkeypatch.setattr(jev, "classify", fake)
    result = _classify(world, "PO-2026-1005-001")
    assert result.final == Classification(amount_type="fixed", cadence="one_time")
    assert result.needs_human and not result.contradictions
    assert result.suggested == Classification(amount_type="dynamic", cadence="recurring")
