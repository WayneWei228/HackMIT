"""The held-out vendors: fresh documents and data the pipeline was never tuned on.

`seed_holdout/` holds three vendors written in different wordings, layouts and currency notation
than the five demo vendors. These tests check the data is consistent, that the whole close runs
on it offline without crashing, and they pin what happens today. Misses are documented as strict
expected failures that name their cause, so fixing an agent flips them and forces this file to be
updated. Nothing here loosens a check or changes an agent to make the held-out vendors pass.
"""

import importlib.util
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trueup.ingest.manifest import FileUniverse
from trueup.ingest.readers import read_text
from trueup.simulator.files.models import RelevanceTruth
from trueup.simulator.scenario_models import StaticCompanyData

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed_holdout"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load("run_holdout")
generator = _load("generate_holdout")


@pytest.fixture(scope="module")
def universe() -> FileUniverse:
    return FileUniverse.model_validate_json((SEED / "file_universe.json").read_text())


@pytest.fixture(scope="module")
def relevance() -> RelevanceTruth:
    return RelevanceTruth.model_validate_json((SEED / "relevance_truth.json").read_text())


@pytest.fixture(scope="module")
def static() -> StaticCompanyData:
    return StaticCompanyData.model_validate_json((SEED / "static_company_data.json").read_text())


@pytest.fixture(scope="module")
def truth() -> dict:
    return json.loads((SEED / "holdout_truth.json").read_text())["cases"]


def _score(suite):
    harness.score_documents(
        suite, harness.ingestion.rule_judge, harness.evidence_rules.rule_extractor, False
    )
    harness.run_pipeline(suite, harness.ingestion.rule_judge, harness.evidence_rules.rule_extractor)
    harness.score_pipeline(suite)
    return suite


@pytest.fixture(scope="module")
def held_out():
    return _score(harness.load_suite("held-out", SEED))


@pytest.fixture(scope="module")
def demo_control():
    return _score(harness.load_suite("demo", harness.ingestion.SEED_DIR))


def find(suite, vendor: str, dimension: str, label: str | None = None):
    rows = [
        c
        for c in suite.checks
        if c.vendor == vendor and c.dimension == dimension and (label is None or c.label == label)
    ]
    if len(rows) != 1:
        raise LookupError(f"{vendor} / {dimension} / {label}: {len(rows)} checks")
    return rows[0]


# ---- (a) the generated files and hidden keys agree -------------------------------------------


def test_every_file_exists_and_has_a_relevance_entry(universe, relevance):
    ids = {f.file_id for f in universe.files}
    assert ids == set(relevance.entries)
    for f in universe.files:
        assert (SEED / f.path).is_file(), f.path
        assert read_text(SEED / f.path).strip(), f"{f.path} reads as empty"


def test_each_case_has_ten_files_three_or_four_relevant(universe, relevance):
    assert len(universe.cases) == 3
    for case in universe.cases:
        visible = [f for f in universe.for_case(case.case_id) if f.available_at <= universe.as_of]
        assert len(visible) == 10, case.case_id
        entries = [relevance.entries[f.file_id] for f in visible]
        wanted = [e for e in entries if e.relevant]
        assert 3 <= len(wanted) <= 4, case.case_id
        roles = {e.role for e in entries}
        assert {"HARD_NEGATIVE", "NOISE"} <= roles
        reasons = " ".join(e.reason for e in entries if e.role == "HARD_NEGATIVE")
        assert "different vendor" in reasons, f"{case.case_id} has no wrong-vendor lookalike"
        assert any(w in reasons for w in ("superseded", "replaced", "expired")), case.case_id
        late = [e for e in relevance.for_case(case.case_id) if e.role == "LATE_ARRIVAL"]
        assert late and all(not e.in_universe for e in late)
        arrivals = {f.file_id: f.available_at for f in universe.files}
        assert all(arrivals[e.file_id] > universe.as_of for e in late), case.case_id


def test_all_five_file_formats_are_used(universe):
    assert {f.format for f in universe.files} == {"PDF", "XLSX", "DOCX", "EML", "TXT"}


def test_documents_avoid_the_dollar_sign_notation_of_the_demo(universe):
    for f in universe.files:
        assert "$" not in read_text(SEED / f.path), f.path


