from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select

from tests.support import open_obligation
from trueup.agents import outreach_agent as outreach
from trueup.agents.classification_agent import classify
from trueup.agents.estimation_agent import estimate
from trueup.agents.outreach_agent import (
    Draft,
    OutreachError,
    ParsedReply,
    Topic,
    check_draft,
    expire_overdue,
    poll_replies,
    process_reply,
    send_outreach,
    template_draft,
)
from trueup.agents.policy_agent import enforce
from trueup.gateway import llm
from trueup.learning.testing import activate_escalator_rule
from trueup.simulator import generator
from trueup.simulator.simulator import Simulator
from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.workflow import IllegalTransitionError, advance

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
CLOSE = "2026-12-31T23:59:00Z"
OPENAI_REPLY_AT = "2027-01-02T10:00:00Z"
ASUS_REPLY_AT = "2027-01-04T10:00:00Z"
PERIOD = "2026-12"
OPENAI_KEY = "OPENAI-2026-12-USAGE_CONFIRMATION"
ASUS_KEY = "ASUS-2026-12-IN_SERVICE_DATE"
SEARCH = (e.WorkflowStage.SEARCHING_AP, e.NextAction.SEARCH_AP)
OUTREACH_STATE = (e.WorkflowStage.AWAITING_OUTREACH, e.NextAction.SEND_OUTREACH)
ESTIMATE_STATE = (e.WorkflowStage.ESTIMATING, e.NextAction.ESTIMATE)
CONTROLLER = (e.WorkflowStage.AWAITING_CONTROLLER, e.NextAction.CONTROLLER_REVIEW)
S = e.EvidenceStatus


@pytest.fixture(scope="module")
def world():
    return generator.generate(generator.DEFAULT_SEED)


@pytest.fixture
def sim(world):
    simulator = Simulator.from_world(world)
    simulator.advance_to(CLOSE)
    return simulator


@pytest.fixture
def session(sim):
    with sim.session() as s:
        yield s


def clone(session, row, **overrides):
    columns = {a.key: getattr(row, a.key) for a in inspect(row).mapper.column_attrs}
    new = type(row)(**{**columns, **overrides})
    session.add(new)
    session.flush()
    return new


def clone_usage_vendor(session, new_id, name):
    clone(session, session.get(m.CompanyVendor, "VEN-OPENAI"), vendor_id=new_id, vendor_name=name)
    rows = session.scalars(
        select(m.CompanyServiceEvidence).where(m.CompanyServiceEvidence.vendor_id == "VEN-OPENAI")
    ).all()
    for i, row in enumerate(rows):
        clone(
            session,
            row,
            service_evidence_id=f"{new_id}-S{i}",
            vendor_id=new_id,
            po_id=None,
            contract_id=None,
        )


def at_outreach(session, vendor_id, status=None):
    obligation = open_obligation(session, vendor_id, PERIOD, now=NOW, to=SEARCH)
    if status is not None:
        obligation.evidence_status = status
    advance(obligation, *OUTREACH_STATE, "test", at=NOW)
    return obligation


def runs(session, action=None):
    query = select(m.TrueUpAgentRun).where(m.TrueUpAgentRun.agent_name == "outreach")
    if action:
        query = query.where(m.TrueUpAgentRun.action == action)
    return list(session.scalars(query.order_by(m.TrueUpAgentRun.run_id)))


def cards(session):
    return list(
        session.scalars(
            select(m.TrueUpEvidence)
            .where(m.TrueUpEvidence.source_table == "outreach")
            .order_by(m.TrueUpEvidence.evidence_id)
        )
    )


def no_floats(value):
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(no_floats(v) for v in value.values())
    if isinstance(value, list):
        return all(no_floats(v) for v in value)
    return True


def fixed_parser(**fields):
    return lambda reply, topic, units: ParsedReply(**fields)


# --- sending ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "topic", "person"),
    [
        (S.MISSING_USAGE, Topic.USAGE_CONFIRMATION, "ENG-001"),
        (S.MISSING_SERVICE_CONFIRMATION, Topic.SERVICE_CONFIRMATION, "ENG-001"),
        (S.MISSING_RATE, Topic.RATE_CONFIRMATION, "PROC-001"),
    ],
)
def test_topic_and_recipient_come_from_state_and_config(session, status, topic, person):
    obligation = at_outreach(session, "VEN-OPENAI", status)
    sent = send_outreach(session, obligation.obligation_id, now=NOW)
    assert sent.topic == topic
    assert sent.recipient_person_id == person
    assert sent.outreach_key == f"OPENAI-2026-12-{topic.value}"
    assert sent.recipient_email and sent.recipient_email.endswith("@northstar.example")


