"""Simulated email threads and the Meta dispute the Controller raises with the vendor.

Nothing here calls a model: the drafts are templates and the vendor's answer is the simulator's
scripted reply. The point is that everything on the thread is read back from the run rows, and that
the dispute reaches its end only through the real gates.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests import service_flow as flow
from trueup.agents import controller_workspace
from trueup.agents import outreach_agent as outreach
from trueup.agents.outreach_agent import DisputeFacts, Draft, DraftFacts, Topic, check_draft
from trueup.service import demo_state as demo
from trueup.service import outreach_threads
from trueup.service.app import create_app
from trueup.store import enums as e
from trueup.verification import checks as checks_module
from trueup.verification import gates, graph
from trueup.verification import states as st

META, OPENAI, ASUS, MINTLIFY, NOTABILITY = (
    f"OBL-{v}-2026-12" for v in ("META", "OPENAI", "ASUS", "MINTLIFY", "NOTABILITY")
)
DISPUTE = "DISPUTE_WITH_VENDOR"


@pytest.fixture
def api():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


@pytest.fixture
def january(api):
    return flow.january(api)


def threads(api, obligation_id):
    response = api.get(f"/api/obligations/{obligation_id}/outreach")
    assert response.status_code == 200, response.text
    return response.json()


def dispute(api, notes="The invoice is above what was delivered", decided_by=None):
    body = {"decision": DISPUTE, "notes": notes}
    if decided_by:
        body["decided_by"] = decided_by
    return api.post(f"/api/controller/{META}/decision", json=body)


def facts(**overrides):
    base = {
        "vendor_name": "Meta",
        "recipient_name": "Sam Ortiz",
        "recipient_role": "VENDOR_BILLING",
        "topic": Topic.INVOICE_DISPUTE,
        "ask": outreach.ASK[Topic.INVOICE_DISPUTE],
        "service_start": datetime(2026, 12, 1).date(),
        "service_end": datetime(2026, 12, 31).date(),
        "received_through": None,
        "reply_by": datetime(2027, 3, 2).date(),
        "dispute": DisputeFacts(
            invoice_number="META-2027-001",
            invoiced_amount=Decimal("30000.00"),
            supported_amount=Decimal("24700.00"),
        ),
    }
    return DraftFacts(**{**base, **overrides})


# ---- a case that needed no email has no thread -----------------------------------------------


def test_a_case_that_needed_no_email_has_no_threads(january):
    assert threads(january, MINTLIFY) == []
    detail = january.get(f"/api/obligations/{MINTLIFY}").json()
    assert detail["outreach_threads"] == []


def test_a_case_that_has_not_run_has_no_threads(api):
    assert threads(api, OPENAI) == []


def test_an_unknown_case_is_a_404(api):
    assert api.get("/api/obligations/OBL-NOPE-2026-12/outreach").status_code == 404


# ---- OpenAI: an internal owner is asked, and answers -----------------------------------------


def test_openai_thread_is_sent_with_a_due_date_then_answered_with_a_parsed_quantity(api):
    api.post("/api/close/run")
    sent = threads(api, OPENAI)
    assert len(sent) == 1
    thread = sent[0]
    assert thread["topic"] == "USAGE_CONFIRMATION" and thread["simulated"] is True
    assert thread["status"] == "SENT" and thread["parsed"] is None
    assert thread["sent_at"].endswith("Z") and thread["due_at"] > thread["sent_at"]
    assert thread["waiting_on"] == {
        "name": "Riley Kim",
        "role": "Engineering Service Owner",
        "kind": "INTERNAL_OWNER",
    }
    (out,) = thread["messages"]
    assert out["direction"] == "OUT" and out["from"]["name"] == "Finance Operations"
    assert out["to"]["name"] == "Riley Kim" and out["method"] == "TEMPLATE"
    assert out["run_id"] is not None and out["evidence_id"].endswith("-REQ-01")
    assert "$" not in out["body"]

    assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 200
    answered = threads(api, OPENAI)[0]
    assert answered["status"] == "REPLIED" and answered["waiting_on"] is None
    assert [m["direction"] for m in answered["messages"]] == ["OUT", "IN"]
    reply = answered["messages"][1]
    assert reply["from"]["name"] == "Riley Kim" and reply["method"] == "SCRIPTED_REPLY"
    assert "930,000 API calls" in reply["body"]
    assert answered["parsed"]["resolved"] is True
    assert answered["parsed"]["facts"] == {"quantity": "930000", "unit": "API_CALL"}
    gate = answered["verification"]
    assert gate is not None and gate["verdict"] == "PERMIT" and gate["total"] == gate["passed"]


def test_the_detail_carries_the_same_threads_as_the_endpoint(january):
    detail = january.get(f"/api/obligations/{OPENAI}").json()
    assert detail["outreach_threads"] == threads(january, OPENAI)


# ---- ASUS: a reply that is not enough is never treated as confirmation -----------------------


def test_asus_reply_is_insufficient_and_goes_to_the_controller(january):
    state = demo.current()
    when = datetime(2027, 1, 31, 13, tzinfo=UTC)
    with state.session() as session:
        controller_workspace.decide(
            session,
            ASUS,
            e.ControllerDecision.REQUEST_MORE_EVIDENCE,
            now=when,
            decided_by=controller_workspace.controller_id(session),
            notes="Ask the owner when the laptops were placed in service.",
        )
        outreach.send_outreach(session, ASUS, now=when, topic=Topic.IN_SERVICE_DATE)
    (waiting,) = threads(january, ASUS)
    assert waiting["status"] == "SENT" and waiting["waiting_on"]["name"] == "Taylor Morgan"

    later = datetime(2027, 2, 1, 12, tzinfo=UTC)
    state.sim.advance_to(later)
    with state.session() as session:
        replies = outreach.poll_replies(
            session,
            now=later,
            responder=lambda key, _at: state.sim.reply_to_outreach(key, session),
        )
    assert [r.resolved for r in replies] == [False]
    (thread,) = threads(january, ASUS)
    assert thread["topic"] == "IN_SERVICE_DATE" and thread["status"] == "INSUFFICIENT"
    assert thread["parsed"]["resolved"] is False and thread["parsed"]["facts"] == {}
    reply = thread["messages"][-1]
    assert reply["direction"] == "IN" and "do not have the exact in-service dates" in reply["body"]
    detail = january.get(f"/api/obligations/{ASUS}").json()
    assert detail["header"]["workflow_stage"] == "AWAITING_CONTROLLER"


# ---- the vendor-facing dispute ---------------------------------------------------------------


def test_only_a_reconciled_source_data_error_can_be_disputed(january):
    allowed = january.get(f"/api/obligations/{META}").json()["verification"]["controller"]
    assert allowed["allowed_decisions"][0] == DISPUTE
    other = january.get(f"/api/obligations/{MINTLIFY}").json()["verification"]["controller"]
    assert DISPUTE not in (other["allowed_decisions"] if other else [])
    refused = january.post(
        f"/api/controller/{MINTLIFY}/decision", json={"decision": DISPUTE, "notes": "no"}
    )
    assert refused.status_code == 409


def test_only_the_controller_can_raise_a_dispute(january):
    refused = dispute(january, decided_by="AP-001")
    assert refused.status_code == 403 and "not the configured controller" in refused.text
    assert threads(january, META) == []
    assert dispute(january).status_code == 200


def test_the_dispute_email_names_the_invoice_and_cites_only_reconciliation_figures(january):
    assert dispute(january).status_code == 200
    (thread,) = threads(january, META)
    assert thread["topic"] == "INVOICE_DISPUTE" and thread["status"] == "SENT"
    assert thread["waiting_on"] == {
        "name": "Sam Ortiz",
        "role": "Ads billing contact, Meta",
        "kind": "VENDOR_CONTACT",
    }
    (out,) = thread["messages"]
    body = out["subject"] + "\n" + out["body"]
    assert "META-2027-001" in body and "30,000.00" in body and "24,700.00" in body
    assert out["to"]["name"] == "Sam Ortiz" and "$" not in body
    figures = set(re.findall(r"\d[\d,]*\.\d{2}", body))
    assert figures == {"30,000.00", "24,700.00"}
    assert thread["due_at"] > thread["sent_at"]


def test_the_vendor_answers_a_corrected_invoice_arrives_and_the_case_closes_at_zero(january):
    dispute(january)
    assert flow.next_action(january, META)["kind"] == "DELIVER_VENDOR_REPLY"
    assert january.post(f"/api/obligations/{META}/deliver-vendor-reply").status_code == 200

    (thread,) = threads(january, META)
    assert thread["status"] == "REPLIED"
    reply = thread["messages"][1]
    assert reply["direction"] == "IN" and reply["from"]["name"] == "Sam Ortiz"
    assert reply["at"] > thread["sent_at"]
    assert thread["parsed"]["facts"] == {"corrected_amount": "24700.00"}
    gate = thread["verification"]
    ids = {c["check_id"] for c in gate["checks"]}
    assert gate["verdict"] == "PERMIT" and {"VER-26", "VER-27"} <= ids

    detail = january.get(f"/api/obligations/{META}").json()
    assert detail["header"]["workflow_stage"] == "CLOSED"
    rec = detail["verification"]["reconciliation"]
    assert rec["actual"] == "24700.00" and rec["variance"] == "0.00"
    assert rec["resolved_dispute"]["original_root_cause"] == "SOURCE_DATA_ERROR"
    assert rec["resolved_dispute"]["original_amount"] == "30000.00"
    assert rec["invoice_ids"] == ["INV-META-CORR-2026-12"]
    assert flow.next_action(january, META) is None


def test_no_reply_before_the_clock_reaches_it_and_no_second_dispute_email(january):
    dispute(january)
    (thread,) = threads(january, META)
    assert thread["status"] == "SENT" and len(thread["messages"]) == 1
    assert january.post(f"/api/obligations/{META}/deliver-vendor-reply").status_code == 200
    assert january.post(f"/api/obligations/{META}/deliver-vendor-reply").status_code == 409
    (again,) = threads(january, META)
    assert [m["direction"] for m in again["messages"]] == ["OUT", "IN"]


def test_the_original_invoice_is_not_matched_again_while_the_correction_is_pending(january):
    dispute(january)
    state = demo.current()
    state.sim.advance_to(datetime(2027, 2, 2, 12, tzinfo=UTC))
    from trueup.agents import reconciliation_agent as recon

    with state.session() as session:
        run = demo.run_for(state, session)
        run.collect_replies(now=datetime(2027, 2, 2, 12, tzinfo=UTC))
        ob = session.get(demo.m.TrueUpObligation, META)
        matches, considered = recon._matching_invoices(
            session, ob, datetime(2027, 2, 2, 12, tzinfo=UTC)
        )
    assert matches == []
    assert {c["decision"] for c in considered} == {"IGNORED_DISPUTED"}


# ---- a reply that does not commit to the supported amount ------------------------------------


def test_a_vendor_reply_for_the_wrong_amount_does_not_resolve_the_dispute(january):
    dispute(january)
    state = demo.current()
    when = datetime(2027, 2, 2, 12, tzinfo=UTC)
    with state.session() as session:
        result = outreach.process_reply(
            session,
            META,
            "We will issue a corrected invoice for 28,000.00 tomorrow.",
            now=when,
        )
    assert not result.resolved and result.corrected_amount == Decimal("28000.00")
    assert result.routed_stage == e.WorkflowStage.AWAITING_CONTROLLER
    (thread,) = threads(january, META)
    assert thread["status"] == "INSUFFICIENT" and thread["parsed"]["resolved"] is False


def test_a_reply_that_commits_to_no_amount_does_not_resolve_it(january):
    dispute(january)
    state = demo.current()
    when = datetime(2027, 2, 2, 12, tzinfo=UTC)
    with state.session() as session:
        result = outreach.process_reply(
            session, META, "Thanks, we are looking into this.", now=when
        )
    assert not result.resolved and result.routed_stage == e.WorkflowStage.AWAITING_CONTROLLER


def test_an_amount_the_reply_does_not_contain_is_dropped(january):
    dispute(january)
    state = demo.current()
    parsed = outreach.ParsedReply(
        resolved=True, corrected_amount=Decimal("24700.00"), reason="model says so"
    )
    with state.session() as session:
        result = outreach.process_reply(
            session,
            META,
            "We will get back to you.",
            now=datetime(2027, 2, 2, 12, tzinfo=UTC),
            parser=lambda reply, topic, units: parsed,
        )
    assert not result.resolved and result.corrected_amount is None
    assert any("not in the reply text" in u for u in result.uncertainties)


# ---- the draft guardrail and different vendors -----------------------------------------------


def test_the_dispute_template_passes_its_own_guardrail():
    f = facts()
    draft = outreach.template_draft(f)
    assert check_draft(draft, f) is None
    assert "30,000.00" in draft.body and "24,700.00" in draft.body


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("Hi Sam, invoice META-2027-001 is for 35,000.00 against 24,700.00.", "35000"),
        ("Hi Sam, invoice META-2027-001 is for 30,000.00 against 24,700.00 plus 500.", "500"),
    ],
)
def test_a_dispute_draft_with_an_unsupplied_figure_is_rejected(body, reason):
    problem = check_draft(Draft(subject="Invoice META-2027-001", body=body), facts())
    assert problem is not None and reason in problem


def test_a_dispute_draft_may_state_the_supplied_figures_with_a_currency_mark():
    draft = Draft(
        subject="Invoice META-2027-001",
        body="Hi Sam, invoice META-2027-001 is for $30,000.00 but the records support $24,700.00.",
    )
    assert check_draft(draft, facts()) is None


def test_two_vendors_get_different_emails_from_their_own_facts(january):
    dispute(january)
    meta = threads(january, META)[0]["messages"][0]
    openai = threads(january, OPENAI)[0]["messages"][0]
    assert meta["body"] != openai["body"]
    assert "Meta" in meta["body"] and "OpenAI" not in meta["body"]
    assert "OpenAI" in openai["body"] and "Meta" not in openai["body"]
    assert meta["to"]["name"] == "Sam Ortiz" and openai["to"]["name"] == "Riley Kim"


def test_a_dispute_needs_a_vendor_contact(january):
    state = demo.current()
    with state.session() as session:
        row = session.get(demo.m.CompanyConfig, "vendor_contacts")
        row.config_value_json = {}
    refused = dispute(january)
    assert refused.status_code == 409 and "nowhere to go" in refused.text


# ---- the new edge in the graph and its gates -------------------------------------------------


def test_the_dispute_edges_have_gates_that_name_real_checks():
    back = gates.EDGE_GATES[(st.OUTREACH, st.WAIT)]
    assert {"VER-26", "VER-27"} <= set(back.checks)
    assert {gates.DRAFTED, gates.ESTIMATED, gates.POLICY_EVALUATED} <= set(back.requires)
    raised = gates.EDGE_GATES[(st.CONTROLLER, st.OUTREACH)]
    assert "VER-25" in raised.checks and raised.by_controller
    assert {"VER-25", "VER-26", "VER-27"} <= set(checks_module.REGISTRY)


def test_the_model_check_still_proves_every_property_with_the_new_edge():
    report = graph.verify_workflow_graph()
    assert report.holds, [(p.key, p.counterexample) for p in report.properties if not p.holds]


def test_the_guard_on_the_new_edge_is_load_bearing():
    unguarded = dict(gates.EDGE_GATES)
    edge = (st.OUTREACH, st.WAIT)
    unguarded[edge] = gates.HandoffGate(edge=edge, checks=unguarded[edge].checks)
    report = graph.verify_workflow_graph(gates=unguarded)
    assert not report.holds
    failed = report.get("policy_before_posting")
    assert (
        not failed.holds and failed.counterexample[-1] == "AWAITING_ACTUAL_INVOICE/WAIT_FOR_INVOICE"
    )


def test_a_dispute_reply_that_is_not_resolved_cannot_pass_the_return_gate(january):
    dispute(january)
    state = demo.current()
    with state.session() as session:
        outreach.process_reply(
            session,
            META,
            "We will issue a corrected invoice for 28,000.00.",
            now=datetime(2027, 2, 2, 12, tzinfo=UTC),
        )
        ob = session.get(demo.m.TrueUpObligation, META)
    assert ob.workflow_stage == e.WorkflowStage.AWAITING_CONTROLLER


# ---- boundaries ------------------------------------------------------------------------------


def test_the_new_code_never_reads_a_hidden_answer_key():
    for module in (outreach_threads, outreach, checks_module):
        source = inspect.getsource(module)
        for forbidden in ("relevance_truth", "historical_truth", "simulator.files"):
            assert forbidden not in source, (module.__name__, forbidden)


# ---- the run log tells the truth about how the email was written and what estimation did ------


def _log(api, obligation_id):
    return api.get(f"/api/obligations/{obligation_id}/log").json()["entries"]


def test_the_outreach_run_is_llm_only_when_the_model_wrote_or_read_the_email():
    from types import SimpleNamespace

    from trueup.service import runlog

    def row(facts):
        return SimpleNamespace(
            agent_name="outreach", facts_used_json=facts, decision_summary="", output_summary=""
        )

    assert runlog._method(row([{"drafted_by": "llm"}])) == "LLM"
    assert runlog._method(row([{"parsed_by": "llm"}])) == "LLM"
    assert runlog._method(row([{"drafted_by": "template"}])) == "CODE"
    assert runlog._method(row([{"parsed_by": "rule"}])) == "CODE"
    assert runlog._method(row(None)) == "CODE"


def test_a_stage_that_produced_no_estimate_says_so_in_the_log(api):
    api.post("/api/close/run")
    openai = [e for e in _log(api, OPENAI) if e["agent"] == "estimation"]
    assert [e["title"] for e in openai] == ["Estimation did not produce an estimate"]
    assert openai[0]["summary"].startswith("No estimate for VEN-OPENAI")
    mintlify = [e for e in _log(api, MINTLIFY) if e["agent"] == "estimation"]
    assert [e["title"] for e in mintlify] == ["Estimation computed the accrual"]


# ---- time is per case: OpenAI's story runs alone ----------------------------------------------


RULE = "LRN-000002"
OTHERS = ("Meta", "Mintlify", "Notability", "ASUS")


def test_openai_runs_alone_from_email_to_graded_and_strands_no_other_case(api):
    assert api.post(f"/api/obligations/{OPENAI}/start").status_code == 200
    assert threads(api, OPENAI)[0]["status"] == "SENT"
    assert flow.next_action(api, OPENAI)["kind"] == "DELIVER_REPLY"

    assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 200
    thread = threads(api, OPENAI)[0]
    assert thread["status"] == "REPLIED" and thread["parsed"]["resolved"] is True
    reply = thread["messages"][1]
    assert reply["at"] == "2027-01-02T10:00:00Z" and "930,000 API calls" in reply["body"]
    flow.rest(api, OPENAI)
    assert flow.cases(api)["OpenAI"]["status"] == "Close-ready"
    assert flow.next_action(api, OPENAI)["kind"] == "BRING_IN_INVOICE"

    assert api.post(f"/api/obligations/{OPENAI}/bring-in-invoice").status_code == 200
    flow.rest(api, OPENAI)
    graded = flow.cases(api)
    assert graded["OpenAI"]["status"] == "Complete"
    for name in OTHERS:
        assert graded[name]["status"] == "Pending" and graded[name]["can_start"] is True

    assert api.post("/api/close/run").status_code == 200
    started = flow.cases(api)
    assert all(started[name]["status"] != "Pending" for name in OTHERS)
    assert started["OpenAI"]["status"] == "Complete"


def test_starting_and_advancing_one_case_never_touches_another(api):
    before = {n: (c["status"], c["stage"], c["workflow_stage"]) for n, c in flow.cases(api).items()}
    api.post(f"/api/obligations/{OPENAI}/start")
    flow.take(api, OPENAI)
    after = flow.cases(api)
    for name in OTHERS:
        assert (after[name]["status"], after[name]["stage"], after[name]["workflow_stage"]) == (
            before[name]
        )
    api.post(f"/api/obligations/{MINTLIFY}/start")
    assert flow.take(api, MINTLIFY) == "BRING_IN_INVOICE"
    assert flow.cases(api)["Mintlify"]["status"] == "Complete"
    assert flow.cases(api)["OpenAI"]["status"] == "Close-ready"
    for name in ("Meta", "Notability", "ASUS"):
        assert flow.cases(api)[name]["status"] == "Pending"


def test_the_reply_changes_openais_number_only_when_the_learned_rule_was_approved(api):
    for approve in (False, True):
        assert api.post("/api/reset").status_code == 200
        if approve:
            assert api.post(f"/api/learning/{RULE}/approve").status_code == 200
        api.post(f"/api/obligations/{OPENAI}/start")
        assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 200
        flow.rest(api, OPENAI)
        expected = "18600.00" if approve else "14880.00"
        assert flow.cases(api)["OpenAI"]["amount"] == expected


def test_each_time_action_refuses_when_it_does_not_apply_to_the_case(api):
    assert api.post(f"/api/obligations/{MINTLIFY}/deliver-reply").status_code == 409
    assert api.post(f"/api/obligations/{MINTLIFY}/bring-in-invoice").status_code == 409
    assert api.post(f"/api/obligations/{MINTLIFY}/deliver-vendor-reply").status_code == 409
    for action in ("deliver-reply", "bring-in-invoice", "deliver-vendor-reply"):
        assert api.post(f"/api/obligations/OBL-NOPE-2026-12/{action}").status_code == 404
    api.post(f"/api/obligations/{OPENAI}/start")
    assert api.post(f"/api/obligations/{OPENAI}/bring-in-invoice").status_code == 409
    assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 200
    assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 409
    flow.rest(api, OPENAI)
    assert api.post(f"/api/obligations/{OPENAI}/bring-in-invoice").status_code == 200
    assert api.post(f"/api/obligations/{OPENAI}/bring-in-invoice").status_code == 409


def test_a_delivered_reply_survives_the_world_being_rebuilt(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    api.post(f"/api/obligations/{OPENAI}/deliver-reply")
    before = threads(api, OPENAI)
    offered = api.get(f"/api/obligations/{MINTLIFY}").json()["ingestion"]["offered"]
    rebuilt = api.put(
        f"/api/obligations/{MINTLIFY}/ingestion-selection",
        json={"excluded_file_ids": [offered[0]["file_id"]]},
    )
    assert rebuilt.status_code == 200, rebuilt.text
    after = threads(api, OPENAI)
    assert after[0]["status"] == before[0]["status"] == "REPLIED"
    assert after[0]["messages"] == before[0]["messages"]


def test_the_log_names_who_the_email_went_to_and_whose_reply_was_read(api):
    api.post(f"/api/obligations/{OPENAI}/start")
    sent = [e for e in _log(api, OPENAI) if e["agent"] == "outreach"]
    assert [e["title"] for e in sent] == ["Outreach sent an email to Riley Kim"]
    api.post(f"/api/obligations/{OPENAI}/deliver-reply")
    titles = [e["title"] for e in _log(api, OPENAI) if e["agent"] == "outreach"]
    assert titles == ["Outreach sent an email to Riley Kim", "Outreach read Riley Kim's reply"]
