"""Foundations: periods, time-gated reads, state files, the case machine, gates, math, Jev."""

from __future__ import annotations

import pytest
from typesafe_sdk import Choice, Noul, Score, SystemOneResponse
from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, TypeSafeError, Usage

from close import case, events, jev, policy, safe_math, store, workspace
from close.tests.fakes import AS_OF, FakeJev, FakeLLM, make_ws, write_world


# ---- periods -------------------------------------------------------------


def test_period_bounds_and_days():
    assert workspace.period_bounds("2026-12") == ("2026-12-01", "2026-12-31")
    assert workspace.period_bounds("2026-02") == ("2026-02-01", "2026-02-28")
    assert workspace.period_bounds("2028-02") == ("2028-02-01", "2028-02-29")
    assert workspace.days_in("2026-12") == 31
    assert workspace.days_in("2026-02") == 28


def test_prev_periods_crosses_the_year():
    assert workspace.prev_periods("2026-12", 3) == ["2026-09", "2026-10", "2026-11"]
    assert workspace.prev_periods("2026-01", 2) == ["2025-11", "2025-12"]
    assert workspace.prev_periods("2026-12", 0) == []


def test_covers_treats_a_none_bound_as_open_ended():
    assert workspace.covers("2026-01-01", "2026-12-31", "2026-12")
    assert workspace.covers("2026-12-15", None, "2026-12")
    assert workspace.covers(None, "2026-12-01", "2026-12")
    assert workspace.covers(None, None, "2026-12")
    assert not workspace.covers(None, "2026-11-30", "2026-12")
    assert not workspace.covers("2027-01-01", None, "2026-12")


def test_overlap_days():
    assert workspace.overlap_days("2026-12-01", "2026-12-31", "2026-12") == 31
    assert workspace.overlap_days("2026-12-01", "2026-12-25", "2026-12") == 25
    assert workspace.overlap_days("2026-11-01", "2027-01-31", "2026-12") == 31
    assert workspace.overlap_days(None, "2026-12-10", "2026-12") == 10
    assert workspace.overlap_days("2026-12-10", None, "2026-12") == 22
    assert workspace.overlap_days("2027-01-01", "2027-01-31", "2026-12") == 0


# ---- store ---------------------------------------------------------------


def test_visible_hides_the_future_and_normalises_bare_dates():
    rows = [
        {"id": "always"},
        {"id": "bare-past", "available_at": "2026-12-31"},
        {"id": "bare-today", "available_at": "2027-01-05"},
        {"id": "past", "available_at": "2027-01-05T11:59:59Z"},
        {"id": "future", "available_at": "2027-01-06T00:00:00Z"},
        {"id": "null", "available_at": None},
    ]
    seen = [r["id"] for r in store.visible(rows, AS_OF)]
    assert seen == ["always", "bare-past", "bare-today", "past", "null"]


def test_world_filters_and_world_raw_does_not(tmp_path):
    ws = make_ws(tmp_path)
    write_world(ws, "invoices", [
        {"invoice_id": "INV-1", "available_at": "2026-12-20T00:00:00Z"},
        {"invoice_id": "INV-2", "available_at": "2027-02-01T00:00:00Z"},
    ])
    assert [r["invoice_id"] for r in store.world(ws, "invoices")] == ["INV-1"]
    assert len(store.world_raw(ws, "invoices")) == 2
    assert store.world(ws, "nothing_here") == []
    assert store.company(ws) == {}


def test_company_and_nested_world_names(tmp_path):
    ws = make_ws(tmp_path)
    write_world(ws, "company", {"entity_id": "ORBIT-US", "materiality": 5000})
    write_world(ws, "documents/index", [{"doc_id": "DOC-1", "file": "DOC-1.txt"}])
    assert store.company(ws)["materiality"] == 5000
    assert store.world(ws, "documents/index")[0]["doc_id"] == "DOC-1"


def test_upsert_replaces_on_key_else_appends():
    rows = [{"po_line_id": "A", "v": 1}, {"po_line_id": "B", "v": 2}]
    store.upsert(rows, {"po_line_id": "A", "v": 9}, ("po_line_id",))
    store.upsert(rows, {"po_line_id": "C", "v": 3}, ("po_line_id",))
    assert rows == [{"po_line_id": "A", "v": 9}, {"po_line_id": "B", "v": 2}, {"po_line_id": "C", "v": 3}]