def test_explicit_topic_overrides_status_and_uses_the_service_owner(session):
    obligation = at_outreach(session, "VEN-ASUS", S.SUFFICIENT)
    sent = send_outreach(session, obligation.obligation_id, now=NOW, topic="IN_SERVICE_DATE")
    assert sent.outreach_key == ASUS_KEY
    assert sent.recipient_person_id == "OPS-001"


def test_no_topic_and_no_missing_status_raises(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.SUFFICIENT)
    with pytest.raises(OutreachError):
        send_outreach(session, obligation.obligation_id, now=NOW)


def test_recipient_is_read_from_the_config_map(session):
    row = session.get(m.CompanyConfig, "ownership_map")
    value = {**row.config_value_json}
    value["vendors"] = {
        **value["vendors"],
        "VEN-OPENAI": {**value["vendors"]["VEN-OPENAI"], "service_owner_id": "MKT-001"},
    }
    row.config_value_json = value
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    assert send_outreach(session, obligation.obligation_id, now=NOW).recipient_person_id == (
        "MKT-001"
    )


def test_unseen_vendor_maps_by_structure_and_falls_back_to_the_default_owner(session):
    clone_usage_vendor(session, "VEN-VEGAAI", "Vega AI")
    clone_usage_vendor(session, "VEN-NOVAAI", "Nova AI")
    row = session.get(m.CompanyConfig, "ownership_map")
    value = {**row.config_value_json}
    value["vendors"] = {
        **value["vendors"],
        "VEN-VEGAAI": {"service_owner_id": "OPS-001", "procurement_owner_id": "PROC-001"},
    }
    row.config_value_json = value

    mapped = send_outreach(
        session, at_outreach(session, "VEN-VEGAAI", S.MISSING_USAGE).obligation_id, now=NOW
    )
    assert (mapped.outreach_key, mapped.recipient_person_id) == (
        "VEGAAI-2026-12-USAGE_CONFIRMATION",
        "OPS-001",
    )
    assert "Vega AI" in mapped.body

    fallback_obligation = at_outreach(session, "VEN-NOVAAI", S.MISSING_USAGE)
    fallback = send_outreach(session, fallback_obligation.obligation_id, now=NOW)
    assert fallback.recipient_person_id == "AP-001"
    assert any(
        "default AP owner" in u for u in runs(session, "send_outreach")[-1].uncertainties_json
    )


