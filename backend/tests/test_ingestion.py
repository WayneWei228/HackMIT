import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from trueup.agents import ingestion
from trueup.agents.ingestion import FileDecision, ingest, load_universe
from trueup.gateway import llm
from trueup.simulator.files.models import RelevanceTruth
from trueup.simulator.files.scoring import score_selection
from trueup.store import models as m
from trueup.store.session import create_all, get_session, make_engine

SEED = Path(__file__).resolve().parents[1] / "seed"
CLOSE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
JANUARY = datetime(2027, 1, 31, tzinfo=UTC)
CASES = [
    "CASE-MINTLIFY-2026-12",
    "CASE-OPENAI-2026-12",
    "CASE-ASUS-2026-12",
    "CASE-META-2026-12",
    "CASE-NOTABILITY-2026-12",
]


@pytest.fixture(scope="module")
def universe():
    return load_universe(SEED)


@pytest.fixture(scope="module")
def truth():
    return RelevanceTruth.model_validate_json((SEED / "relevance_truth.json").read_text())


def pick(*names):
    def judge(case, cards):
        return [
            FileDecision(file_id=c.entry.file_id, selected=c.entry.name in names, reason="test")
            for c in cards
        ]

    return judge


@pytest.mark.parametrize("case_id", CASES)
def test_every_visible_file_gets_one_decision(universe, case_id):
    result = ingest(universe, case_id, now=CLOSE, seed_dir=SEED)
    assert result.files_loaded == 10
    assert [d.file_id for d in result.decisions] == [
        f.file_id for f in universe.for_case(case_id) if f.available_at <= CLOSE
    ]
    assert all(d.reason for d in result.decisions)
    assert set(result.selected) | set(result.rejected) == {d.file_id for d in result.decisions}


def test_late_arrivals_only_appear_once_available(universe):
    at_close = ingest(universe, "CASE-OPENAI-2026-12", now=CLOSE, seed_dir=SEED)
    in_january = ingest(universe, "CASE-OPENAI-2026-12", now=JANUARY, seed_dir=SEED)
    assert in_january.files_loaded > at_close.files_loaded
    early = {d.file_id for d in at_close.decisions}
    assert early < {d.file_id for d in in_january.decisions}


def test_rule_baseline_runs_offline_and_can_be_scored(universe, truth):
    for case_id in CASES:
        result = ingest(universe, case_id, now=CLOSE, seed_dir=SEED)
        assert result.judge == "rule_judge"
        assert 0 <= score_selection(result.selected, truth, case_id)["f1"] <= 1


def test_scoring_rewards_the_right_selection(universe, truth):
    case_id = "CASE-MINTLIFY-2026-12"
    right = {e.file_id for e in truth.for_case(case_id) if e.in_universe and e.relevant}
    names = {f.name for f in universe.files if f.file_id in right}
    result = ingest(universe, case_id, now=CLOSE, seed_dir=SEED, judge=pick(*names))
    assert score_selection(result.selected, truth, case_id)["f1"] == 1.0


def test_llm_judge_sends_file_text_and_no_answer_key(universe, monkeypatch):
    seen = {}

    def fake_complete_json(prompt, schema, **_):
        seen["prompt"] = prompt
        files = [
            f.file_id for f in universe.for_case("CASE-MINTLIFY-2026-12") if f.available_at <= CLOSE
        ]
        return schema(
            decisions=[
                {"file_id": i, "selected": n < 2, "reason": "because"} for n, i in enumerate(files)
            ]
        )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    result = ingest(universe, "CASE-MINTLIFY-2026-12", now=CLOSE, seed_dir=SEED)
    assert result.judge == "llm_judge"
    assert len(result.selected) == 2
    prompt = seen["prompt"]
    assert "Mintlify" in prompt and "mintlify_master_subscription_agreement.pdf" in prompt
    assert "$1,400" in prompt
    for leak in ("SUPPORTS_", "HARD_NEGATIVE", "relevance_truth", "NOISE"):
        assert leak not in prompt


def test_missing_decision_defaults_to_rejected_and_is_logged(universe):
    engine = make_engine()
    create_all(engine)

    def partial(case, cards):
        return [FileDecision(file_id=cards[0].entry.file_id, selected=True, reason="kept")]

    with get_session(engine) as session:
        result = ingest(
            universe,
            "CASE-META-2026-12",
            now=CLOSE,
            seed_dir=SEED,
            judge=partial,
            session=session,
        )
    assert len(result.selected) == 1 and len(result.rejected) == 9
    with get_session(engine) as session:
        run = session.scalars(select(m.TrueUpAgentRun)).one()
    assert run.agent_name == "ingestion" and run.action == "select_files"
    assert run.status == "COMPLETED"
    assert len(run.input_record_ids_json) == 10
    assert run.output_record_ids_json == result.selected
    assert len(run.uncertainties_json) == 9
    assert "Selected 1 of 10" in run.decision_summary


def test_agent_never_touches_the_answer_key():
    source = inspect.getsource(ingestion)
    assert "scoring" not in source and "relevance_truth" not in source
    assert "RelevanceTruth" not in source
    manifest = json.loads((SEED / "file_universe.json").read_text())
    assert "relevant" not in json.dumps(manifest)