def test_table_and_state_round_trip(tmp_path):
    ws = make_ws(tmp_path)
    assert store.load_table(ws, "contracts") == []
    store.save_table(ws, "contracts", [{"contract_id": "C-1", "amount": 1400.0}])
    assert store.load_table(ws, "contracts") == [{"contract_id": "C-1", "amount": 1400.0}]
    assert store.load_state(ws, "rules", {"rules": []}) == {"rules": []}
    store.save_state(ws, "rules", {"rules": ["R-1"]})
    assert store.load_state(ws, "rules", {}) == {"rules": ["R-1"]}


# ---- events --------------------------------------------------------------


def test_events_append_and_read(tmp_path):
    ws = make_ws(tmp_path)
    assert events.read(ws) == []
    events.log(ws, "evidence", "extracted DOC-1", "2026-12")
    events.log(ws, "detection", "3 cases")
    lines = events.read(ws)
    assert [e["worker"] for e in lines] == ["evidence", "detection"]
    assert lines[0] == {"at": AS_OF, "worker": "evidence", "period": "2026-12", "message": "extracted DOC-1"}
    assert lines[1]["period"] is None


# ---- cases ---------------------------------------------------------------


def a_case(ws, status="DETECTED"):
    c = case.new_case(
        ws,
        period="2026-12",
        kind="PO_LINE",
        case_key="PO-002-001",
        vendor_id="V002",
        vendor_name="OpenAI",
        entity_id="ORBIT-US",
        obligation={"source_type": "PO", "recognition_basis": "USAGE"},
        po_line_id="PO-002-001",
    )
    c["status"] = status
    return c


def test_new_case_shape(tmp_path):
    c = a_case(make_ws(tmp_path))
    assert c["case_id"] == "2026-12/PO-002-001"
    assert c["as_of"] == AS_OF and c["status"] == "DETECTED"
    for key in ("invoice_match", "classification", "estimate", "outreach", "journal", "settlement"):
        assert c[key] is None
    assert c["flags"] == [] and c["evidence_refs"] == [] and c["decision_log"] == []


def test_every_legal_transition_is_allowed(tmp_path):
    ws = make_ws(tmp_path)
    assert set(case.TRANSITIONS) == set(case.STATUSES)
    for old, allowed in case.TRANSITIONS.items():
        for new in allowed:
            c = a_case(ws, old)
            case.transition(ws, c, new, "engine", "walking the machine")
            assert c["status"] == new


@pytest.mark.parametrize(
    "old,new",
    [
        ("DETECTED", "JOURNALED"),
        ("ENRICHED", "CLOSED"),
        ("ESTIMATED", "SETTLED"),
        ("OUTREACH_PENDING", "ESTIMATED"),
        ("CLOSED", "REVIEW"),
        ("LEARNED", "CLOSED"),
        ("DETECTED", "NOT_A_STATUS"),
    ],
)
def test_illegal_transitions_raise(tmp_path, old, new):
    ws = make_ws(tmp_path)
    c = a_case(ws, old)
    with pytest.raises(case.IllegalTransition):
        case.transition(ws, c, new, "engine", "should not happen")
    assert c["status"] == old


def test_transition_writes_a_decision_and_an_event(tmp_path):
    ws = make_ws(tmp_path)
    c = a_case(ws, "DETECTED")
    case.transition(ws, c, "ENRICHED", "engine", "lookup and classification done")
    entry = c["decision_log"][-1]
    assert entry["kind"] == "RULE" and entry["worker"] == "engine"
    assert entry["answer"] == "ENRICHED" and entry["action"] == "DETECTED -> ENRICHED"
    assert entry["at"] == AS_OF
    assert "DETECTED -> ENRICHED" in events.read(ws)[-1]["message"]


def test_log_decision_and_flags(tmp_path):
    ws = make_ws(tmp_path)
    c = a_case(ws)
    case.log_decision(ws, c, "classifier", "JEV", "which category?", "RECURRING_VARIABLE", 0.86, "flag CONTRADICTION")
    entry = c["decision_log"][-1]
    assert entry["kind"] == "JEV" and entry["confidence"] == 0.86
    case.add_flag(c, "CONTRADICTION")
    case.add_flag(c, "CONTRADICTION")
    case.add_flag(c, "DATA_MISMATCH")
    assert c["flags"] == ["CONTRADICTION", "DATA_MISMATCH"]


