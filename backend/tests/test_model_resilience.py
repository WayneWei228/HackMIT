"""The live model never fails silently: retries, honest fallbacks, health and the key's facts.

Everything here is keyless. A fake client stands in for the provider and raises what it raises.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from trueup import close_orchestrator as orchestrator
from trueup.agents import evidence_agent, evidence_rules
from trueup.agents.evidence_agent import DocumentFacts, FactKey
from trueup.agents.ingestion import FileDecision, IngestionResult, load_universe
from trueup.gateway import llm
from trueup.service import demo_state, model_probe
from trueup.service.app import create_app
from trueup.store import enums as e
from trueup.store import models as m

CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
PERIOD = "2026-12"
ASUS = "OBL-ASUS-2026-12"


def make_key(
    *, region: str = "us-east-1", signed: str = "20260920T121610Z", lifetime: str = "43200"
):
    url = (
        "bedrock.amazonaws.com/?Action=CallWithBearerToken&X-Amz-Algorithm=AWS4-HMAC-SHA256"
        f"&X-Amz-Credential=ASIAEXAMPLE%2F20260920%2F{region}%2Fbedrock%2Faws4_request"
        f"&X-Amz-Date={signed}&X-Amz-Expires={lifetime}&X-Amz-SignedHeaders=host&Version=1"
    )
    return "bedrock-api-key-" + base64.b64encode(url.encode()).decode()


class HTTPFail(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status_code = status


class APIConnectionError(Exception):
    """Named like the SDK's class, which carries no status code."""


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