def test_static_data_is_three_new_vendors_on_day_one(static):
    names = {v.vendor_name for v in static.company_vendors}
    assert names == {"Terrastack Compute", "Larkspur Design Studio", "Corvid Security"}
    start = datetime.fromisoformat(static.meta["simulation_start"])
    for table in ("company_service_evidence", "company_ap_invoices", "company_gl_entries"):
        for row in getattr(static, table):
            stamp = row.created_at
            assert stamp <= start, f"{table} row {stamp} is after day one"


def test_hidden_truth_matches_the_invoices_in_the_data(static, truth):
    events = json.loads((SEED / "scenario_events.json").read_text())
    invoices = {i.invoice_id: i.amount for i in static.company_ap_invoices}
    invoices |= {
        e["record"]["invoice_id"]: Decimal(e["record"]["amount"])
        for e in events
        if e["table"] == "company_ap_invoices"
    }
    history = json.loads((SEED / "historical_truth.json").read_text())["expected_outcomes"]
    for row in history:
        assert Decimal(row["expected_actual_amount"]) == invoices[row["invoice_id"]], row
    for case in truth.values():
        december = next(
            h for h in history if h["vendor_id"] == case["vendor_id"] and h["period"] == "2026-12"
        )
        assert Decimal(case["final"]["invoice"]) == Decimal(december["expected_actual_amount"])
        assert Decimal(case["final"]["accrued"]) == Decimal(december["expected_actual_amount"])


def test_expected_amounts_are_plain_arithmetic():
    assert Decimal("6900") * Decimal("2.70") == Decimal("18630.00")
    assert Decimal("6200") * Decimal("2.70") - Decimal("6200") * Decimal("2.50") == Decimal("1240")
    assert Decimal("6500") * Decimal("2.70") - Decimal("6500") * Decimal("2.50") == Decimal("1300")
    prorated = (Decimal("3250") * 15 / 31 + Decimal("3900") * 16 / 31).quantize(Decimal("0.01"))
    assert prorated == Decimal("3585.48")
    assert sum(Decimal(x) for x in ("18000", "22500", "27450", "28050")) == Decimal("96000")
    assert Decimal("27450") >= Decimal("25000")


def test_regeneration_reproduces_the_committed_seed(tmp_path):
    out = tmp_path / "seed_holdout"
    assert generator.generate(out) == len(list((SEED / "files").rglob("*.*")))
    for name in (
        "static_company_data.json",
        "scenario_events.json",
        "outreach_responses.json",
        "file_universe.json",
        "relevance_truth.json",
        "historical_truth.json",
        "holdout_truth.json",
    ):
        assert (out / name).read_text() == (SEED / name).read_text(), name
    for committed in (SEED / "files").rglob("*.*"):
        rebuilt = out / committed.relative_to(SEED)
        assert read_text(rebuilt) == read_text(committed), committed.name


# ---- (b) the whole close runs offline on vendors it has never seen ---------------------------


def test_the_offline_close_completes_without_crashing(held_out):
    assert "crash" not in held_out.report, held_out.report.get("crash")
    assert not held_out.report["at_close"].errors and not held_out.report["actuals"].errors
    hit, total = harness.tally(held_out.checks)
    assert total >= 50 and 0 < hit < total
    for vendor in ("Terrastack Compute", "Larkspur Design Studio", "Corvid Security"):
        assert find(held_out, vendor, "detection").ok


def test_the_demo_control_passes_every_pipeline_check(demo_control):
    documents = ("ingestion", "facts (end to end)", "facts (extractor alone)")
    stages = [c for c in demo_control.checks if c.dimension not in documents]
    assert stages and all(c.ok for c in stages), [c for c in stages if not c.ok]


# ---- (c) the answer keys stay out of agent code ---------------------------------------------


def test_agent_code_never_reads_the_holdout_keys():
    allowed = ("simulator",)
    offenders = []
    for path in (ROOT / "trueup").rglob("*.py"):
        parts = path.relative_to(ROOT / "trueup").parts
        if parts[0] in allowed:
            continue
        source = path.read_text()
        for needle in ("holdout_truth", "seed_holdout"):
            if needle in source:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, offenders


def test_only_evaluation_scripts_read_the_hidden_keys():
    readers = [p.name for p in (ROOT / "scripts").glob("*.py") if "holdout_truth" in p.read_text()]
    assert set(readers) == {"run_holdout.py", "generate_holdout.py"}