def test_cases_round_trip(tmp_path):
    ws = make_ws(tmp_path)
    assert case.load_cases(ws) == []
    older = a_case(ws)
    older["period"], older["case_id"] = "2026-11", "2026-11/PO-002-001"
    case.save_cases(ws, [a_case(ws), older])
    assert [c["case_id"] for c in case.cases_for(ws, "2026-12")] == ["2026-12/PO-002-001"]
    assert case.find_case(case.load_cases(ws), "2026-11/PO-002-001")["period"] == "2026-11"
    assert case.find_case(case.load_cases(ws), "nope") is None


# ---- policy --------------------------------------------------------------


def test_gate():
    assert policy.gate(0.95) == "ACT"
    assert policy.gate(policy.ACT) == "ACT"
    assert policy.gate(0.7) == "VERIFY"
    assert policy.gate(policy.CAUTION) == "VERIFY"
    assert policy.gate(0.2) == "REVIEW"
    assert policy.gate(None) == "REVIEW"


def test_gate_promotes_material_amounts_to_review():
    assert policy.gate(0.7, amount=4999.0, materiality=5000.0) == "VERIFY"
    assert policy.gate(0.7, amount=5000.0, materiality=5000.0) == "REVIEW"
    assert policy.gate(0.95, amount=50000.0, materiality=5000.0) == "ACT"
    assert policy.gate(0.7, amount=50000.0, materiality=None) == "VERIFY"


# ---- safe_math -----------------------------------------------------------


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("700000 / 25 * 31 * 0.02", 17360.0),
        ("$1,400.00", 1400.0),
        ("(14200 + 16800 + 15500) / 3", 15500.0),
        ("20 * 1600", 32000.0),
        ("-2500 + 3000", 500.0),
    ],
)
def test_safe_math_evaluates_arithmetic(expression, expected):
    assert safe_math.evaluate(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    ["2 ** 10", "__import__('os').system('ls')", "amount * 2", "abs(-3)", "1 if True else 2", "", "1 / 0", "[1,2]"],
)
def test_safe_math_rejects_everything_else(expression):
    with pytest.raises(ValueError):
        safe_math.evaluate(expression)


# ---- jev -----------------------------------------------------------------

CHOICE_Q = Choice(
    instructions="Which category best describes `po_line.line_description`?",
    criteria={"RECURRING_VARIABLE": "billed every period, amount varies", "ONE_TIME_FIXED": None, "OTHER": None},
)
NOUL_Q = Noul(instructions="Is the amount in `document.text` supported by `record.amount`?")
SCORE_Q = Score(
    instructions="How sufficient is the evidence for a defensible estimate?",
    criteria=["no evidence at all", "partial period covered", "the whole period covered"],
)
QUESTIONS = {"category": CHOICE_Q, "supported": NOUL_Q, "sufficiency": SCORE_Q}


def a_response():
    return SystemOneResponse(
        model="jev-latest",
        usage=Usage(input_tokens=100, output_tokens=10),
        answers={
            "category": ChoiceAnswer(
                choice="RECURRING_VARIABLE",
                confidence=0.86,
                probabilities={"RECURRING_VARIABLE": 0.86, "ONE_TIME_FIXED": 0.1, "OTHER": 0.04},
            ),
            "supported": NoulAnswer(noul=0.93),
            "sufficiency": ScoreAnswer(
                score=0.86,
                confidence=0.71,
                legend={0: "no evidence at all", 1: "partial period covered", 2: "the whole period covered"},
                probabilities={0: 0.2, 1: 0.74, 2: 0.06},
            ),
        },
    )


def test_normalise_choice():
    answer = jev.normalise(a_response().answers["category"], CHOICE_Q)
    assert answer == {
        "type": "choice",
        "choice": "RECURRING_VARIABLE",
        "confidence": 0.86,
        "probabilities": {"RECURRING_VARIABLE": 0.86, "ONE_TIME_FIXED": 0.1, "OTHER": 0.04},
    }


def test_normalise_noul():
    assert jev.normalise(a_response().answers["supported"], NOUL_Q) == {"type": "noul", "noul": 0.93}