def test_send_persists_a_pending_request_card_with_a_deadline(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    sent = send_outreach(session, obligation.obligation_id, now=NOW)
    (card,) = cards(session)
    assert card.evidence_id == f"EVD-OUT-{OPENAI_KEY}-REQ-01"
    assert card.evidence_type == e.EvidenceCardType.OUTREACH_RESPONSE
    assert card.status == e.EvidenceCardStatus.PENDING
    assert (card.source_table, card.source_id) == ("outreach", OPENAI_KEY)
    assert card.value_json["direction"] == "REQUEST"
    assert card.value_json["topic"] == "USAGE_CONFIRMATION"
    assert sent.due_at == NOW + timedelta(days=outreach.DEFAULT_DEADLINE_DAYS)
    assert card.value_json["due_at"] == sent.due_at.isoformat()
    assert card.source_excerpt == sent.body
    assert (obligation.workflow_stage, obligation.next_action) == OUTREACH_STATE
    assert no_floats(card.value_json)


def test_deadline_days_can_come_from_config(session):
    session.add(
        m.CompanyConfig(config_key="outreach_deadline_days", config_value_json=2, updated_at=NOW)
    )
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    assert send_outreach(session, obligation.obligation_id, now=NOW).due_at == NOW + timedelta(
        days=2
    )


def test_sending_twice_is_idempotent(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    first = send_outreach(session, obligation.obligation_id, now=NOW)
    second = send_outreach(session, obligation.obligation_id, now=NOW + timedelta(hours=1))
    assert (first.created, second.created) == (True, False)
    assert second.evidence_id == first.evidence_id
    assert len(cards(session)) == 1
    assert len(runs(session, "send_outreach")) == 1


def test_no_model_uses_the_template_and_says_so(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    sent = send_outreach(session, obligation.obligation_id, now=NOW)
    assert sent.drafted_by == "template"
    assert "Hi Riley" in sent.body and "December 19, 2026" in sent.body
    notes = runs(session, "send_outreach")[0].uncertainties_json
    assert any("No language model" in n for n in notes)


@pytest.mark.parametrize("topic", [t for t in Topic if t not in outreach.TO_VENDOR])
def test_every_template_passes_its_own_guardrail(session, topic):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    sent = send_outreach(session, obligation.obligation_id, now=NOW, topic=topic)
    facts = outreach._draft_facts(
        session, obligation, topic, {"name": "Riley Kim", "role_label": "SERVICE_OWNER"}, NOW
    )
    assert check_draft(template_draft(facts), facts) is None
    assert "$" not in sent.body


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("Hi Riley, is the bill about $18,600 for December 2026?", "currency"),
        ("Hi Riley, please send the total in USD for December 2026.", "currency"),
        ("Hi Riley, we expect 31000 calls for December 2026.", "number"),
    ],
)
def test_a_draft_that_breaks_the_guardrail_is_replaced_by_the_template(session, body, reason):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    sent = send_outreach(
        session,
        obligation.obligation_id,
        now=NOW,
        drafter=lambda facts: Draft(subject="Usage", body=body),
    )
    assert sent.drafted_by == "template"
    assert body not in sent.body
    notes = runs(session, "send_outreach")[0].uncertainties_json
    assert any("rejected" in n and reason in n for n in notes)


def test_a_clean_custom_draft_is_sent_as_written(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    body = "Hi Riley, could you send the usage total for December 2026? Thanks."
    sent = send_outreach(
        session,
        obligation.obligation_id,
        now=NOW,
        drafter=lambda facts: Draft(subject="December usage", body=body),
    )
    assert (sent.drafted_by, sent.body) == ("custom", body)


def test_a_failing_model_falls_back_to_the_template(session):
    def broken(facts):
        raise llm.LLMError("boom")

    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    sent = send_outreach(session, obligation.obligation_id, now=NOW, drafter=broken)
    assert sent.drafted_by == "template"
    assert any("failed" in n for n in runs(session, "send_outreach")[0].uncertainties_json)


def test_the_default_drafter_uses_the_model_when_configured(session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen = {}

    def fake(prompt, schema, **_):
        seen["prompt"] = prompt
        return Draft(subject="December usage", body="Hi Riley, could you send the total? Thanks.")

    monkeypatch.setattr(llm, "complete_json", fake)
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    sent = send_outreach(session, obligation.obligation_id, now=NOW)
    assert sent.drafted_by == "llm"
    assert "December 19, 2026" in seen["prompt"] and "$" not in seen["prompt"]


# --- replies ---------------------------------------------------------------------------------


def sent_openai(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    send_outreach(session, obligation.obligation_id, now=NOW)
    return obligation


REPLY = "Riley here. The full December export is in: 930,000 API calls for December 1 through 31."


def test_a_verbatim_quantity_is_kept_and_routes_back_to_estimation(session):
    obligation = sent_openai(session)
    parser = fixed_parser(resolved=True, quantity=Decimal("930000"), unit="API_CALL")
    result = process_reply(session, obligation.obligation_id, REPLY, now=NOW, parser=parser)
    assert (result.resolved, result.quantity, result.unit) == (True, Decimal("930000"), "API_CALL")
    assert (result.routed_stage, result.next_action) == ESTIMATE_STATE
    assert (obligation.workflow_stage, obligation.next_action) == ESTIMATE_STATE
    assert obligation.assigned_agent == "outreach"


def test_an_invented_quantity_is_dropped_and_goes_to_the_controller(session):
    obligation = sent_openai(session)
    parser = fixed_parser(resolved=True, quantity=Decimal("777000"), unit="API_CALL")
    result = process_reply(session, obligation.obligation_id, REPLY, now=NOW, parser=parser)
    assert (result.resolved, result.quantity) == (False, None)
    assert (result.routed_stage, result.next_action) == CONTROLLER
    assert any("not in the reply text" in u for u in result.uncertainties)


def test_an_unknown_unit_is_dropped_but_the_grounded_quantity_stays(session):
    obligation = sent_openai(session)
    parser = fixed_parser(resolved=True, quantity=Decimal("930000"), unit="widgets")
    result = process_reply(session, obligation.obligation_id, REPLY, now=NOW, parser=parser)
    assert (result.resolved, result.quantity, result.unit) == (True, Decimal("930000"), None)


def test_dates_are_grounded_in_the_reply_text(session):
    obligation = at_outreach(session, "VEN-ASUS", S.SUFFICIENT)
    send_outreach(session, obligation.obligation_id, now=NOW, topic=Topic.IN_SERVICE_DATE)
    good = process_reply(
        session,
        obligation.obligation_id,
        "They went live on December 19 for the new team.",
        now=NOW,
        parser=fixed_parser(resolved=True, in_service_date="2026-12-19"),
    )
    assert (good.resolved, good.in_service_date) == (True, date(2026, 12, 19))

    other = at_outreach(session, "VEN-META", S.SUFFICIENT)
    send_outreach(session, other.obligation_id, now=NOW, topic=Topic.IN_SERVICE_DATE)
    bad = process_reply(
        session,
        other.obligation_id,
        "They went live on December 19 for the new team.",
        now=NOW,
        parser=fixed_parser(resolved=True, in_service_date="2026-12-24"),
    )
    assert (bad.resolved, bad.in_service_date) == (False, None)
    assert (bad.routed_stage, bad.next_action) == CONTROLLER


def test_a_service_not_received_reply_goes_to_the_controller(session):
    obligation = at_outreach(session, "VEN-ASUS", S.MISSING_SERVICE_CONFIRMATION)
    send_outreach(session, obligation.obligation_id, now=NOW)
    result = process_reply(
        session,
        obligation.obligation_id,
        "Nothing has arrived yet.",
        now=NOW,
        parser=fixed_parser(resolved=True, service_received=False),
    )
    assert result.resolved and result.service_received is False
    assert (result.routed_stage, result.next_action) == CONTROLLER
    assert any("not received" in u for u in result.uncertainties)


def test_the_reply_becomes_a_verified_card_and_the_request_is_superseded(session):
    obligation = sent_openai(session)
    parser = fixed_parser(resolved=True, quantity=Decimal("930000"), unit="API_CALL")
    result = process_reply(session, obligation.obligation_id, REPLY, now=NOW, parser=parser)
    request, response = cards(session)
    assert request.status == e.EvidenceCardStatus.SUPERSEDED
    assert request.value_json["closed_reason"] == "ANSWERED"
    assert response.evidence_id == result.evidence_id == f"EVD-OUT-{OPENAI_KEY}-RSP-01"
    assert response.status == e.EvidenceCardStatus.VERIFIED
    assert response.fact == "Owner reply to USAGE_CONFIRMATION: 930000 API_CALL"
    assert response.source_excerpt == REPLY
    assert response.value_json["quantity"] == "930000"
    assert no_floats(response.value_json)


def test_an_unresolved_reply_leaves_an_unverified_card(session):
    obligation = sent_openai(session)
    process_reply(
        session,
        obligation.obligation_id,
        "Not sure yet, will check.",
        now=NOW,
        parser=fixed_parser(resolved=False, reason="No numbers given."),
    )
    response = cards(session)[-1]
    assert response.status == e.EvidenceCardStatus.PENDING
    assert response.value_json["resolved"] is False
    assert response.confidence == Decimal("0.00")


def test_default_reader_falls_back_to_rules_without_a_model(session):
    obligation = sent_openai(session)
    result = process_reply(session, obligation.obligation_id, REPLY, now=NOW)
    assert (result.parsed_by, result.resolved) == ("rules", True)
    assert (result.quantity, result.unit) == (Decimal("930000"), "API_CALL")


def test_default_reader_uses_the_model_when_configured(session, monkeypatch):
    replies = {
        ParsedReply: ParsedReply(resolved=True, quantity=Decimal("930000"), unit="API_CALL"),
        Draft: Draft(subject="December usage", body="Hi Riley, could you send the total? Thanks."),
    }
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete_json", lambda prompt, schema, **_: replies[schema])
    obligation = sent_openai(session)
    assert process_reply(session, obligation.obligation_id, REPLY, now=NOW).parsed_by == "llm"


def test_a_model_error_falls_back_to_rules(session, monkeypatch):
    def broken(prompt, schema, **_):
        raise llm.LLMError("boom")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete_json", broken)
    obligation = sent_openai(session)
    result = process_reply(session, obligation.obligation_id, REPLY, now=NOW)
    assert (result.parsed_by, result.resolved) == ("rules", True)
    assert any("offline reader" in u for u in result.uncertainties)


def test_replying_without_an_open_request_raises(session):
    obligation = at_outreach(session, "VEN-OPENAI", S.MISSING_USAGE)
    with pytest.raises(OutreachError):
        process_reply(session, obligation.obligation_id, REPLY, now=NOW)


def test_wrong_stage_raises(session):
    obligation = open_obligation(session, "VEN-OPENAI", PERIOD, now=NOW)
    with pytest.raises(IllegalTransitionError):
        send_outreach(session, obligation.obligation_id, now=NOW, topic=Topic.USAGE_CONFIRMATION)
    with pytest.raises(IllegalTransitionError):
        process_reply(session, obligation.obligation_id, REPLY, now=NOW)
    with pytest.raises(LookupError):
        send_outreach(session, "OBL-NOPE", now=NOW)


# --- expiry ----------------------------------------------------------------------------------


def test_overdue_requests_are_escalated_to_the_controller(session):
    obligation = sent_openai(session)
    assert expire_overdue(session, now=NOW + timedelta(days=4)) == []
    expired = expire_overdue(session, now=NOW + timedelta(days=5))
    assert [x.outreach_key for x in expired] == [OPENAI_KEY]
    assert expired[0].routed_stage == e.WorkflowStage.AWAITING_CONTROLLER
    assert (obligation.workflow_stage, obligation.next_action) == CONTROLLER
    (request,) = cards(session)
    assert request.status == e.EvidenceCardStatus.SUPERSEDED
    assert request.value_json["closed_reason"] == "EXPIRED"
    assert expire_overdue(session, now=NOW + timedelta(days=9)) == []
    assert runs(session, "expire_request")[0].status == e.AgentRunStatus.ESCALATED


def test_expiry_of_an_obligation_that_moved_on_only_supersedes_the_card(session):
    obligation = sent_openai(session)
    advance(obligation, *ESTIMATE_STATE, "test", at=NOW)
    (expired,) = expire_overdue(session, now=NOW + timedelta(days=6))
    assert expired.routed_stage is None
    assert (obligation.workflow_stage, obligation.next_action) == ESTIMATE_STATE


# --- the simulator side ----------------------------------------------------------------------


def test_the_reply_is_gated_by_the_clock_and_inserts_its_evidence_once(sim, session):
    assert sim.reply_to_outreach(OPENAI_KEY) is None
    assert sim.reply_to_outreach("NOPE-KEY") is None
    sim.advance_to(OPENAI_REPLY_AT)
    text = sim.reply_to_outreach(OPENAI_KEY)
    assert text and "930,000 API calls" in text
    assert sim.reply_to_outreach(OPENAI_KEY) == text
    assert sim.reply_to_outreach(OPENAI_KEY, session) == text
    rows = session.scalars(
        select(m.CompanyServiceEvidence).where(
            m.CompanyServiceEvidence.service_evidence_id == "USE-OPENAI-2026-12-CONFIRMED"
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].quantity == Decimal("930000")


def test_a_reply_without_evidence_inserts_nothing(sim, session):
    before = session.scalars(select(m.CompanyServiceEvidence)).all()
    sim.advance_to(ASUS_REPLY_AT)
    assert "in-service dates" in sim.reply_to_outreach(ASUS_KEY)
    assert len(session.scalars(select(m.CompanyServiceEvidence)).all()) == len(before)


def test_the_hidden_truth_never_reaches_an_agent_visible_row(sim, session):
    sent_openai(session)
    sim.advance_to(OPENAI_REPLY_AT)
    poll_replies(session, now=NOW, responder=lambda key, now: sim.reply_to_outreach(key, session))
    blob = str([c.value_json for c in cards(session)]) + str(
        [r.facts_used_json for r in runs(session)]
    )
    assert "parsed_truth" not in blob and "INSUFFICIENT_RESPONSE" not in blob


# --- the real fixtures -----------------------------------------------------------------------


def test_the_openai_fixture_reply_matches_the_hidden_truth(sim, session, world):
    truth = {o.outreach_key: o.parsed_truth for o in world.outreach}[OPENAI_KEY]
    obligation = sent_openai(session)
    sim.advance_to(OPENAI_REPLY_AT)
    text = sim.reply_to_outreach(OPENAI_KEY, session)
    result = process_reply(session, obligation.obligation_id, text, now=NOW)
    assert result.resolved is truth["resolved"]
    assert result.quantity == Decimal(truth["quantity"])
    assert result.unit == truth["unit"]
    assert result.service_received is None or result.service_received is truth["service_received"]


def test_the_asus_fixture_reply_is_unresolved_and_goes_to_the_controller(sim, session, world):
    truth = {o.outreach_key: o.parsed_truth for o in world.outreach}[ASUS_KEY]
    obligation = at_outreach(session, "VEN-ASUS", S.SUFFICIENT)
    send_outreach(session, obligation.obligation_id, now=NOW, topic=Topic.IN_SERVICE_DATE)
    sim.advance_to(ASUS_REPLY_AT)
    text = sim.reply_to_outreach(ASUS_KEY, session)
    result = process_reply(session, obligation.obligation_id, text, now=NOW)
    assert result.resolved is truth["resolved"] is False
    assert (result.routed_stage, result.next_action) == CONTROLLER
    assert result.in_service_date is None


def test_polling_processes_a_reply_once_it_has_arrived(sim, session):
    obligation = sent_openai(session)

    def responder(key, now):
        return sim.reply_to_outreach(key, session)

    assert poll_replies(session, now=NOW, responder=responder) == []
    sim.advance_to(OPENAI_REPLY_AT)
    (result,) = poll_replies(session, now=NOW, responder=responder)
    assert result.obligation_id == obligation.obligation_id
    assert poll_replies(session, now=NOW, responder=responder) == []


def test_openai_end_to_end_partial_usage_outreach_reply_estimate_permit(sim, session):
    obligation = open_obligation(session, "VEN-OPENAI", PERIOD, now=NOW)
    classify(session, obligation.obligation_id, now=NOW)
    first = estimate(session, obligation.obligation_id, now=NOW)
    assert first.outcome == "NEEDS_OUTREACH" and first.amount is None
    assert obligation.evidence_status == S.MISSING_USAGE

    sent = send_outreach(session, obligation.obligation_id, now=NOW)
    assert sent.topic == Topic.USAGE_CONFIRMATION
    sim.advance_to(OPENAI_REPLY_AT)
    reply_at = datetime(2027, 1, 2, 10, tzinfo=UTC)
    (reply,) = poll_replies(
        session, now=reply_at, responder=lambda key, now: sim.reply_to_outreach(key, session)
    )
    assert (reply.routed_stage, reply.next_action) == ESTIMATE_STATE

    activate_escalator_rule(session, now=reply_at)
    second = estimate(session, obligation.obligation_id, now=reply_at)
    assert (second.outcome, second.amount) == ("ESTIMATED", Decimal("18600.00"))
    assert obligation.evidence_status == S.SUFFICIENT
    policy = enforce(session, obligation.obligation_id, now=reply_at)
    assert policy.decision == e.PolicyDecision.PERMIT


# --- the run log -----------------------------------------------------------------------------


def test_every_action_is_logged(session):
    obligation = sent_openai(session)
    process_reply(
        session,
        obligation.obligation_id,
        REPLY,
        now=NOW,
        parser=fixed_parser(resolved=True, quantity=Decimal("930000"), unit="API_CALL"),
    )
    other = at_outreach(session, "VEN-ASUS", S.MISSING_SERVICE_CONFIRMATION)
    send_outreach(session, other.obligation_id, now=NOW)
    expire_overdue(session, now=NOW + timedelta(days=6))

    by_action = {r.action: r for r in runs(session)}
    assert set(by_action) == {"send_outreach", "process_reply", "expire_request"}
    send = runs(session, "send_outreach")[0]
    assert send.obligation_id == obligation.obligation_id
    assert send.output_record_ids_json == [f"EVD-OUT-{OPENAI_KEY}-REQ-01"]
    reply = by_action["process_reply"]
    assert reply.status == e.AgentRunStatus.COMPLETED
    assert reply.input_record_ids_json == [f"EVD-OUT-{OPENAI_KEY}-REQ-01"]
    assert reply.output_record_ids_json == [f"EVD-OUT-{OPENAI_KEY}-RSP-01"]
    for run in runs(session):
        assert run.decision_summary and no_floats(run.facts_used_json)