# ---- (d) what the offline pipeline scores today ----------------------------------------------
#
# Measured on the first offline run (rule judge, rule extractor, no model): 30 of 55 checks, and
# 66 of 74 on the five demo vendors. Floors below are those measured values; a fix that raises a
# number is welcome, one that lowers it is a regression.

MEASURED_FLOORS = {
    "detection": 3,
    "purchase type": 3,
    "method": 2,
    "close: accrual": 3,
    "close: stage": 3,
    "close: controller": 1,
    "final: stage": 2,
    "final: accrual": 2,
    "final: diagnosis": 2,
    "history diagnosis": 8,
    "learning": 1,
}
MEASURED_OVERALL = 30


def test_regression_floor(held_out):
    for dimension, floor in MEASURED_FLOORS.items():
        hit, _ = harness.tally(held_out.checks, dimension)
        assert hit >= floor, f"{dimension}: {hit} < measured {floor}"
    assert harness.tally(held_out.checks)[0] >= MEASURED_OVERALL


WHY_JUDGE = (
    "the rule judge only keeps files that show a '$' amount; these documents write 'USD 2.50'"
)
WHY_EXTRACTOR = (
    "the regex extractor is templated on the demo documents ('$X per month', 'Units to date', "
    "'Delivered to date', 'Total due: $X', Month D, YYYY dates) and reads no 'USD' amounts, "
    "amounts inside tables, or day-first dates"
)
WHY_UPSTREAM = "nothing was selected upstream and the extractor is templated on the demo documents"
WHY_REPLY = (
    "the offline reply reader wants the quantity directly before the unit; "
    "'6,900 GPU compute-hours' has 'GPU' in between, so the reply is 'not resolved' and the "
    "case goes to the Controller with no estimate"
)

TERRASTACK, LARKSPUR, CORVID = "Terrastack Compute", "Larkspur Design Studio", "Corvid Security"
KNOWN_MISSES = [
    (v, "ingestion", "every relevant file selected", WHY_JUDGE)
    for v in (TERRASTACK, LARKSPUR, CORVID)
]
FACTS = {
    TERRASTACK: [
        "stepped-up rate 2.70 per hour",
        "base rate 2.50 per hour",
        "usage to date 4,690 hours",
        "usage covers only to 2026-12-21",
    ],
    LARKSPUR: ["not-to-exceed budget 96,000", "D3 accepted, fee 27,450"],
    CORVID: [
        "amended monthly fee 3,900",
        "original monthly fee 3,250",
        "amendment effective 2026-12-16",
    ],
}
for _vendor, _labels in FACTS.items():
    for _label in _labels:
        KNOWN_MISSES.append((_vendor, "facts (end to end)", _label, WHY_UPSTREAM))
        KNOWN_MISSES.append((_vendor, "facts (extractor alone)", _label, WHY_EXTRACTOR))
KNOWN_MISSES += [
    (TERRASTACK, "method", None, WHY_REPLY),
    (TERRASTACK, "final: stage", None, WHY_REPLY),
    (TERRASTACK, "final: accrual", None, WHY_REPLY),
    (TERRASTACK, "final: diagnosis", None, WHY_REPLY),
]


@pytest.mark.parametrize(
    ("vendor", "dimension", "label", "reason"),
    [
        pytest.param(
            v,
            d,
            label,
            why,
            marks=pytest.mark.xfail(strict=True, reason=why, raises=AssertionError),
        )
        for v, d, label, why in KNOWN_MISSES
    ],
    ids=[f"{v.split()[0]}-{d}-{(label or '')[:24]}" for v, d, label, _ in KNOWN_MISSES],
)
def test_known_miss_still_missing(held_out, vendor, dimension, label, reason):
    check = find(held_out, vendor, dimension, label)
    assert check.ok, check.detail


def test_no_miss_beyond_the_documented_ones(held_out):
    documented = {(v, d, label) for v, d, label, _ in KNOWN_MISSES}
    unexpected = [
        f"{c.vendor} / {c.dimension} / {c.label}: {c.detail}"
        for c in held_out.checks
        if not c.ok
        and (c.vendor, c.dimension, c.label) not in documented
        and (c.vendor, c.dimension, None) not in documented
    ]
    assert not unexpected, unexpected
