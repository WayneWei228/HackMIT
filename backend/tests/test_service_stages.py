"""The stage-by-stage API: nothing exists before the agent that produces it has run.

Covers the advance endpoint, the run log and handoffs read from the run rows, the per-stage checks
composed from records, and the file-removal escalation that re-runs a case without a document.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from trueup.agents.ingestion import FileDecision
from trueup.service import demo_state
from trueup.service.app import create_app
from trueup.store import models as m

MINTLIFY, OPENAI, ASUS, META, NOTABILITY = (
    f"OBL-{v}-2026-12" for v in ("MINTLIFY", "OPENAI", "ASUS", "META", "NOTABILITY")
)
ASUS_NO_RECEIPT = "OBL-ASUS-2026-12-02"
CASES = (MINTLIFY, OPENAI, ASUS, ASUS_NO_RECEIPT, META, NOTABILITY)
RULE = "LRN-000002"
# Kinds of document that carry the facts an estimate stands on. Nothing here names a vendor.
FACT_KINDS = {"agreement", "usage", "po", "receipt", "delivery", "order", "prior", "gl", "invoice"}
STAGE_ORDER = ["Ingestion", "Evidence", "Obligation", "Estimation", "Verification"]


def fact_judge(case, cards):
    """A judge that keeps every document of a fact-bearing kind, so removals have consequences."""
    return [
        FileDecision(
            file_id=c.entry.file_id,
            selected=c.entry.kind in FACT_KINDS
            and not c.entry.file_id.rsplit("-", 1)[-1][0] == "L",
            reason="test judge",
        )
        for c in cards
    ]


@pytest.fixture
def api():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    return client


@pytest.fixture
def api_with_facts(api):
    demo_state.current().judge = fact_judge
    return api


def advance(api, obligation_id):
    response = api.post(f"/api/obligations/{obligation_id}/advance")
    assert response.status_code == 200, response.text
    return response.json()


def drive(api, obligation_id):
    steps = []
    for _ in range(60):
        step = advance(api, obligation_id)
        if step["stage_run"]:
            steps.append(step)
        if step["done"]:
            return steps, step
    raise AssertionError("the case never rested")


def table(api):
    return {
        c["vendor_name"]: (c["status"], c["amount"], c["workflow_stage"])
        for c in api.get("/api/close").json()["cases"]
    }


def floats_in(node):
    if isinstance(node, float):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from floats_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from floats_in(value)


# ---- one stage at a time -------------------------------------------------------------------------


def test_a_case_that_has_not_run_has_an_empty_log_and_no_handoffs(api):
    log = api.get(f"/api/obligations/{ASUS}/log").json()
    handoffs = api.get(f"/api/obligations/{ASUS}/handoffs").json()
    assert log["entries"] == [] and handoffs["handoffs"] == []
    header = api.get(f"/api/obligations/{ASUS}").json()["header"]
    assert (header["status"], header["stages_completed"], header["log_count"]) == ("Pending", [], 0)
    assert header["current_agent"] == "invoice_lookup"


@pytest.mark.parametrize("obligation_id", [MINTLIFY, ASUS])
def test_each_advance_runs_one_agent_and_only_that_stage_appears(api, obligation_id):
    agents, seen_logs, seen_handoffs = [], 0, 0
    reading = False
    while True:
        step = advance(api, obligation_id)
        case, run = step["case"], step["stage_run"]
        header = case["header"]
        if run:
            reading = run["partial"]
            agents.append(run["agent"])
            assert run["duration_ms"] >= 0
            assert run["log_seqs"] == list(range(seen_logs + 1, header["log_count"] + 1))
            assert run["handoff_seqs"] == list(
                range(seen_handoffs + 1, header["handoff_count"] + 1)
            )
            seen_logs, seen_handoffs = header["log_count"], header["handoff_count"]
        ran = set(agents)
        assert (header["supported"] is not None) == ("estimation" in ran)
        assert case["estimation"]["available"] == ("estimation" in ran)
        assert case["verification"]["available"] == ("policy" in ran)
        assert case["evidence"]["available"] == ("evidence" in ran)
        assert case["ingestion"]["available"] == ("ingestion" in ran)
        assert case["obligation"]["available"] == ("classification" in ran)
        expected = [
            s
            for s, need in zip(
                STAGE_ORDER,
                (
                    {"invoice_lookup", "ingestion"},
                    {"evidence"},
                    {"classification"},
                    {"estimation"},
                    {"policy"},
                ),
                strict=True,
            )
            if need <= ran and not (s == "Evidence" and reading)
        ]
        assert header["stages_completed"] == expected
        if step["done"]:
            break
        assert header["current_agent"]
    turns = [agent for i, agent in enumerate(agents) if i == 0 or agents[i - 1] != agent]
    assert turns[:6] == [
        "invoice_lookup",
        "ingestion",
        "evidence",
        "classification",
        "estimation",
        "policy",
    ]
    assert header["status"] in ("Close-ready", "Needs review")
    again = advance(api, obligation_id)
    assert again["done"] is True and again["stage_run"] is None


def test_a_resting_status_needs_the_stage_that_produces_it(api):
    seen: dict[str, list[str]] = {}
    for _ in range(20):
        step = advance(api, NOTABILITY)
        ran = step["stage_run"]["agent"] if step["stage_run"] else None
        seen.setdefault(step["case"]["header"]["status"], []).append(ran)
        if step["done"]:
            break
    assert list(seen) == ["Running", "Needs review"]
    assert seen["Needs review"][0] == "policy" and "policy" not in seen["Running"]
    case = api.get(f"/api/obligations/{NOTABILITY}").json()
    fired = [c["check_id"] for c in case["verification"]["stage_checks"] if c["status"] == "FLAG"]
    assert "POL-01" in fired


def test_advancing_stage_by_stage_ends_where_start_all_ends(api):
    for obligation_id in CASES:
        drive(api, obligation_id)
    stepwise = table(api)
    assert api.post("/api/reset").status_code == 200
    assert api.post("/api/close/run").status_code == 200
    assert table(api) == stepwise


def test_the_learned_rule_still_changes_openai_when_approved_before_estimation(api):
    api.post(f"/api/learning/{RULE}/approve")
    for _ in range(3):
        advance(api, OPENAI)
    assert api.get(f"/api/obligations/{OPENAI}").json()["header"]["supported"] is None
    drive(api, OPENAI)
    assert api.post(f"/api/obligations/{OPENAI}/deliver-reply").status_code == 200
    drive(api, OPENAI)
    assert table(api)["OpenAI"][1] == "18600.00"


# ---- the run log and the handoffs ----------------------------------------------------------------


def test_the_log_is_the_run_rows_including_verifier_and_reviewer(api):
    drive(api, ASUS)
    entries = api.get(f"/api/obligations/{ASUS}/log").json()["entries"]
    kinds = Counter(e["kind"] for e in entries)
    assert kinds["VERIFICATION"] >= 6 and kinds["REVIEW"] == 1 and kinds["AGENT"] >= 6
    state = demo_state.current()
    with state.session() as session:
        rows = {r.run_id: r for r in session.scalars(select(m.TrueUpAgentRun))}
    for entry in entries:
        row = rows[entry["run_ref"]]
        assert entry["run_id"] == int(entry["run_ref"].rsplit("-", 1)[-1])
        assert entry["summary"] == row.decision_summary and entry["agent"] == row.agent_name
    assert [e["seq"] for e in entries] == list(range(1, len(entries) + 1))
    gates = [e for e in entries if e["verification"]]
    assert all(e["kind"] == "VERIFICATION" and e["method"] == "CODE" for e in gates)
    assert all(e["verification"]["passed"] <= e["verification"]["total"] for e in gates)
    policy = next(e for e in entries if e["agent"] == "policy")
    assert {r["rule_id"] for r in policy["detail"]["rules"]} >= {"POL-01", "POL-07"}
    assert [r["rule_id"] for r in policy["detail"]["rules"] if r["fired"]] == ["POL-01"]
    evidence = [e for e in entries if e["agent"] == "evidence"]
    sources = [s for e in evidence for s in e["detail"]["sources"]]
    assert sources and all(s["quote"] for s in sources)
    assert len(evidence) == 2  # Evidence reads one document per turn
    assert {s["file_name"] for s in sources} == {
        "goods_receipt_use-asus-2026-12-18.pdf",
        "po_asus_laptops.pdf",
    }
    assert all(e["method"] == "CODE" and "rule_extractor" in e["summary"] for e in evidence)
    assert all(e["detail"]["duration_ms"] is not None for e in entries[1:])


def test_handoffs_carry_the_typed_json_and_the_gate_result_between_agents(api):
    drive(api, ASUS)
    handoffs = api.get(f"/api/obligations/{ASUS}/handoffs").json()["handoffs"]
    edges = [(h["from_agent"], h["to_agent"]) for h in handoffs]
    assert edges == [
        ("detection", "invoice_lookup"),
        ("invoice_lookup", "ingestion"),
        ("ingestion", "evidence"),
        ("evidence", "classification"),
        ("classification", "estimation"),
        ("estimation", "policy"),
        ("policy", "controller_workspace"),
    ]
    assert [h["seq"] for h in handoffs] == list(range(1, 8))
    workpaper = next(h for h in handoffs if h["payload_kind"] == "Workpaper")
    assert workpaper["payload"]["record"]["amount"] == "32000.00"
    assert workpaper["payload"]["proposal"]["amount"] == "32000.00"
    assert workpaper["verification"]["verdict"] == "PERMIT"
    assert workpaper["record_ids"] and workpaper["run_ref"].startswith("RUN-")
    selection = next(h for h in handoffs if h["payload_kind"] == "IngestionResult")
    assert selection["verification"] is None
    assert not list(floats_in(json.loads(json.dumps(handoffs))))
    cards = next(h for h in handoffs if h["payload_kind"] == "EvidenceCards")
    assert cards["record_ids"] == [c["evidence_id"] for c in cards["payload"]["record"]["cards"]]


def test_two_vendors_get_different_stage_checks_from_their_own_documents(api):
    for obligation_id in (MINTLIFY, NOTABILITY):
        drive(api, obligation_id)
    mint = api.get(f"/api/obligations/{MINTLIFY}").json()
    note = api.get(f"/api/obligations/{NOTABILITY}").json()
    ids = lambda case, screen: {c["check_id"] for c in case[screen]["stage_checks"]}  # noqa: E731
    assert "OBL-AMEND" in ids(mint, "obligation") and "OBL-DEFER" in ids(note, "obligation")
    assert "OBL-DEFER" not in ids(mint, "obligation") and "OBL-AMEND" not in ids(note, "obligation")
    bodies = {c["check_id"]: c["body"] for c in mint["obligation"]["stage_checks"]}
    assert "$1,400" in bodies["OBL-AMEND"] and "December 1, 2026" in bodies["OBL-AMEND"]
    assert (
        "21600" in note["estimation"]["stage_checks"][0]["body"]
        or "1,800" in (note["estimation"]["stage_checks"][0]["body"])
    )
    for case, name in ((mint, "MINTLIFY"), (note, "NOTABILITY")):
        sources = {
            s["file_id"]
            for entry in api.get(f"/api/obligations/{'OBL-' + name + '-2026-12'}/log").json()[
                "entries"
            ]
            for s in entry["detail"]["sources"]
        }
        assert sources and all(f"-{name}-" in i for i in sources)
        received = case["evidence"]["received"]
        assert received["counts"]["files_selected"] == case["ingestion"]["selected_count"]
    handoffs = api.get(f"/api/obligations/{MINTLIFY}/handoffs").json()["handoffs"]
    cards = next(h for h in handoffs if h["payload_kind"] == "EvidenceCards")["payload"]["record"]
    received = mint["obligation"]["received"]
    assert received["counts"]["facts"] == len(cards["cards"])
    assert received["counts"]["files"] == len({c["source_id"] for c in cards["cards"]})
    assert received["handoff_seq"] == next(
        h["seq"] for h in handoffs if h["payload_kind"] == "EvidenceCards"
    )


def test_usage_and_receipt_vendors_show_their_own_checks(api):
    for obligation_id in (OPENAI, ASUS, META):
        drive(api, obligation_id)
    got = {
        o: {
            c["check_id"]
            for c in api.get(f"/api/obligations/{o}").json()["obligation"]["stage_checks"]
        }
        for o in (OPENAI, ASUS, META)
    }
    assert "OBL-USAGE" in got[OPENAI] and "OBL-RECEIPT" in got[ASUS] and "OBL-DELIVERY" in got[META]
    assert not got[OPENAI] & {"OBL-RECEIPT", "OBL-DELIVERY"}


def test_the_controller_is_named_rudraksh_awasthi(api):
    close = api.get("/api/close").json()
    assert close["controller_name"] == "Rudraksh Awasthi"
    assert {p["name"] for p in close["people"] if p["role"] == "Controller"} == {"Rudraksh Awasthi"}


# ---- one evidence card per fact ------------------------------------------------------------------


def no_repeated_facts(api):
    for obligation_id in CASES:
        cards = api.get(f"/api/obligations/{obligation_id}").json()["evidence"]["facts"]
        keys = Counter((c["label"], c["value"], c["file_id"]) for c in cards)
        assert not [k for k, n in keys.items() if n > 1], (obligation_id, keys)
    state = demo_state.current()
    with state.session() as session:
        rows = session.scalars(
            select(m.TrueUpEvidence).where(m.TrueUpEvidence.source_table == "document")
        )
        stored = Counter((r.obligation_id, r.fact, r.source_id) for r in rows)
    assert not [k for k, n in stored.items() if n > 1]


def test_no_obligation_repeats_a_fact_before_or_after_a_regather_or_a_file_change(api_with_facts):
    api = api_with_facts
    for obligation_id in CASES:
        drive(api, obligation_id)
    no_repeated_facts(api)
    note = api.get(f"/api/obligations/{NOTABILITY}").json()["evidence"]["facts"]
    assert sum(1 for f in note if f["key"] == "TREATMENT") == 1

    decided = api.post(
        f"/api/controller/{NOTABILITY}/decision",
        json={"decision": "REQUEST_MORE_EVIDENCE", "notes": "look again"},
    )
    assert decided.status_code == 200
    drive(api, NOTABILITY)
    no_repeated_facts(api)

    changed = api.put(
        f"/api/obligations/{MINTLIFY}/ingestion-selection",
        json={"excluded_file_ids": ["FILE-MINTLIFY-03"]},
    )
    assert changed.status_code == 200
    drive(api, MINTLIFY)
    no_repeated_facts(api)


# ---- taking files out escalates ------------------------------------------------------------------

# The document that carried what the estimate stood on, and where the case must go without it.
WITHOUT = [
    (OPENAI, "FILE-OPENAI-08", "usage report", "OUTREACH"),
    (OPENAI, "FILE-OPENAI-02", "contract rate", "CONTROLLER"),
    (MINTLIFY, "FILE-MINTLIFY-05", "monthly fee", "CONTROLLER"),
    (ASUS, "FILE-ASUS-03", "goods receipt", "OUTREACH"),
    (ASUS, "FILE-ASUS-08", "purchase order price", "CONTROLLER"),
    (META, "FILE-META-01", "campaign delivery report", "OUTREACH"),
    (NOTABILITY, "FILE-NOTABILITY-05", "amortization schedule", "CONTROLLER"),
]


@pytest.mark.parametrize(("obligation_id", "file_id", "missing", "routed"), WITHOUT)
def test_removing_the_document_an_estimate_stands_on_escalates_instead_of_guessing(
    api_with_facts, obligation_id, file_id, missing, routed
):
    api = api_with_facts
    for _ in range(2):
        advance(api, obligation_id)
    changed = api.put(
        f"/api/obligations/{obligation_id}/ingestion-selection",
        json={"excluded_file_ids": [file_id]},
    )
    assert changed.status_code == 200
    detail = changed.json()
    gone = [f for f in detail["ingestion"]["files"] if f["user_removed"]]
    assert [f["file_id"] for f in gone] == [file_id] and not any(f["selected"] for f in gone)
    assert detail["header"]["stages_completed"] == ["Ingestion"]
    assert detail["evidence"]["available"] is False

    _, last = drive(api, obligation_id)
    case = last["case"]
    assert case["header"]["supported"] is None and case["estimation"]["available"] is False
    assert case["escalation"]["reason"] == "INSUFFICIENT_INFORMATION"
    assert missing in case["escalation"]["missing"] and case["escalation"]["routed_to"] == routed
    assert missing in case["escalation"]["message"]
    assert api.get(f"/api/obligations/{obligation_id}").json()["escalation"] == case["escalation"]
    stop = next(c for c in case["estimation"]["stage_checks"] if c["check_id"] == "EST-STOP")
    assert missing in stop["body"] and stop["status"] == "FLAG"

    entries = api.get(f"/api/obligations/{obligation_id}/log").json()["entries"]
    override = next(e for e in entries if e["kind"] == "HUMAN_OVERRIDE")
    assert override["method"] == "HUMAN" and override["detail"]["output_ids"] == [file_id]
    assert "demo user" in override["summary"] and override["detail"]["sources"]
    assert entries.index(override) > next(
        i for i, e in enumerate(entries) if e["agent"] == "ingestion"
    )


def test_removing_a_file_nothing_depends_on_changes_nothing(api_with_facts):
    api = api_with_facts
    drive(api, MINTLIFY)
    baseline = api.get(f"/api/obligations/{MINTLIFY}").json()["header"]["supported"]
    assert baseline == "1400.00"
    api.put(
        f"/api/obligations/{MINTLIFY}/ingestion-selection",
        json={"excluded_file_ids": ["FILE-MINTLIFY-03"]},
    )
    _, last = drive(api, MINTLIFY)
    assert last["case"]["header"]["supported"] == baseline
    assert last["case"]["escalation"] is None and last["case"]["header"]["status"] == "Close-ready"


def test_putting_the_file_back_returns_the_original_answer(api_with_facts):
    api = api_with_facts
    drive(api, ASUS)
    original = api.get(f"/api/obligations/{ASUS}").json()
    api.put(
        f"/api/obligations/{ASUS}/ingestion-selection",
        json={"excluded_file_ids": ["FILE-ASUS-03"]},
    )
    _, escalated = drive(api, ASUS)
    assert escalated["case"]["escalation"] is not None
    restored = api.put(
        f"/api/obligations/{ASUS}/ingestion-selection", json={"excluded_file_ids": []}
    )
    assert restored.status_code == 200 and not any(
        f["user_removed"] for f in restored.json()["ingestion"]["files"]
    )
    _, last = drive(api, ASUS)
    case = last["case"]
    assert case["escalation"] is None
    assert case["header"]["supported"] == original["header"]["supported"] == "32000.00"
    assert case["header"]["status"] == original["header"]["status"] == "Needs review"
    assert case["evidence"]["facts"] == original["evidence"]["facts"]


def test_the_log_and_the_stage_checks_change_when_the_input_changes(api_with_facts):
    api = api_with_facts
    drive(api, ASUS)
    before_log = api.get(f"/api/obligations/{ASUS}/log").json()["entries"]
    before = api.get(f"/api/obligations/{ASUS}").json()
    api.put(
        f"/api/obligations/{ASUS}/ingestion-selection",
        json={"excluded_file_ids": ["FILE-ASUS-03"]},
    )
    drive(api, ASUS)
    after_log = api.get(f"/api/obligations/{ASUS}/log").json()["entries"]
    after = api.get(f"/api/obligations/{ASUS}").json()
    assert [e["agent"] for e in after_log] != [e["agent"] for e in before_log]
    evidence_before = next(e for e in before_log if e["agent"] == "evidence")
    evidence_after = next(e for e in after_log if e["agent"] == "evidence")
    assert len(evidence_after["detail"]["sources"]) < len(evidence_before["detail"]["sources"])
    grounded = lambda case: next(  # noqa: E731
        c["body"] for c in case["evidence"]["stage_checks"] if c["check_id"] == "EVI-GROUND"
    )
    assert grounded(before) != grounded(after)
    assert before["evidence"]["received"]["counts"] != after["evidence"]["received"]["counts"]
    handoffs = api.get(f"/api/obligations/{ASUS}/handoffs").json()["handoffs"]
    cards = next(h for h in handoffs if h["payload_kind"] == "EvidenceCards")
    assert all(c["source_id"] != "FILE-ASUS-03" for c in cards["payload"]["record"]["cards"])


def test_an_unknown_file_is_refused_and_a_change_is_replayed_around_other_cases(api_with_facts):
    api = api_with_facts
    refused = api.put(
        f"/api/obligations/{ASUS}/ingestion-selection", json={"excluded_file_ids": ["FILE-NOPE"]}
    )
    assert refused.status_code == 422
    assert (
        api.put(
            "/api/obligations/OBL-NOPE/ingestion-selection", json={"excluded_file_ids": []}
        ).status_code
        == 404
    )
    drive(api, MINTLIFY)
    drive(api, NOTABILITY)
    api.put(
        f"/api/obligations/{ASUS}/ingestion-selection",
        json={"excluded_file_ids": ["FILE-ASUS-03"]},
    )
    cases = table(api)
    assert cases["Mintlify"][0] == "Close-ready" and cases["Notability"][0] == "Needs review"
    assert cases["ASUS"][0] == "Pending"


def test_the_live_judge_records_whether_the_model_or_the_rules_picked_the_files(monkeypatch):
    from trueup.agents import ingestion
    from trueup.gateway import llm

    picked = [FileDecision(file_id="F-1", selected=True, reason="model")]
    fallback = [FileDecision(file_id="F-1", selected=False, reason="rules")]
    monkeypatch.setattr(ingestion, "rule_judge", lambda case, cards: fallback)

    judge = ingestion.ModelOrRulesJudge()
    monkeypatch.setattr(ingestion, "llm_judge", lambda case, cards: picked)
    assert judge(None, []) == picked
    assert judge.__name__ == "llm_judge"

    def refuse(case, cards):
        raise llm.LLMError("model unavailable")

    monkeypatch.setattr(ingestion, "llm_judge", refuse)
    assert judge(None, []) == fallback
    assert "llm_judge" not in judge.__name__ and "rule_judge" in judge.__name__


@pytest.mark.parametrize("obligation_id", CASES)
def test_a_case_that_has_not_run_lists_the_files_it_will_read_but_judges_none(api, obligation_id):
    ingestion = api.get(f"/api/obligations/{obligation_id}").json()["ingestion"]
    assert ingestion["available"] is False
    assert ingestion["files"] == [] and ingestion["selected_count"] == 0
    offered = ingestion["offered"]
    count = 9 if obligation_id == ASUS_NO_RECEIPT else 10
    assert len(offered) == count
    assert {"file_id", "name", "kind", "format", "size_label", "preview"} == set(offered[0])
    assert all(f["preview"] for f in offered)
    assert len({f["file_id"] for f in offered}) == count

    advance(api, obligation_id)
    advance(api, obligation_id)
    after = api.get(f"/api/obligations/{obligation_id}").json()["ingestion"]
    assert after["available"] is True
    assert [f["file_id"] for f in after["files"]] == [f["file_id"] for f in offered]
    assert after["offered"] == offered


def test_evidence_reads_one_document_per_turn_and_shows_each_documents_facts_as_it_returns(api):
    advance(api, ASUS)  # invoice lookup
    after_ingestion = advance(api, ASUS)["case"]
    assert after_ingestion["header"]["current_agent"] == "evidence"
    documents = after_ingestion["evidence"]["documents"]
    assert len(documents) == 2 and all(any(d["pages"]) for d in documents)
    assert (
        after_ingestion["evidence"]["facts"] == []
        and after_ingestion["evidence"]["read_files"] == []
    )

    first = advance(api, ASUS)
    assert first["stage_run"]["agent"] == "evidence" and first["stage_run"]["partial"] is True
    assert first["done"] is False
    case = first["case"]
    assert case["header"]["workflow_stage"] == "GATHERING_EVIDENCE"
    assert "Evidence" not in case["header"]["stages_completed"]
    assert case["header"]["current_agent"] == "evidence"
    read = case["evidence"]["read_files"]
    assert len(read) == 1 and {f["file_id"] for f in case["evidence"]["facts"]} == set(read)

    second = advance(api, ASUS)
    assert second["stage_run"]["agent"] == "evidence" and second["stage_run"]["partial"] is False
    case = second["case"]
    assert "Evidence" in case["header"]["stages_completed"]
    assert case["header"]["workflow_stage"] != "GATHERING_EVIDENCE"
    assert set(case["evidence"]["read_files"]) == {d["file_id"] for d in documents}
    assert {f["file_id"] for f in case["evidence"]["facts"]} == set(case["evidence"]["read_files"])
    assert advance(api, ASUS)["stage_run"]["agent"] == "classification"


def test_evidence_reads_every_selected_document_before_the_case_moves_on(api_with_facts):
    api = api_with_facts
    advance(api, MINTLIFY)
    advance(api, MINTLIFY)
    documents = api.get(f"/api/obligations/{MINTLIFY}").json()["evidence"]["documents"]
    assert documents
    turns = 0
    while True:
        step = advance(api, MINTLIFY)
        turns += 1
        if step["stage_run"]["agent"] != "evidence" or not step["stage_run"]["partial"]:
            break
    read = api.get(f"/api/obligations/{MINTLIFY}").json()["evidence"]["read_files"]
    assert set(read) == {d["file_id"] for d in documents} and turns >= 1


def test_a_stage_shows_what_it_received_before_its_own_agent_has_run(api):
    advance(api, MINTLIFY)  # invoice lookup
    case = advance(api, MINTLIFY)["case"]  # ingestion
    evidence = case["evidence"]
    assert evidence["received"]["from_agent"] == "ingestion"
    assert evidence["received"]["counts"]["files_selected"] == len(evidence["documents"])
    assert evidence["available"] is False and not evidence["stage_checks"]
    assert case["obligation"]["received"] is None and case["estimation"]["received"] is None

    while advance(api, MINTLIFY)["stage_run"]["agent"] == "evidence":
        pass
    case = api.get(f"/api/obligations/{MINTLIFY}").json()
    assert case["obligation"]["received"]["from_agent"] == "evidence"
    assert case["obligation"]["available"] is True
    assert case["estimation"]["received"]["from_agent"] == "classification"
    assert case["estimation"]["available"] is False and case["header"]["supported"] is None