def test_normalise_score_is_zero_to_one_with_string_keys():
    answer = jev.normalise(a_response().answers["sufficiency"], SCORE_Q)
    assert answer["type"] == "score"
    assert answer["score"] == pytest.approx(0.43)  # 0.86 over len(criteria) - 1
    assert answer["confidence"] == 0.71
    assert answer["probabilities"] == {"0": 0.2, "1": 0.74, "2": 0.06}


def test_dump_questions_is_json_serialisable():
    dumped = jev.dump_questions(QUESTIONS)
    assert dumped["category"]["type"] == "choice"
    assert "RECURRING_VARIABLE" in dumped["category"]["criteria"]
    assert dumped["sufficiency"]["criteria"][0] == "no evidence at all"


class StubClient:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls = []

    def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return self.response


def test_typesafe_jev_normalises_and_logs_the_call(tmp_path):
    ws = make_ws(tmp_path)
    client = StubClient(response=a_response())
    answers = jev.TypeSafeJev(ws, client=client).ask({"po_line": {"x": 1}}, QUESTIONS, tag="classifier")
    assert set(answers) == {"category", "supported", "sufficiency"}
    assert answers["category"]["choice"] == "RECURRING_VARIABLE"
    assert len(client.calls) == 1
    logged = jev.read_calls(ws)
    assert len(logged) == 1
    assert logged[0]["tag"] == "classifier" and logged[0]["at"] == AS_OF
    assert logged[0]["state_hash"] == jev.state_hash({"po_line": {"x": 1}})
    assert logged[0]["answers"]["supported"]["noul"] == 0.93
    assert logged[0]["questions"]["category"]["type"] == "choice"
    assert isinstance(logged[0]["ms"], int)


def test_typesafe_jev_maps_sdk_errors_to_jev_unavailable(tmp_path):
    ws = make_ws(tmp_path)
    client = StubClient(error=TypeSafeError("service is down"))
    with pytest.raises(jev.JevUnavailable):
        jev.TypeSafeJev(ws, client=client).ask({}, QUESTIONS, tag="classifier")
    assert "service is down" in jev.read_calls(ws)[0]["error"]


def test_typesafe_jev_without_a_key_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(jev, "load_env", lambda *a, **k: None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(jev.JevUnavailable):
        jev.TypeSafeJev(make_ws(tmp_path)).ask({}, QUESTIONS, tag="classifier")


# ---- fakes ---------------------------------------------------------------


def test_fake_jev_answers_records_and_demands_every_question():
    fake = FakeJev({
        "category": {"type": "choice", "choice": "ONE_TIME_FIXED", "confidence": 0.9, "probabilities": {}},
        "supported": lambda state: {"type": "noul", "noul": 1.0 if state["amount"] == 1400 else 0.0},
    })
    answers = fake.ask({"amount": 1400}, {"category": CHOICE_Q, "supported": NOUL_Q}, tag="classifier")
    assert answers["category"]["choice"] == "ONE_TIME_FIXED"
    assert answers["supported"]["noul"] == 1.0
    assert fake.calls[0][0] == "classifier" and fake.calls[0][1] == {"amount": 1400}
    with pytest.raises(KeyError):
        fake.ask({}, {"sufficiency": SCORE_Q}, tag="estimation")


def test_fake_llm():
    fake = FakeLLM(extract={"amount": 1400.0}, outreach=lambda variables: {"text": f"Hi {variables['to']}"})
    assert fake("extract", {"text": "..."}) == {"amount": 1400.0}
    assert fake("outreach", {"to": "Dana"}) == {"text": "Hi Dana"}
    assert [name for name, _ in fake.calls] == ["extract", "outreach"]
    with pytest.raises(KeyError):
        fake("nope", {})


def test_make_ws_is_isolated_and_writable(tmp_path):
    ws = make_ws(tmp_path, world={"vendors": [{"vendor_id": "V001", "vendor_name": "Mintlify"}]})
    assert ws.db_dir.exists() and ws.state_dir.exists() and ws.out_dir.exists()
    assert store.world(ws, "vendors")[0]["vendor_name"] == "Mintlify"
    later = ws.at("2027-01-25T12:00:00Z")
    assert later.as_of == "2027-01-25T12:00:00Z" and later.world_dir == ws.world_dir