@pytest.fixture
def model(monkeypatch):
    """A live Bedrock key in the environment and a fake provider that replays what it is given."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key())
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)
    pauses: list[float] = []
    monkeypatch.setattr(llm, "_sleep", pauses.append)

    def install(*replies):
        client = FakeClient(*replies)
        monkeypatch.setattr(llm, "_client", lambda: client)
        client.pauses = pauses
        return client

    return install


# ---- the gateway: what is retried, what is not -------------------------------------------------


def test_a_rejected_key_is_not_retried_and_says_so(model):
    client = model(HTTPFail(401), "never reached")
    with pytest.raises(llm.LLMAuthError) as raised:
        llm.complete("hi")
    assert len(client.calls) == 1
    assert "credentials were rejected (401)" in str(raised.value)
    report = llm.health()
    assert report["status"] == "credentials_rejected" and "401" in report["last_error"]


def test_a_forbidden_key_is_also_an_auth_error(model):
    model(HTTPFail(403))
    with pytest.raises(llm.LLMAuthError):
        llm.complete("hi")


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_throttle_or_server_error_is_retried_until_it_works(model, status):
    client = model(HTTPFail(status), HTTPFail(status), "ok")
    assert llm.complete("hi") == "ok"
    assert len(client.calls) == 3
    assert client.pauses == [1.0, 3.0]
    report = llm.health()
    assert report["status"] == "ok" and report["last_ok_at"] and report["last_error"] is None


def test_a_timeout_and_a_dropped_connection_are_retried(model):
    client = model(TimeoutError("slow"), APIConnectionError("reset"), "ok")
    assert llm.complete("hi") == "ok"
    assert len(client.calls) == 3


def test_retries_are_bounded_and_the_error_names_what_failed(model):
    client = model(HTTPFail(500), HTTPFail(500), HTTPFail(500))
    with pytest.raises(llm.LLMError) as raised:
        llm.complete("hi")
    assert not isinstance(raised.value, llm.LLMAuthError)
    assert len(client.calls) == llm.CALL_ATTEMPTS
    assert "after 3 tries" in str(raised.value) and "500" in str(raised.value)
    assert llm.health()["status"] == "unavailable"


def test_a_bad_request_is_not_retried(model):
    client = model(HTTPFail(400), "never reached")
    with pytest.raises(llm.LLMError, match="Model call failed"):
        llm.complete("hi")
    assert len(client.calls) == 1 and client.pauses == []


def test_the_auth_message_says_when_the_key_has_expired(model, monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key(signed="20200101T000000Z"))
    model(HTTPFail(401))
    with pytest.raises(llm.LLMAuthError, match="The key expired at 2020-01-01T12:00:00Z"):
        llm.complete("hi")


def test_the_auth_message_says_when_the_region_is_wrong(model, monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key(signed="20990101T000000Z"))
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    model(HTTPFail(401))
    with pytest.raises(
        llm.LLMAuthError, match="signed for us-east-1 but the call went to us-east-2"
    ):
        llm.complete("hi")


# ---- a reply of the wrong shape is an error, never an empty read -------------------------------


def a_fact(**over):
    fact = {"key": FactKey.OTHER.value, "label": "Note", "value_text": "v", "quote": "q"}
    return {**fact, **over}


def test_a_reply_wrapped_in_one_key_is_unwrapped(model):
    reply = json.dumps({"result": {"vendor_name": "ASUS", "facts": [a_fact()]}})
    client = model(reply)
    got = llm.complete_json("read it", DocumentFacts)
    assert [f.label for f in got.facts] == ["Note"] and len(client.calls) == 1


def test_a_reply_with_the_wrong_shape_is_retried_then_an_error_not_zero_facts(model):
    client = model(json.dumps({"unrelated": 1}), json.dumps({"answer": "none"}))
    with pytest.raises(llm.LLMError, match="did not match DocumentFacts"):
        llm.complete_json("read it", DocumentFacts)
    assert len(client.calls) == llm.JSON_ATTEMPTS


def test_extra_keys_are_refused_so_a_wrapper_around_facts_cannot_read_as_empty(model):
    client = model(json.dumps({"facts": [], "reasoning": "x"}), json.dumps({"facts": []}))
    assert llm.complete_json("read it", DocumentFacts).facts == []
    assert len(client.calls) == 2


def test_a_real_empty_reply_is_still_allowed(model):
    model(json.dumps({"facts": []}))
    assert llm.complete_json("read it", DocumentFacts).facts == []


# ---- the key says where it works and until when ------------------------------------------------


def test_the_key_names_its_region_and_its_latest_expiry():
    info = llm.key_info(make_key())
    assert info.region == "us-east-1" and info.expires_at == "2026-09-21T00:16:10Z"


def test_a_key_that_says_nothing_yields_nothing():
    assert llm.key_info("token") == llm.KeyInfo(None, None)
    assert llm.key_info("") == llm.KeyInfo(None, None)
    assert llm.key_info("bedrock-api-key-!!!") == llm.KeyInfo(None, None)


def test_a_key_missing_its_lifetime_still_gives_the_region():
    url = (
        "bedrock.amazonaws.com/?X-Amz-Credential=A%2F20260920%2Feu-west-1%2Fbedrock%2Faws4_request"
    )
    key = base64.b64encode(url.encode()).decode()
    assert llm.key_info(key) == llm.KeyInfo("eu-west-1", None)


def test_a_credential_scope_for_another_service_is_not_a_region():
    url = "x/?X-Amz-Credential=A%2F20260920%2Fus-east-1%2Fs3%2Faws4_request"
    assert llm.key_info(base64.b64encode(url.encode()).decode()).region is None


def test_the_region_is_the_env_then_the_key_then_the_default(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key(region="ap-south-1"))
    monkeypatch.delenv("AWS_REGION", raising=False)
    assert llm._region() == "ap-south-1"
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert llm._region() == "us-west-2"
    monkeypatch.delenv("AWS_REGION")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "opaque")
    assert llm._region() == llm.BEDROCK_DEFAULT_REGION


def test_the_client_calls_the_region_the_key_is_signed_for(monkeypatch):
    built: dict = {}

    class Recording:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", Recording)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key(region="us-east-1"))
    monkeypatch.delenv("AWS_REGION", raising=False)
    llm._client()
    assert built["base_url"] == "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1"


def test_health_reports_the_expiry_and_never_the_key(monkeypatch):
    key = make_key()
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", key)
    report = llm.health()
    assert report["mode"] == "live" and report["expires_at"] == "2026-09-21T00:16:10Z"
    assert key not in json.dumps(report) and key[16:60] not in json.dumps(report)


def test_health_is_offline_and_unknown_without_a_key():
    assert llm.health() == {
        "mode": "offline",
        "status": "unknown",
        "last_error": None,
        "last_ok_at": None,
        "expires_at": None,
    }


# ---- the probe keeps health fresh without anyone running a case --------------------------------


def test_a_probe_without_credentials_makes_no_call():
    assert llm.probe()["mode"] == "offline"


def test_a_probe_records_success_and_failure_without_raising(model):
    model("ok", HTTPFail(401))
    assert llm.probe()["status"] == "ok"
    assert llm.probe()["status"] == "credentials_rejected"


@pytest.fixture
def probe_thread():
    model_probe._thread = None
    yield
    model_probe.stop()
    if model_probe._thread is not None:
        model_probe._thread.join(timeout=2)
    model_probe._thread = None


def test_the_background_probe_runs_repeatedly_and_stops(monkeypatch, probe_thread):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key())
    seen: list[int] = []
    monkeypatch.setattr(llm, "probe", lambda: seen.append(1) or llm.health())
    assert model_probe.start(interval=0.01) is True
    assert model_probe.start(interval=0.01) is False
    deadline = time.time() + 2
    while len(seen) < 3 and time.time() < deadline:
        time.sleep(0.01)
    assert len(seen) >= 3
    model_probe.stop()
    model_probe._thread.join(timeout=2)
    assert not model_probe._thread.is_alive()


def test_the_probe_never_starts_without_credentials_or_when_switched_off(monkeypatch, probe_thread):
    assert model_probe.start() is False
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", make_key())
    monkeypatch.setenv("TRUEUP_MODEL_PROBE", "0")
    assert model_probe.start() is False


def test_starting_the_app_does_not_probe_in_tests(probe_thread):
    with TestClient(create_app()):
        assert model_probe._thread is None


def test_the_close_carries_the_model_health():
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    body = client.get("/api/close").json()
    assert body["model"] == {
        "mode": "offline",
        "status": "unknown",
        "last_error": None,
        "last_ok_at": None,
        "expires_at": None,
    }


# ---- Evidence: a failed model read is never a clean run ----------------------------------------


def _failing(case, entry, text):
    raise llm.LLMError("Model call failed after 3 tries (APIStatusError 429: throttled)")


_failing.__name__ = "llm_extractor"


def _mintlify_all_selected():
    universe = load_universe()
    case = next(c for c in universe.cases if c.vendor_id == "VEN-MINTLIFY")
    files = universe.for_case(case.case_id)
    picked = IngestionResult(
        case_id=case.case_id,
        files_loaded=len(files),
        decisions=[FileDecision(file_id=f.file_id, selected=True, reason="all") for f in files],
        judge="all",
    )
    return universe, picked


def _last_evidence_run(session):
    return session.scalars(
        select(m.TrueUpAgentRun)
        .where(m.TrueUpAgentRun.agent_name == "evidence")
        .order_by(m.TrueUpAgentRun.run_id)
    ).all()[-1]


def test_when_the_model_fails_the_rules_read_the_file_and_the_run_says_so():
    from trueup.simulator.simulator import Simulator

    sim = Simulator.initialize()
    with sim.session() as session:
        ob = orchestrator.walk_to(
            session, "VEN-MINTLIFY", PERIOD, now=CLOSE, to=orchestrator.ESTIMATE
        )
        universe, picked = _mintlify_all_selected()
        result = evidence_agent.collect_evidence(
            universe,
            picked,
            now=CLOSE,
            extractor=_failing,
            fallback=evidence_rules.rule_extractor,
            session=session,
            obligation_id=ob.obligation_id,
        )
        assert result.cards, "the rule-based extractor read the documents"
        assert result.extractor == "rule_extractor after a model error"
        assert len(result.model_errors) == len(picked.selected)
        assert any("the rule-based extractor read it" in u for u in result.uncertainties)
        run = _last_evidence_run(session)
        assert run.status == e.AgentRunStatus.COMPLETED
        assert "Model error on" in run.decision_summary and "429" in run.decision_summary


def test_when_the_model_fails_and_nothing_else_reads_the_file_the_run_fails():
    from trueup.simulator.simulator import Simulator

    sim = Simulator.initialize()
    with sim.session() as session:
        ob = orchestrator.walk_to(
            session, "VEN-MINTLIFY", PERIOD, now=CLOSE, to=orchestrator.ESTIMATE
        )
        universe, picked = _mintlify_all_selected()
        result = evidence_agent.collect_evidence(
            universe,
            picked,
            now=CLOSE,
            extractor=_failing,
            session=session,
            obligation_id=ob.obligation_id,
        )
        assert result.cards == [] and len(result.unread_files) == len(picked.selected)
        assert _last_evidence_run(session).status == e.AgentRunStatus.FAILED


def test_zero_grounded_facts_escalate_instead_of_passing_the_gate():
    from trueup.agents.controller_workspace import controller_id
    from trueup.demo_controller import ScriptedController
    from trueup.simulator.simulator import Simulator

    sim = Simulator.initialize()
    with sim.session() as session:
        controller = ScriptedController(controller_id(session), approve_vendors=["VEN-ASUS"])
        settings = orchestrator.CloseSettings(extractor=_failing)
        orchestrator.run_month_end_close(
            session,
            PERIOD,
            now=CLOSE,
            simulator=sim,
            controller=controller,
            settings=settings,
        )
        for vendor in ("ASUS", "MINTLIFY", "OPENAI", "META", "NOTABILITY"):
            ob = session.get(m.TrueUpObligation, f"OBL-{vendor}-{PERIOD}")
            assert ob.workflow_stage == e.WorkflowStage.AWAITING_CONTROLLER, vendor
            assert ob.accrual_status == e.AccrualStatus.NOT_STARTED, vendor


# ---- the service: what a person sees when the model is down -----------------------------------


@pytest.fixture
def api_with_a_failing_model(monkeypatch):
    """Live mode is on, the Evidence model call fails, and the rules can still read the files."""
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(evidence_agent, "llm_extractor", _failing)
    client = TestClient(create_app())
    assert client.post("/api/reset").status_code == 200
    demo_state.current().judge = lambda case, cards: [
        FileDecision(file_id=c.entry.file_id, selected=True, reason="test judge") for c in cards
    ]
    return client


def _drive(api, obligation_id):
    for _ in range(60):
        step = api.post(f"/api/obligations/{obligation_id}/advance").json()
        if step["done"]:
            return step
    raise AssertionError("the case never rested")


def test_the_screen_says_the_model_failed_and_the_rules_read_the_documents(
    api_with_a_failing_model,
):
    _drive(api_with_a_failing_model, ASUS)
    detail = api_with_a_failing_model.get(f"/api/obligations/{ASUS}").json()
    checks = {c["check_id"]: c for c in detail["evidence"]["stage_checks"]}
    assert checks["EVI-MODEL"]["status"] == "FLAG" and "429" in checks["EVI-MODEL"]["body"]
    assert "rule_extractor after a model error" in checks["EVI-GROUND"]["body"]
    log = api_with_a_failing_model.get(f"/api/obligations/{ASUS}/log").json()["entries"]
    reads = [x for x in log if x["title"] == "Evidence extracted facts"]
    assert reads and all(x["method"] == "CODE" for x in reads)
    assert all("rule_extractor after a model error" in x["summary"] for x in reads)


def test_a_case_whose_documents_the_model_could_not_read_shows_the_escalation(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(evidence_agent, "llm_extractor", _failing)
    monkeypatch.setattr(orchestrator, "default_fallback", lambda: None)
    client = TestClient(create_app())
    client.post("/api/reset")
    demo_state.current().judge = lambda case, cards: [
        FileDecision(file_id=c.entry.file_id, selected=True, reason="test judge") for c in cards
    ]
    _drive(client, ASUS)
    detail = client.get(f"/api/obligations/{ASUS}").json()
    escalation = detail["escalation"]
    assert escalation["reason"] == "INSUFFICIENT_INFORMATION"
    assert "the model failed while reading them" in escalation["message"]
    checks = {c["check_id"]: c for c in detail["evidence"]["stage_checks"]}
    assert checks["EVI-GROUND"]["status"] == "FLAG"
    assert client.get("/api/close").json()["cases"][0]["status"] != "Close-ready"
