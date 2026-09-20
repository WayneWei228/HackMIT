"""The HTTP API: the shapes the Next.js UI is typed against, read off a small run directory built here.

The allowed key sets below are hard-coded from the frontend's `_data.ts` files: a screen endpoint may only
return names that are exported DATA constants of the matching file (never delays, step thresholds or functions).
"""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from close import api

P = "2026-12"
CLOSE_AT = "2027-01-05T12:00:00Z"
SETTLE_AT = "2027-01-15T12:00:00Z"

VENDORS = [{"vendor_id": "V001", "vendor_name": "Mintlify", "aliases": []},
           {"vendor_id": "V002", "vendor_name": "OpenAI", "aliases": []},
           {"vendor_id": "V003", "vendor_name": "ASUS", "aliases": []},
           {"vendor_id": "V004", "vendor_name": "Meta", "aliases": []}]
HEADERS = [{"po_number": "PO-001", "vendor_id": "V001", "vendor_name": "Mintlify", "order_type": "FO", "status": "Open",
            "entity_id": "ORBIT-US", "validity_start": "2026-09-01", "validity_end": "2027-08-31"},
           {"po_number": "PO-002", "vendor_id": "V002", "vendor_name": "OpenAI", "order_type": "FO", "status": "Open",
            "entity_id": "ORBIT-US", "validity_start": "2026-09-01", "validity_end": "2027-08-31"},
           {"po_number": "PO-003", "vendor_id": "V003", "vendor_name": "ASUS", "order_type": "NB", "status": "Open",
            "entity_id": "ORBIT-US", "requester": "alex.chen"},
           {"po_number": "CAMPAIGN-004", "vendor_id": "V004", "vendor_name": "Meta", "order_type": "NB",
            "status": "Open", "entity_id": "ORBIT-US", "validity_start": "2026-12-01", "validity_end": "2026-12-31"}]
LINES = [{"po_line_id": "PO-001-001", "po_number": "PO-001", "item_category": "P", "contract_id": "CTR-001",
          "gr_required": False, "unit_price": 1200, "line_description": "documentation platform"},
         {"po_line_id": "PO-002-001", "po_number": "PO-002", "item_category": "B", "contract_id": "CTR-002",
          "gr_required": False, "line_description": "api usage"},
         {"po_line_id": "PO-003-001", "po_number": "PO-003", "item_category": "", "gr_required": True,
          "quantity_ordered": 25, "quantity_received": 20, "quantity_billed": 0, "unit_price": 1600,
          "line_description": "laptops"},
         {"po_line_id": "CAMPAIGN-004-001", "po_number": "CAMPAIGN-004", "item_category": "B", "gr_required": False,
          "overall_limit": 30000, "line_description": "december campaign"}]
CONTRACTS = [{"contract_id": "CTR-001", "vendor_id": "V001", "version": 1, "monthly_rate": 1200.0, "unit_rate": None,
              "effective_start": "2026-01-01", "effective_end": "2026-11-30", "status": "Superseded",
              "source_doc": "CTR-001"},
             {"contract_id": "CTR-001", "vendor_id": "V001", "version": 2, "monthly_rate": 1400.0, "unit_rate": None,
              "effective_start": "2026-12-01", "effective_end": None, "status": "Active", "source_doc": "AMD-001"},
             {"contract_id": "CTR-002", "vendor_id": "V002", "version": 1, "monthly_rate": None, "unit_rate": 0.02,
              "effective_start": "2026-01-01", "effective_end": None, "status": "Active", "source_doc": "CTR-002"}]
INVOICES = [{"invoice_id": "INV-MINT-DEC", "vendor_id": "V001", "po_line_id": "PO-001-001", "service_period": P,
             "amount": 1400.0, "status": "POSTED", "source_doc": "INV-MINT-DEC"},
            {"invoice_id": "INV-ASUS-DEC", "vendor_id": "V003", "po_line_id": "PO-003-001", "service_period": P,
             "amount": 32000.0, "status": "POSTED", "source_doc": "INV-ASUS-DEC"}]
ACTIVITY = [{"activity_id": "USG-DEC", "po_line_id": "PO-002-001", "kind": "USAGE", "service_period": P,
             "coverage_start": "2026-12-01", "coverage_end": "2026-12-25", "quantity": 700000.0, "value": 14000.0,
             "replaced_by": None, "source_doc": "USG-DEC"}]
RECEIPTS = [{"gr_id": "GR-ASUS-DEC", "po_line_id": "PO-003-001", "received_date": "2026-12-28", "quantity": 20.0,
             "source_doc": "GR-ASUS-DEC"}]
DOCUMENTS = [{"doc_id": "CTR-001", "doc_type": "CONTRACT", "vendor_id": "V001", "po_line_id": "PO-001-001",
              "quality": "OK", "reasons": [], "applied_to": "contracts", "record": {"monthly_rate": 1200.0}},
             {"doc_id": "INV-MINT-DEC", "doc_type": "INVOICE", "vendor_id": "V001", "po_line_id": "PO-001-001",
              "quality": "OK", "reasons": [], "applied_to": "invoices", "record": {"amount": 1400.0}},
             {"doc_id": "USG-DEC", "doc_type": "USAGE_REPORT", "vendor_id": "V002", "po_line_id": "PO-002-001",
              "quality": "OK", "reasons": [], "applied_to": "activity", "record": {"quantity": 700000.0}},
             {"doc_id": "GR-ASUS-DEC", "doc_type": "GOODS_RECEIPT", "vendor_id": "V003", "po_line_id": "PO-003-001",
              "quality": "OK", "reasons": [], "applied_to": "goods_receipts", "record": {"quantity": 20.0}}]
TICKETS = [{"ticket_id": "T-2026-12-CAMPAIGN-004-001-MISSING_DATA", "case_id": f"{P}/CAMPAIGN-004-001", "period": P,
            "reason": "MISSING_DATA", "asked_of": "INTERNAL", "to": "maria.gomez", "question": "What was delivered?",
            "message": None, "blocking": True, "deadline": "2027-01-05T00:00:00Z", "state": "EXPIRED",
            "opened_at": "2027-01-02T12:00:00Z", "answered_at": None, "answered_by_doc": None,
            "expired_at": CLOSE_AT},
           {"ticket_id": "T-2026-12-PO-002-001-MISSING_DATA", "case_id": f"{P}/PO-002-001", "period": P,
            "reason": "MISSING_DATA", "asked_of": "INTERNAL", "to": "dana.kim", "question": "Final usage?",
            "message": None, "blocking": True, "deadline": "2027-01-05T00:00:00Z", "state": "OPEN",
            "opened_at": "2027-01-02T12:00:00Z", "answered_at": None, "answered_by_doc": None, "expired_at": None}]


def _case(key, status, **blocks):
    line = next(l for l in LINES if l["po_line_id"] == key)
    header = next(h for h in HEADERS if h["po_number"] == line["po_number"])
    case = {"case_id": f"{blocks.pop('period', P)}/{key}", "case_key": key, "period": P, "as_of": CLOSE_AT,
            "kind": "PO_LINE", "entity_id": "ORBIT-US", "vendor_id": header["vendor_id"],
            "vendor_name": header["vendor_name"], "po_line_id": key, "status": status,
            "obligation": {"source_type": "PO", "source_id": key, "recognition_basis": "CONTRACT_SCHEDULE",
                           "service_period_start": f"{P}-01", "service_period_end": f"{P}-31",
                           "reasons": ["PO validity covers period"]},
            "invoice_match": None, "classification": None, "estimate": None, "outreach": None, "journal": None,
            "settlement": None, "flags": [], "evidence_refs": [], "decision_log": []}
    case.update(blocks)
    return case


MATCH_NONE = {"result": "NO_INVOICE", "invoice_ids": [], "invoiced_amount": 0, "on_ap": [], "in_queue": [],
              "expected_amount": None, "uninvoiced_amount": None, "duplicates": [], "candidates": []}
MATCH_FULL = {"result": "FULL_INVOICE", "invoice_ids": ["INV-ASUS-DEC"], "invoiced_amount": 32000.0,
              "on_ap": ["INV-ASUS-DEC"], "in_queue": [], "expected_amount": 32000.0, "uninvoiced_amount": 0.0,
              "duplicates": [], "candidates": []}


def _classification(final, confidence=0.9):
    return {"rules": final, "rules_why": "columns fit", "contradictions": [], "model": final,
            "model_confidence": confidence, "cache_hit": True, "agree": True, "final": final, "suggested": None}


def _estimate(category, estimator, amount, calculation, **extra):
    return {"category": category, "estimator": estimator, "amount": amount, "calculation": calculation,
            "complete": True, "forced": False, "extrapolated": False, "missing": None, "three_way_match": None,
            "fallback": None, "base": {"amount": amount, "calculation": calculation}, "lessons_applied": [],
            "sources": [], "mismatch": None, "explanation": "", **extra}


def _log(worker, question, answer):
    return {"at": CLOSE_AT, "worker": worker, "kind": "RULE", "question": question, "answer": answer,
            "confidence": None, "action": ""}


FULL_LOG = [_log(w, "q", "a") for w in ("detection", "invoice_lookup", "classifier", "estimation", "settlement")]

# One case per status we map, so the stage / status tables are all exercised.
CASES = [
    # SETTLED: a fixed recurring accrual the vendor then billed higher.
    _case("PO-001-001", "SETTLED", invoice_match=MATCH_NONE, classification=_classification("RECURRING_FIXED"),
          estimate=_estimate("RECURRING_FIXED", "CONTRACT_RATE", 1200.0, "1200"), decision_log=FULL_LOG,
          settlement={"actual": 1400.0, "accrued": 1200.0, "true_up": 200.0, "settled_by": ["INV-MINT-DEC"],
                      "cause": "EXTERNAL_CHANGE", "within_tolerance": False,
                      "recheck": {"contract_rate_at_close": 1200.0, "po_rate": 1200, "prior_invoice_amounts": [1200.0],
                                  "estimate_basis": "CONTRACT_RATE", "consistent_at_close": True, "notes": []},
                      "ticket_id": None, "explained": True, "explanation": "the vendor changed the price",
                      "settled_at": SETTLE_AT}),
    # OUTREACH_PENDING with an OPEN ticket -> Outreach / Queued.
    _case("PO-002-001", "OUTREACH_PENDING", invoice_match=MATCH_NONE,
          classification=_classification("RECURRING_VARIABLE", 0.97),
          estimate=_estimate("RECURRING_VARIABLE", "USAGE_EXTRAPOLATED", None, None, complete=False,
                             extrapolated=True, missing="usage after 2026-12-25"),
          flags=["EXTRAPOLATED"], decision_log=FULL_LOG[:4]),
    # INVOICED -> Invoice Lookup / Close-ready / Accounts Payable.
    _case("PO-003-001", "INVOICED", invoice_match=MATCH_FULL, classification=_classification("ONE_TIME_FIXED", 0.82),
          decision_log=FULL_LOG[:3]),
    # CLOSED with a forced estimate and an EXPIRED ticket -> Settlement / Close-ready.
    _case("CAMPAIGN-004-001", "CLOSED", invoice_match=MATCH_NONE,
          classification=_classification("ONE_TIME_VARIABLE", 0.72),
          estimate=_estimate("ONE_TIME_VARIABLE", "PO_BUDGET", 30000.0, "30000", complete=False, forced=True,
                             missing="delivery report for the period",
                             fallback={"estimator": "PO_BUDGET", "calculation": "30000",
                                       "basis": "PO budget (overall limit)"}),
          flags=["MISSING_DATA", "FORCED_ESTIMATE"], decision_log=FULL_LOG[:4]),
]
# The remaining statuses, as bare cases whose blocks say how far each got.
EXTRA_CASES = [
    _case("PO-001-001", "DETECTED"),
    _case("PO-001-001", "ENRICHED", invoice_match=MATCH_NONE, classification=_classification("RECURRING_FIXED")),
    _case("PO-001-001", "REVIEW", invoice_match=MATCH_NONE, classification=_classification("RECURRING_FIXED")),
    _case("PO-001-001", "ESTIMATED", invoice_match=MATCH_NONE, classification=_classification("RECURRING_FIXED"),
          estimate=_estimate("RECURRING_FIXED", "CONTRACT_RATE", 1200.0, "1200")),
    _case("PO-001-001", "NO_ACCRUAL", invoice_match=MATCH_NONE, classification=_classification("RECURRING_FIXED")),
    _case("PO-001-001", "LEARNED", invoice_match=MATCH_NONE, classification=_classification("RECURRING_FIXED"),
          estimate=_estimate("RECURRING_FIXED", "CONTRACT_RATE", 1200.0, "1200")),
]

EVENTS = [{"at": CLOSE_AT, "worker": "detection", "period": P, "message": f"event {i}"} for i in range(5)]


def write_run(root, cases=CASES, tickets=TICKETS):
    for name, rows in (("vendors", VENDORS), ("po_headers", HEADERS), ("po_lines", LINES), ("contracts", CONTRACTS),
                       ("invoices", INVOICES), ("activity", ACTIVITY), ("goods_receipts", RECEIPTS),
                       ("documents", DOCUMENTS)):
        (root / "db").mkdir(parents=True, exist_ok=True)
        (root / "db" / f"{name}.json").write_text(json.dumps(rows))
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "cases.json").write_text(json.dumps(cases))
    (root / "state" / "outreach.json").write_text(json.dumps(tickets))
    (root / "state" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in EVENTS))
    # `close.runner` reads these: the run book says which months ran, the package says what they came to.
    (root / "state" / "runs.json").write_text(json.dumps({P: {"closed_at": CLOSE_AT, "settled_at": SETTLE_AT}}))
    (root / "out" / P).mkdir(parents=True, exist_ok=True)
    (root / "out" / P / "accruals.json").write_text(json.dumps(
        [{"case_key": c["case_key"], "amount": (c.get("estimate") or {}).get("amount")}
         for c in cases if (c.get("estimate") or {}).get("amount") is not None]))
    (root / "out" / P / "trueups.json").write_text(json.dumps(
        [{"case_key": c["case_key"], **c["settlement"]} for c in cases if c.get("settlement")]))
    return root


MONTHS = ["2026-09", "2026-10", "2026-11", "2026-12"]


def write_pdfs(root):
    """A PDF folder is only its month folders as far as the API is concerned."""
    for month in MONTHS:
        (root / month).mkdir(parents=True, exist_ok=True)
        (root / month / f"DOC-{month}.pdf").write_bytes(b"%PDF-1.4\n")
    return root


@pytest.fixture(autouse=True)
def idle_job():
    """The job slot is module state; every test starts with it free."""
    api.JOB.update(running=False, action=None, period=None, started_at=None, finished_at=None,
                   error=None, result=None)
    yield
    api.JOB["running"] = False


@pytest.fixture
def pdfs(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUEUP_PDF_DIR", str(write_pdfs(tmp_path / "pdf")))
    return tmp_path / "pdf"


@pytest.fixture
def client(tmp_path, monkeypatch, pdfs):
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run")))
    return TestClient(api.app)


@pytest.fixture
def empty_client(tmp_path, monkeypatch, pdfs):
    """A brand new root: nothing has been run, nothing is pre-dumped."""
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(tmp_path / "nothing"))
    return TestClient(api.app)


def wait_for_job(client):
    for _ in range(200):
        status = client.get("/api/run/status").json()
        if not status["running"]:
            return status
        time.sleep(0.01)
    raise AssertionError("the job never finished")


# --------------------------------------------------------------------------------------------------------------
# The UI's string unions, copied from the frontend types
# --------------------------------------------------------------------------------------------------------------

CASE_CATEGORIES = {"Accruals", "Prepaids", "Fixed Assets", "Accounts Payable"}
CASE_STATUSES = {"Running", "In progress", "Queued", "Close-ready", "Complete"}
CASE_STAGES = {"Evidence", "Detection", "Invoice Lookup", "Classification", "Estimation", "Outreach", "Settlement"}
VENDOR_STATES = {"Autonomous", "Waiting for evidence", "Verified"}
WORKFLOW_NAMES = {"December accrual", "December usage accrual", "Asset recognition", "Prepaid amortization",
                  "Campaign spend", "Infrastructure spend"}
AGENT_NAMES = {"Evidence agent", "Detection agent", "Invoice Lookup agent", "Classification agent",
               "Estimation agent", "Outreach agent", "Settlement agent"}
HISTORY_TAGS = {"Verified", "In review"}
CONFIDENCES = {"High", "Medium"}

CASE_FIELDS = {"vendor", "initials", "mark", "item", "category", "amount", "stage", "status", "date", "time",
               "ts", "href"}
VENDOR_FIELDS = {"name", "id", "mark", "initials", "profile", "treatment", "workflow", "amount", "sort", "state",
                 "category", "accTreatment", "confidence", "history", "sources", "memory", "relationship", "agents"}

# Exported DATA constants of each screen's `_data.ts` (its `MOCK` object); anything else the endpoint
# returns is a bug. Copied by hand from the frontend, which is the contract.
INGESTION_KEYS = {"CASE_VENDOR", "CASE_TITLE", "CASE_META", "CASE_STATS", "CASE_STATUS_VALUE",
                  "SOURCE_ORDER", "SOURCE_NAMES", "SOURCE_FOOTERS", "SOURCE_TABS", "FILES_LOADED_LABEL"}
EVIDENCE_KEYS = {"CASE", "FACTS", "MATCH", "SELECTION"}
ANALYSIS_KEYS = {"caseMeta", "headerStats", "evidenceInputsLabel", "sourceFacts", "factAttributes",
                 "sourceDocumentsLabel", "analysisIntro", "analysisChecks", "conclusion", "conclusionRows",
                 "railTasks", "handoffBlurb"}
ESTIMATION_KEYS = {"CASE", "SUMMARY", "SUMMARY_STATUS", "INPUTS", "INPUTS_FOOTNOTE", "BUILD_STEPS", "BUILD_BLURB",
                   "CALC_ROWS", "CALC_TOTAL", "ADJUSTMENTS", "ACCRUAL_AMOUNT", "RECOMMENDATION_ROWS",
                   "RECOMMENDATION_NOTE", "JOURNAL", "RAIL_TASKS", "HANDOFF_BLURB"}
CONTROLS_KEYS = {"HEAD_STATS", "CASE_META", "ASSERTIONS", "EXTRA_CHECKS", "CONTROLS", "SCAN_ITEMS", "FINAL_ROWS",
                 "JOURNAL_LINES", "ACCRUAL_AMOUNT", "TASKS", "HANDOFF_BLURB"}
SCREEN_KEYS = {"ingestion": INGESTION_KEYS, "evidence": EVIDENCE_KEYS, "detection": ANALYSIS_KEYS,
               "invoice-lookup": ANALYSIS_KEYS, "classification": ANALYSIS_KEYS, "estimation": ESTIMATION_KEYS,
               "outreach": CONTROLS_KEYS, "settlement": CONTROLS_KEYS}

BUILD_STEP_FIELDS = {"kind", "n", "title", "text", "pendingText", "resolvesAt", "tallBody", "waitingUntil"}
BUILD_STEP_KINDS = ("coverage", "rate", "calc", "adjustments", "final")

AGENT_CHAIN = ["Evidence", "Detection", "Invoice Lookup", "Classification", "Estimation", "Outreach",
               "Settlement"]
# Every case key in the fixture, and the amount string that belongs to it alone.
OTHER_AMOUNTS = {"PO-001-001": ["$1,200", "$1,400"], "PO-003-001": ["$32,000"],
                 "CAMPAIGN-004-001": ["$30,000"]}


def money_to_float(text):
    return float(text.replace("$", "").replace(",", "").replace("+", ""))


# --------------------------------------------------------------------------------------------------------------


def test_health_lists_the_pdf_months_and_the_company(client, pdfs):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["company"] == "Orbit Labs"
    assert body["periods"] == MONTHS and body["pdf_dir"] == str(pdfs)


def test_cases_are_typed_case_records(client):
    rows = client.get("/api/cases").json()["CASES"]
    assert len(rows) == len(CASES)
    for row in rows:
        assert set(row) == CASE_FIELDS
        assert row["category"] in CASE_CATEGORIES and row["status"] in CASE_STATUSES and row["stage"] in CASE_STAGES
        assert isinstance(row["amount"], int) and isinstance(row["ts"], float) and 0 <= row["mark"] <= 4
        assert row["initials"] and row["item"] and row["date"] and row["time"]


def test_period_filter(client):
    assert client.get("/api/cases", params={"period": "2020-01"}).json()["CASES"] == []
    assert len(client.get("/api/cases", params={"period": P}).json()["CASES"]) == len(CASES)


@pytest.mark.parametrize("status,stage,ui_status", [
    ("DETECTED", "Detection", "Running"),
    ("ENRICHED", "Classification", "Running"),
    ("REVIEW", "Estimation", "In progress"),
    ("ESTIMATED", "Estimation", "Running"),
    ("NO_ACCRUAL", "Classification", "Close-ready"),
    ("LEARNED", "Settlement", "Complete"),
    ("SETTLED", "Settlement", "Complete"),
    ("OUTREACH_PENDING", "Outreach", "Queued"),
    ("INVOICED", "Invoice Lookup", "Close-ready"),
    ("CLOSED", "Settlement", "Close-ready"),
])
def test_stage_and_status_mapping(tmp_path, monkeypatch, status, stage, ui_status):
    wanted = next(c for c in CASES + EXTRA_CASES if c["status"] == status)
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run", cases=[wanted])))
    row = TestClient(api.app).get("/api/cases").json()["CASES"][0]
    assert (row["stage"], row["status"]) == (stage, ui_status)


def test_invoiced_case_is_a_payable_at_the_invoiced_amount(client):
    row = next(r for r in client.get("/api/cases").json()["CASES"] if r["vendor"] == "ASUS")
    assert row["category"] == "Accounts Payable" and row["amount"] == 32000


def test_vendors_are_typed_vendor_records(client):
    rows = client.get("/api/vendors").json()["VENDORS"]
    assert len(rows) == len(VENDORS)
    for row in rows:
        assert set(row) == VENDOR_FIELDS
        assert row["state"] in VENDOR_STATES and row["workflow"] in WORKFLOW_NAMES
        assert row["confidence"] in CONFIDENCES and 0 <= row["mark"] <= 4
        assert isinstance(row["memory"], str) and isinstance(row["sort"], float)
        for entry in row["history"]:
            assert set(entry) == {"period", "amount", "tag"} and entry["tag"] in HISTORY_TAGS
        for entry in row["relationship"]:
            assert set(entry) == {"when", "what"}
        for entry in row["agents"]:
            assert set(entry) == {"agent", "uses"} and entry["agent"] in AGENT_NAMES and entry["uses"]


def test_vendor_state_and_confidence_follow_the_data(client):
    by_name = {v["name"]: v for v in client.get("/api/vendors").json()["VENDORS"]}
    assert by_name["OpenAI"]["state"] == "Waiting for evidence"   # an OPEN ticket
    assert by_name["OpenAI"]["confidence"] == "Medium"            # an extrapolated estimate
    assert by_name["Mintlify"]["state"] == "Verified"             # its latest case is SETTLED
    assert by_name["Mintlify"]["confidence"] == "High"
    assert "the vendor changed the price" in by_name["Mintlify"]["memory"]
    assert by_name["Mintlify"]["sources"] == ["CTR-001", "INV-MINT-DEC"]


@pytest.mark.parametrize("screen", sorted(SCREEN_KEYS))
def test_every_screen_returns_every_data_constant(client, screen):
    """The frontend no longer merges over a mock, so a missing key is a blank screen."""
    for key in ("PO-001-001", "CAMPAIGN-004-001", "PO-003-001"):
        body = client.get(f"/api/cases/{P}/{key}/screens/{screen}").json()
        assert set(body) == SCREEN_KEYS[screen], f"{screen}/{key}: {SCREEN_KEYS[screen] ^ set(body)}"


@pytest.mark.parametrize("status", sorted({c["status"] for c in CASES + EXTRA_CASES}))
@pytest.mark.parametrize("screen", sorted(SCREEN_KEYS))
def test_every_screen_is_complete_for_every_status(tmp_path, monkeypatch, pdfs, screen, status):
    """DETECTED-only, INVOICED, ESTIMATED, OUTREACH_PENDING, CLOSED, SETTLED - all of them render."""
    wanted = next(c for c in CASES + EXTRA_CASES if c["status"] == status)
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / f"{status}-{screen}", cases=[wanted])))
    body = TestClient(api.app).get(f"/api/cases/{P}/{wanted['case_key']}/screens/{screen}").json()
    assert set(body) == SCREEN_KEYS[screen], f"{screen}/{status}: {SCREEN_KEYS[screen] ^ set(body)}"


def test_journal_lines_balance(client):
    estimation = client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/estimation").json()
    debit, credit = estimation["JOURNAL"]
    assert debit["side"] == "Dr" and credit["side"] == "Cr"
    assert money_to_float(debit["amount"]) == money_to_float(credit["amount"]) == 30000.0
    assert debit["account"].startswith("6300") and credit["account"].startswith("2150")
    assert estimation["ACCRUAL_AMOUNT"] == "$30,000"
    verification = client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/settlement").json()
    dr, cr = verification["JOURNAL_LINES"]
    assert money_to_float(dr["amount"]) == money_to_float(cr["amount"]) == 30000.0


def test_an_invoiced_case_still_carries_both_journal_keys(client):
    """Complete means complete: the keys are there, the accrual entry is simply empty."""
    body = client.get(f"/api/cases/{P}/PO-003-001/screens/estimation").json()
    assert body["JOURNAL"] == [] and body["ACCRUAL_AMOUNT"] == "—"
    controls = client.get(f"/api/cases/{P}/PO-003-001/screens/outreach").json()
    assert controls["JOURNAL_LINES"] == [] and controls["ACCRUAL_AMOUNT"] == "—"


def test_screens_carry_that_agents_own_data(client):
    detection = client.get(f"/api/cases/{P}/PO-001-001/screens/detection").json()
    assert any("PO validity covers period" == f["amount"] for f in detection["sourceFacts"])
    lookup = client.get(f"/api/cases/{P}/PO-003-001/screens/invoice-lookup").json()
    assert any(r["value"] == "FULL_INVOICE" for r in lookup["conclusionRows"])
    assert lookup["conclusion"]["amount"] == "$0"       # the invoice is on hand, nothing stays accrued
    classification = client.get(f"/api/cases/{P}/PO-002-001/screens/classification").json()
    assert any(r.get("kind") == "confidence" and r["width"] == "97%" for r in classification["conclusionRows"])
    outreach = client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/outreach").json()
    assert {"label": "State", "value": "EXPIRED", "plain": True} in outreach["ASSERTIONS"]
    settlement = client.get(f"/api/cases/{P}/PO-001-001/screens/settlement").json()
    assert {"label": "True-up", "value": "+$200"} in settlement["ASSERTIONS"]
    assert len(settlement["CONTROLS"]) == 6 and settlement["CONTROLS"][-1]["body"] is None
    assert len(settlement["ASSERTIONS"]) == 6 and len(settlement["EXTRA_CHECKS"]) == 2


@pytest.mark.parametrize("case_key", sorted(OTHER_AMOUNTS))
@pytest.mark.parametrize("screen", sorted(SCREEN_KEYS))
def test_a_screen_never_mentions_another_cases_numbers(client, screen, case_key):
    body = json.dumps(client.get(f"/api/cases/{P}/{case_key}/screens/{screen}").json())
    strays = [amount for key, amounts in OTHER_AMOUNTS.items() if key != case_key
              for amount in amounts if amount in body]
    assert not strays, f"{screen} for {case_key} carries {strays}"


@pytest.mark.parametrize("screen", ["detection", "invoice-lookup", "classification"])
def test_analysis_screens_carry_their_narrative(client, screen):
    body = client.get(f"/api/cases/{P}/PO-001-001/screens/{screen}").json()
    for check in body["analysisChecks"]:
        assert set(check) <= {"label", "body", "pendingBody", "resolvesAt", "subChecks", "pending", "bodyDuration"}
        assert check["label"] and check["body"] and isinstance(check["bodyDuration"], float)
        if "pendingBody" in check:
            assert isinstance(check["resolvesAt"], int)
    assert all(set(task) <= {"label", "multiline"} and task["label"] for task in body["railTasks"])


def test_estimation_build_steps_describe_this_case(client):
    body = client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/estimation").json()
    steps = body["BUILD_STEPS"]
    assert [s["kind"] for s in steps] == list(BUILD_STEP_KINDS)
    assert [s["n"] for s in steps] == ["1", "2", "3", "4", "5"]
    assert all(set(step) <= BUILD_STEP_FIELDS for step in steps)
    assert all(isinstance(step["title"], str) and step["title"] for step in steps)
    assert "$30,000" in steps[1]["text"] and "PO budget" in steps[1]["text"]
    assert steps[2]["text"] == "30000 = $30,000." and steps[2]["pendingText"] and steps[2]["resolvesAt"] == 8
    assert steps[4]["text"] == body["RECOMMENDATION_NOTE"]     # the final step is the real recommendation
    assert "CAMPAIGN-004-001" in body["BUILD_BLURB"] and body["INPUTS_FOOTNOTE"].startswith("Obligation basis")
    assert "PO budget" in body["HANDOFF_BLURB"]


@pytest.mark.parametrize("screen", ["outreach", "settlement"])
def test_control_screens_carry_their_narrative(client, screen):
    body = client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/{screen}").json()
    assert len(body["SCAN_ITEMS"]) == 4 and all(body["SCAN_ITEMS"])
    assert len(body["TASKS"]) == 6 and all(body["TASKS"])
    scan = body["CONTROLS"][-1]
    assert scan["body"] is None and scan["doneSubtitle"]


def test_settlement_says_what_an_invoiced_case_has_instead(client):
    body = client.get(f"/api/cases/{P}/PO-003-001/screens/settlement").json()
    assert body["HEAD_STATS"][1]["value"] == "—" and body["HEAD_STATS"][0]["value"] == "—"
    assert body["FINAL_ROWS"][0] == {"label": "Cause", "value": "Invoiced, nothing to true up"}
    assert "Nothing to settle" in body["CONTROLS"][0]["body"]
    assert "INV-ASUS-DEC" in body["ASSERTIONS"][0]["value"]
    assert body["ASSERTIONS"][2]["value"] == "Nothing accrued"


def test_the_intake_header_names_the_case(client):
    body = client.get(f"/api/cases/{P}/PO-001-001/screens/ingestion").json()
    assert body["CASE_VENDOR"] == "Mintlify" and body["CASE_TITLE"] == "December 2026 accrual"
    assert body["SOURCE_ORDER"] == ["agreement", "invoice"]
    assert set(body["SOURCE_NAMES"]) == set(body["SOURCE_ORDER"])     # a partial record, only what is there
    assert set(body["SOURCE_FOOTERS"]) == set(body["SOURCE_ORDER"])
    assert body["SOURCE_FOOTERS"]["agreement"]["detail"] == "CTR-001"
    assert body["FILES_LOADED_LABEL"] == "2 files loaded"


def test_the_cited_document_is_the_one_the_number_came_from(client):
    assert client.get(f"/api/cases/{P}/PO-001-001/screens/evidence").json()["MATCH"] == {
        "docId": "CTR-001", "page": 1}                               # the contract rate behind $1,200
    assert client.get(f"/api/cases/{P}/PO-002-001/screens/evidence").json()["MATCH"] == {
        "docId": "USG-DEC", "page": 1}                               # the usage report behind the extrapolation
    assert client.get(f"/api/cases/{P}/PO-003-001/screens/evidence").json()["MATCH"] == {
        "docId": "GR-ASUS-DEC", "page": 1}                           # the goods receipt behind the match
    assert client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/evidence").json()["MATCH"] is None


def test_the_workflow_label_names_the_cases_own_month(client):
    by_name = {v["name"]: v for v in client.get("/api/vendors").json()["VENDORS"]}
    assert by_name["Mintlify"]["workflow"] == "December accrual"
    assert by_name["OpenAI"]["workflow"] == "December usage accrual"
    assert by_name["ASUS"]["workflow"] == "Asset recognition"
    scoped = {v["name"]: v for v in client.get("/api/vendors", params={"period": P}).json()["VENDORS"]}
    assert scoped["Mintlify"]["workflow"] == "December accrual"
    assert api.workflow_of("RECURRING_FIXED", "2026-09") == "September accrual"
    assert api.workflow_of("RECURRING_VARIABLE", "2026-09") == "September usage accrual"


def test_an_invoiced_case_says_so_instead_of_faking_an_estimate(client):
    body = client.get(f"/api/cases/{P}/PO-003-001/screens/estimation").json()
    blob = json.dumps(body)
    for filler in ("no estimator", "None", "(none)", "Not estimated"):
        assert filler not in blob, f"{filler!r} is still in the estimation payload"
    assert "INV-ASUS-DEC" in body["BUILD_BLURB"] and "$32,000" in body["BUILD_BLURB"]
    assert body["INPUTS_FOOTNOTE"] == "Obligation basis: Invoiced, not accrued"
    gl = next(i for i in body["INPUTS"] if i["label"] == "GL account")
    assert gl["value"] == "1500 · Computer equipment"                # the expense account, never the liability
    obligation = next(i for i in body["INPUTS"] if i["label"] == "Obligation amount")
    assert obligation["value"] == "$32,000" and obligation["sub"] == "Invoice on hand"
    assert [s["kind"] for s in body["BUILD_STEPS"]] == list(BUILD_STEP_KINDS)
    assert body["BUILD_STEPS"][1]["title"] == "Look for an invoice"
    assert "Invoiced, not accrued" in body["BUILD_STEPS"][4]["text"]
    assert {"label": "Basis", "value": "Invoiced, not accrued"} in body["RECOMMENDATION_ROWS"]
    assert body["CALC_TOTAL"]["label"] == "Invoiced amount" and body["CALC_TOTAL"]["value"] == "$32,000"
    assert body["JOURNAL"] == [] and body["ACCRUAL_AMOUNT"] == "—"


@pytest.mark.parametrize("status", ["INVOICED", "OUTREACH_PENDING", "REVIEW", "CLOSED", "NO_ACCRUAL"])
def test_no_screen_says_no_estimator(tmp_path, monkeypatch, pdfs, status):
    wanted = next(c for c in CASES + EXTRA_CASES if c["status"] == status)
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / status, cases=[wanted])))
    client = TestClient(api.app)
    for screen in SCREEN_KEYS:
        blob = json.dumps(client.get(f"/api/cases/{P}/{wanted['case_key']}/screens/{screen}").json())
        assert "no estimator" not in blob.lower(), f"{screen}/{status}"
        assert "2150 · Accrued liabilities" not in blob or screen in ("estimation",)


def test_running_a_month_closes_then_settles(empty_client, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "runner_close", lambda period: calls.append(("close", period)) or {"cases": 2})
    monkeypatch.setattr(api, "runner_settle", lambda period: calls.append(("settle", period)) or {"settled": 1})
    assert empty_client.post("/api/periods/2026-09/run").json() == {"started": True, "action": "run",
                                                                    "period": "2026-09"}
    status = wait_for_job(empty_client)
    assert calls == [("close", "2026-09"), ("settle", "2026-09")] and status["error"] is None
    assert status["result"] == {"period": "2026-09", "close": {"cases": 2}, "settle": {"settled": 1}}


def test_running_a_closed_month_only_settles_and_a_settled_one_is_a_no_op(client, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "runner_close", lambda period: calls.append(("close", period)))
    monkeypatch.setattr(api, "runner_settle", lambda period: calls.append(("settle", period)) or {})
    assert client.post(f"/api/periods/{P}/run").status_code == 200
    assert wait_for_job(client)["result"] == {"period": P, "skipped": "already settled"}
    assert calls == []
    monkeypatch.setattr(api, "runner_status", lambda: [{"period": P, "state": "CLOSED"}])
    api.JOB["running"] = False
    client.post(f"/api/periods/{P}/run")
    wait_for_job(client)
    assert calls == [("settle", P)]                                  # closed already: only the settlement runs


def test_a_run_is_refused_while_another_job_is_in_flight(empty_client):
    api.JOB.update(running=True, action="run-all")
    assert empty_client.post("/api/periods/2026-09/run").status_code == 409


def test_the_seven_agents_are_reported_from_the_events(empty_client, monkeypatch):
    log = Path(os.environ["TRUEUP_RUN_DIR"]) / "state" / "events.jsonl"

    def work(period):
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            for worker in ("evidence", "detection", "invoice_lookup", "classifier", "estimation", "runner"):
                fh.write(json.dumps({"at": CLOSE_AT, "worker": worker, "period": period,
                                     "message": f"{worker} said something"}) + "\n")
        return {}

    monkeypatch.setattr(api, "runner_close", work)
    empty_client.post("/api/periods/2026-09/close")
    agents = wait_for_job(empty_client)["agents"]
    assert [a["agent"] for a in agents] == AGENT_CHAIN
    assert all(set(a) == {"agent", "state", "last_message", "events"} for a in agents)
    states = {a["agent"]: a["state"] for a in agents}
    assert states == {"Evidence": "done", "Detection": "done", "Invoice Lookup": "done",
                      "Classification": "done", "Estimation": "done", "Outreach": "pending",
                      "Settlement": "pending"}
    assert states["Settlement"] == "pending"                          # a close-only job never reaches it
    estimation = next(a for a in agents if a["agent"] == "Estimation")
    assert estimation["events"] == 1 and estimation["last_message"] == "estimation said something"
    assert all(a["last_message"] is None for a in agents if a["state"] == "pending")


def test_no_job_yet_means_no_agent_has_run(client):
    """The log may be full of earlier runs; until this process starts a job, none of it is ours."""
    status = client.get("/api/run/status").json()
    assert status["progress"] == []
    assert all(a["state"] == "pending" and a["events"] == 0 for a in status["agents"])


def test_the_latest_agent_is_running_while_the_job_is(empty_client):
    events = [{"at": CLOSE_AT, "worker": w, "period": P, "message": w} for w in ("evidence", "detection")]
    live = api.agent_progress(events, running=True)
    assert [a["state"] for a in live[:3]] == ["done", "running", "pending"]
    finished = api.agent_progress(events, running=False)
    assert [a["state"] for a in finished[:3]] == ["done", "done", "pending"]
    assert api.agent_progress([], running=True) == [
        {"agent": a, "state": "pending", "last_message": None, "events": 0} for a in AGENT_CHAIN]


def test_documents_and_journals_lists(client):
    docs = client.get("/api/documents").json()["documents"]
    assert len(docs) == len(DOCUMENTS)
    assert all(set(d) == {"doc_id", "doc_type", "quality", "period", "known_from", "file_name", "applied_to",
                          "vendor_id", "po_line_id", "record", "fields", "reasons"} for d in docs)
    assert next(d for d in docs if d["doc_id"] == "CTR-001")["fields"] == [
        {"label": "Monthly rate", "value": "1200.0"}]
    assert client.get("/api/documents", params={"period": "2020-01"}).json()["documents"] == []

    body = client.get("/api/journals").json()
    kinds = [(j["case_key"], j["kind"]) for j in body["journals"]]
    assert ("PO-001-001", "ACCRUAL") in kinds and ("PO-001-001", "TRUE_UP") in kinds
    assert ("PO-003-001", "ACCRUAL") not in kinds            # invoiced: no accrual was booked
    for journal in body["journals"]:
        debit, credit = journal["lines"]
        assert debit["amount"] == credit["amount"] and {debit["side"], credit["side"]} == {"Dr", "Cr"}
    assert "display default" in body["note"] and body["accounts"]["ACCRUED_LIABILITIES"]
    assert client.get("/api/journals", params={"period": "2020-01"}).json()["journals"] == []


def test_vendors_answers_with_vendors_and_nothing_else(client):
    """The headline numerals are counted in the frontend from this very list."""
    assert set(client.get("/api/vendors").json()) == {"VENDORS"}
    assert set(client.get("/api/vendors", params={"period": P}).json()) == {"VENDORS"}


@pytest.mark.parametrize("screen,expected", [
    ("detection", "Invoice Lookup receives"),
    ("invoice-lookup", "Classification receives"),
    ("classification", "Estimation receives"),
])
def test_analysis_screens_say_what_the_next_agent_receives(client, screen, expected):
    blurb = client.get(f"/api/cases/{P}/PO-001-001/screens/{screen}").json()["handoffBlurb"]
    assert blurb.startswith(expected) and blurb.endswith(".")


def test_control_screens_say_what_is_being_handed_on(client):
    outreach = client.get(f"/api/cases/{P}/PO-001-001/screens/outreach").json()["HANDOFF_BLURB"]
    assert "Settlement waits for the actual on PO-001-001" in outreach and "$1,200" in outreach
    settled = client.get(f"/api/cases/{P}/PO-001-001/screens/settlement").json()["HANDOFF_BLURB"]
    assert "settled at $1,400" in settled and "EXTERNAL_CHANGE" in settled
    waiting = client.get(f"/api/cases/{P}/CAMPAIGN-004-001/screens/settlement").json()["HANDOFF_BLURB"]
    assert "waiting for the actual invoice" in waiting
    invoiced = client.get(f"/api/cases/{P}/PO-003-001/screens/outreach").json()["HANDOFF_BLURB"]
    assert invoiced.startswith("Nothing for Settlement to true up") and "INV-ASUS-DEC" in invoiced


def test_the_app_payload_invents_no_user(client, pdfs):
    for path in ("/api/health", "/api/app"):
        body = client.get(path).json()
        assert set(body) == {"status", "company", "user", "run_dir", "pdf_dir", "periods", "current_period"}
        assert body["user"] is None and body["company"] == "Orbit Labs"
        assert body["periods"] == MONTHS and body["current_period"] == P


def test_one_document_carries_its_fields_and_pages(tmp_path, monkeypatch, pdfs):
    root = write_run(tmp_path / "run")
    page = tmp_path / "CTR-001.txt"
    page.write_text("Orbit Labs and Mintlify\n\nMonthly fee 1200")
    rows = json.loads((root / "db" / "documents.json").read_text())
    rows[0]["file"] = str(page)
    (root / "db" / "documents.json").write_text(json.dumps(rows))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(root))
    client = TestClient(api.app)
    body = client.get("/api/documents/CTR-001").json()
    assert body["file_name"] == "CTR-001.txt" and body["fields"][0]["label"] == "Monthly rate"
    assert body["pages"] == ["Orbit Labs and Mintlify", "Monthly fee 1200"]
    served = client.get("/api/documents/CTR-001/file")
    assert served.headers["content-type"].startswith("text/plain")
    assert served.headers["content-disposition"].startswith("inline")


def test_evidence_facts_come_from_the_tables(client):
    facts = client.get(f"/api/cases/{P}/PO-001-001/screens/evidence").json()["FACTS"]
    assert {"label": "CTR-001 v2 rate", "value": "$1,400 / mo", "at": 3} in facts
    assert [f["at"] for f in facts] == list(range(1, len(facts) + 1))


def test_evidence_shows_the_files_it_chose_out_of_all_it_read(client):
    picked = client.get(f"/api/cases/{P}/PO-001-001/screens/evidence").json()["SELECTION"]
    assert (picked["total"], picked["selected"]) == (len(DOCUMENTS), 2)
    by_id = {f["docId"]: f for f in picked["files"]}
    assert by_id["CTR-001"]["selected"] and by_id["CTR-001"]["reason"] == "Sets this line's contract terms"
    assert by_id["INV-MINT-DEC"]["reason"] == "Names this PO line"
    assert by_id["USG-DEC"] == {"docId": "USG-DEC", "fileName": "", "docType": "USAGE_REPORT", "period": None,
                                "selected": False, "reason": None, "belongsTo": "PO-002-001"}
    body = client.get(f"/api/cases/{P}/PO-001-001").json()            # the same rule picks the dossier's documents
    assert [d["doc_id"] for d in body["documents"]] == [f["docId"] for f in picked["files"] if f["selected"]]


def test_a_file_from_a_later_month_was_not_there_to_choose_from(tmp_path, monkeypatch, pdfs):
    later = [{**DOCUMENTS[2], "doc_id": "USG-JAN", "period": "2027-01"},                  # another line's, later
             {**DOCUMENTS[1], "doc_id": "INV-MINT-JAN", "period": "2027-01"}]             # this line's, later: kept
    root = write_run(tmp_path / "run")
    (root / "db" / "documents.json").write_text(json.dumps(
        [{**d, "period": P, "file": f"/somewhere/on/disk/{d['doc_id']}.pdf"} for d in DOCUMENTS] + later))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(root))
    picked = TestClient(api.app).get(f"/api/cases/{P}/PO-001-001/screens/evidence").json()["SELECTION"]
    ids = [f["docId"] for f in picked["files"]]
    assert "USG-JAN" not in ids and "INV-MINT-JAN" in ids
    assert all("/" not in f["fileName"] for f in picked["files"]) and picked["files"][0]["fileName"] == "CTR-001.pdf"


def test_dossier_carries_the_native_blocks(client):
    body = client.get(f"/api/cases/{P}/CAMPAIGN-004-001").json()
    assert body["case"]["status"] == "CLOSED" and body["case"]["estimate"]["estimator"] == "PO_BUDGET"
    assert [t["ticket_id"] for t in body["tickets"]] == ["T-2026-12-CAMPAIGN-004-001-MISSING_DATA"]
    assert body["documents"] == [] and body["decision_log"] == body["case"]["decision_log"]


def test_documents(client):
    body = client.get("/api/documents/CTR-001").json()
    assert body["doc_id"] == "CTR-001" and body["doc_type"] == "CONTRACT" and body["quality"] == "OK"
    assert body["record"] == {"monthly_rate": 1200.0} and body["text"] == ""   # no file on disk in this fixture
    assert client.get("/api/documents/NOPE").status_code == 404
    assert client.get("/api/documents/CTR-001/file").status_code == 404


def test_document_file_is_served_when_it_exists(tmp_path, monkeypatch):
    root = write_run(tmp_path / "run")
    page = tmp_path / "CTR-001.txt"
    page.write_text("monthly rate 1200")
    rows = json.loads((root / "db" / "documents.json").read_text())
    rows[0]["file"] = str(page)
    (root / "db" / "documents.json").write_text(json.dumps(rows))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(root))
    client = TestClient(api.app)
    assert client.get("/api/documents/CTR-001/file").text == "monthly rate 1200"
    assert client.get("/api/documents/CTR-001").json()["text"] == "monthly rate 1200"


def test_events_since(client):
    first = client.get("/api/events").json()
    assert len(first["events"]) == len(EVENTS) and first["next"] == len(EVENTS)
    rest = client.get("/api/events", params={"since": 3}).json()
    assert [e["message"] for e in rest["events"]] == ["event 3", "event 4"] and rest["next"] == len(EVENTS)
    assert client.get("/api/events", params={"since": 99}).json()["events"] == []


def test_an_empty_root_is_a_normal_state(empty_client):
    assert empty_client.get("/api/cases").json() == {"CASES": []}
    assert empty_client.get("/api/vendors").json() == {"VENDORS": []}
    assert empty_client.get("/api/documents").json() == {"documents": []}
    assert empty_client.get("/api/journals").json()["journals"] == []
    assert empty_client.get("/api/events").json() == {"events": [], "next": 0}
    health = empty_client.get("/api/health").json()
    assert health["status"] == "ok" and health["periods"] == MONTHS


def test_an_empty_root_still_404s_on_things_that_do_not_exist(empty_client):
    assert empty_client.get(f"/api/cases/{P}/PO-001-001").status_code == 404
    assert empty_client.get(f"/api/cases/{P}/PO-001-001/screens/estimation").status_code == 404
    assert empty_client.get("/api/documents/CTR-001").status_code == 404


def test_periods_before_anything_has_run(empty_client):
    body = empty_client.get("/api/periods").json()
    assert [r["period"] for r in body["periods"]] == MONTHS
    assert body["current"] == MONTHS[0]
    for row in body["periods"]:
        assert set(row) == {"period", "label", "state", "cases", "accrued_total", "true_up_total",
                            "unsettled", "documents", "can_close", "can_settle"}
        assert row["state"] == "NOT_RUN" and row["cases"] == 0 and not row["can_settle"]
        assert row["documents"] == 1          # the source PDF, counted before anything has run
    assert [r["can_close"] for r in body["periods"]] == [True, False, False, False]
    assert body["periods"][-1]["label"] == "December 2026"


def test_periods_once_a_month_has_run(client):
    body = client.get("/api/periods").json()
    rows = {r["period"]: r for r in body["periods"]}
    assert body["current"] == P
    assert rows[P]["cases"] == len(CASES) and rows[P]["state"] == "SETTLED"
    assert rows[P]["accrued_total"] == 31200.0 and rows[P]["true_up_total"] == 200.0
    assert rows[P]["documents"] == 1            # one source PDF in the month folder
    assert rows["2026-09"]["can_close"] and not rows["2026-10"]["can_close"]


def test_vendors_and_events_honour_the_period_filter(client):
    assert client.get("/api/vendors", params={"period": "2026-01"}).json()["VENDORS"] == []
    assert len(client.get("/api/vendors", params={"period": P}).json()["VENDORS"]) == len(VENDORS)
    assert client.get("/api/events", params={"period": "2020-01"}).json()["events"] == []
    scoped = client.get("/api/events", params={"period": P}).json()
    assert len(scoped["events"]) == len(EVENTS) and scoped["next"] == len(EVENTS)


def test_missing_optional_fields_are_tolerated(tmp_path, monkeypatch, pdfs):
    """Vendors built from PDFs: ids like V-MINTLIFY, no aliases, no entity id, no contract."""
    root = tmp_path / "sparse"
    (root / "db").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    (root / "db" / "vendors.json").write_text(json.dumps([{"vendor_id": "V-MINTLIFY",
                                                           "vendor_name": "Mintlify"}]))
    (root / "db" / "po_headers.json").write_text(json.dumps([{"po_number": "PO-001", "vendor_id": "V-MINTLIFY",
                                                              "vendor_name": "Mintlify", "status": "Open"}]))
    (root / "db" / "po_lines.json").write_text(json.dumps([{"po_line_id": "PO-001-001", "po_number": "PO-001"}]))
    bare = _case("PO-001-001", "DETECTED")
    bare["entity_id"] = None
    bare["vendor_id"] = "V-MINTLIFY"
    (root / "state" / "cases.json").write_text(json.dumps([bare]))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(root))
    client = TestClient(api.app)

    row = client.get("/api/cases").json()["CASES"][0]
    assert set(row) == CASE_FIELDS and row["stage"] == "Detection" and row["item"] == "PO-001-001"
    vendor = client.get("/api/vendors").json()["VENDORS"][0]
    assert set(vendor) == VENDOR_FIELDS and vendor["id"] == "V-MINTLIFY" and vendor["sources"] == []
    for screen in SCREEN_KEYS:
        body = client.get(f"/api/cases/{P}/PO-001-001/screens/{screen}")
        assert body.status_code == 200 and set(body.json()) <= SCREEN_KEYS[screen]


def test_404_on_an_unknown_case_or_screen(client):
    assert client.get(f"/api/cases/{P}/PO-009-009").status_code == 404
    response = client.get(f"/api/cases/{P}/PO-001-001/screens/nonsense")
    assert response.status_code == 404 and "unknown screen" in response.json()["detail"]


def test_closing_a_month_runs_the_runner_in_the_background(empty_client, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "runner_close", lambda period: calls.append(period) or {"cases": 2})
    assert empty_client.post("/api/periods/2026-09/close").json() == {"started": True, "action": "close",
                                                                      "period": "2026-09"}
    status = wait_for_job(empty_client)
    assert set(status) == {"running", "action", "period", "started_at", "finished_at", "error", "result",
                           "progress", "agents"}
    assert calls == ["2026-09"] and status["error"] is None and status["result"] == {"cases": 2}
    assert status["action"] == "close" and status["period"] == "2026-09" and status["progress"] == []


def test_settling_and_running_every_month(client, monkeypatch):
    settled = []
    monkeypatch.setattr(api, "runner_settle", lambda period: settled.append(period) or {"settled": 1})
    assert client.post(f"/api/periods/{P}/settle").status_code in (200, 400)   # 400 only once already settled
    closed, done = [], []
    monkeypatch.setattr(api, "runner_close", lambda period: closed.append(period) or {})
    monkeypatch.setattr(api, "runner_settle", lambda period: done.append(period) or {})
    api.JOB["running"] = False
    assert client.post("/api/periods/run-all").json()["action"] == "run-all"
    status = wait_for_job(client)
    assert status["error"] is None and closed == ["2026-09", "2026-10", "2026-11"]
    assert done == MONTHS[:3] or done == MONTHS                                # 2026-12 is settled already


def test_reset_empties_the_root(client, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "runner_reset", lambda: calls.append(True))
    assert client.post("/api/reset").json()["action"] == "reset"
    status = wait_for_job(client)
    assert calls == [True] and status["result"] == {"reset": True} and status["error"] is None


def test_months_close_in_order_and_only_once(empty_client):
    late = empty_client.post("/api/periods/2026-11/close")
    assert late.status_code == 400 and "2026-09 has not been closed yet" in late.json()["detail"]
    assert empty_client.post("/api/periods/2026-09/settle").status_code == 400
    assert empty_client.post("/api/periods/2020-01/close").status_code == 404


def test_an_already_closed_month_cannot_be_closed_again(client):
    response = client.post(f"/api/periods/{P}/close")
    assert response.status_code == 400 and "already" in response.json()["detail"]


def test_a_second_job_is_refused_while_one_is_in_flight(empty_client):
    api.JOB.update(running=True, action="close")
    for path in ("/api/periods/2026-09/close", "/api/periods/run-all", "/api/reset"):
        response = empty_client.post(path)
        assert response.status_code == 409 and "already running" in response.json()["detail"]


def test_progress_is_only_what_this_job_logged(empty_client, monkeypatch):
    log = Path(os.environ["TRUEUP_RUN_DIR"]) / "state" / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"at": CLOSE_AT, "worker": "detection", "period": P, "message": "older"}) + "\n")

    def work(period):
        with log.open("a") as fh:
            for i in range(60):
                fh.write(json.dumps({"at": CLOSE_AT, "worker": "estimation", "period": period,
                                     "message": f"step {i}"}) + "\n")
        return {}

    monkeypatch.setattr(api, "runner_close", work)
    empty_client.post("/api/periods/2026-09/close")
    progress = wait_for_job(empty_client)["progress"]
    assert len(progress) == 50 and progress[-1]["message"] == "step 59"
    assert all(set(e) == {"at", "worker", "message"} for e in progress)
    assert not any(e["message"] == "older" for e in progress)


def test_a_runner_refusal_is_reported_as_the_jobs_error(empty_client, monkeypatch):
    def refuse(period):
        raise ValueError("2026-08 is not closed yet")

    monkeypatch.setattr(api, "runner_close", refuse)
    empty_client.post("/api/periods/2026-09/close")
    assert wait_for_job(empty_client)["error"] == "2026-08 is not closed yet"


def test_a_runner_crash_is_reported_as_the_jobs_error(empty_client, monkeypatch):
    def crash(period):
        raise RuntimeError("bedrock said no")

    monkeypatch.setattr(api, "runner_close", crash)
    empty_client.post("/api/periods/2026-09/close")
    status = wait_for_job(empty_client)
    assert "bedrock said no" in status["error"] and status["result"] is None


# --------------------------------------------------------------------------------------------------------------
# The handoff: the raw JSON an agent read and wrote for one case, and the file each part lives in
# --------------------------------------------------------------------------------------------------------------

AGENTS = ["evidence", "detection", "invoice-lookup", "classification", "estimation", "outreach", "settlement"]


def _parts(body, side):
    return {(p["file"], p["label"]): p["data"] for p in body[side]}


def _handoff(client, case_key, agent):
    return client.get(f"/api/cases/{P}/{case_key}/handoff/{agent}")


@pytest.mark.parametrize("agent", AGENTS)
def test_a_handoff_names_real_files_and_carries_data(client, tmp_path, agent):
    body = _handoff(client, "PO-001-001", agent).json()
    assert body["agent"] == agent and body["case_id"] == f"{P}/PO-001-001"
    for part in body["input"] + body["output"]:
        assert set(part) == {"file", "label", "data"} and part["data"] not in (None, [], {})
        if part["file"].endswith(".json"):
            assert (tmp_path / "run" / part["file"]).is_file(), part["file"]


def test_a_handoff_output_is_the_block_that_agent_wrote(client):
    case = next(c for c in CASES if c["case_key"] == "PO-001-001")
    wrote = {"detection": "obligation", "invoice-lookup": "invoice_match", "classification": "classification",
             "estimation": "estimate", "settlement": "settlement"}
    for agent, block in wrote.items():
        out = _parts(_handoff(client, "PO-001-001", agent).json(), "output")
        assert out[("state/cases.json", block)] == case[block]


def test_a_handoff_keeps_each_agents_own_decisions(client):
    out = _parts(_handoff(client, "PO-001-001", "classification").json(), "output")
    assert [d["worker"] for d in out[("state/cases.json", "decision_log")]] == ["classifier"]


def test_one_agents_output_is_the_next_agents_input(client):
    case = next(c for c in CASES if c["case_key"] == "PO-003-001")
    lookup_in = _parts(_handoff(client, "PO-003-001", "invoice-lookup").json(), "input")
    assert lookup_in[("state/cases.json", "obligation")] == case["obligation"]
    assert [i["invoice_id"] for i in lookup_in[("db/invoices.json", "invoices on this PO line")]] == ["INV-ASUS-DEC"]
    estimation_in = _parts(_handoff(client, "PO-003-001", "estimation").json(), "input")
    assert estimation_in[("state/cases.json", "invoice_match")] == case["invoice_match"]
    assert estimation_in[("state/cases.json", "classification")] == case["classification"]


def test_evidence_hands_off_the_rows_its_documents_wrote(client):
    body = _handoff(client, "PO-003-001", "evidence").json()
    out = _parts(body, "output")
    assert [d["doc_id"] for d in out[("db/documents.json", "documents read for this case")]] == ["GR-ASUS-DEC"]
    assert out[("db/goods_receipts.json", "rows written from these documents")] == RECEIPTS


def test_a_handoff_names_a_documents_file_without_its_path(tmp_path, monkeypatch, pdfs):
    root = write_run(tmp_path / "run")
    rows = [{**d, "file": f"/Users/someone/pdf/2026-12/{d['doc_id']}.pdf"} for d in DOCUMENTS]
    (root / "db" / "documents.json").write_text(json.dumps(rows))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(root))
    out = _parts(_handoff(TestClient(api.app), "PO-003-001", "evidence").json(), "output")
    assert [d["file"] for d in out[("db/documents.json", "documents read for this case")]] == ["GR-ASUS-DEC.pdf"]


def test_outreach_hands_off_the_cases_tickets(client):
    out = _parts(_handoff(client, "PO-002-001", "outreach").json(), "output")
    assert [t["ticket_id"] for t in out[("state/outreach.json", "tickets")]] == ["T-2026-12-PO-002-001-MISSING_DATA"]


def test_a_handoff_leaves_out_what_was_never_written(tmp_path, monkeypatch, pdfs):
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run", cases=[_case("PO-002-001", "DETECTED")])))
    body = _handoff(TestClient(api.app), "PO-002-001", "invoice-lookup").json()
    assert body["output"] == []
    assert ("state/cases.json", "obligation") in _parts(body, "input")


def test_a_handoff_input_is_only_what_was_visible_when_the_agent_ran(tmp_path, monkeypatch, pdfs):
    root = write_run(tmp_path / "run")
    late = [{**i, "available_at": "2027-01-10"} if i["invoice_id"] == "INV-MINT-DEC" else i for i in INVOICES]
    (root / "db" / "invoices.json").write_text(json.dumps(late))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(root))
    client, key = TestClient(api.app), ("db/invoices.json", "invoices on this PO line")
    assert key not in _parts(_handoff(client, "PO-001-001", "estimation").json(), "input")   # closed 01-05
    settled = _parts(_handoff(client, "PO-001-001", "settlement").json(), "input")          # settled 01-15
    assert [i["invoice_id"] for i in settled[key]] == ["INV-MINT-DEC"]


def _chain(client, case_key):
    return client.get(f"/api/cases/{P}/{case_key}/handoff")


def _steps(client, case_key):
    return _chain(client, case_key).json()["steps"]


def test_the_chain_is_the_agents_in_the_order_they_ran(client):
    """With one timestamp and one entry per worker, the chain is the documents, then the log, in order."""
    steps = _steps(client, "PO-001-001")
    assert [s["agent"] for s in steps] == ["evidence", "detection", "invoice-lookup", "classification",
                                           "estimation", "settlement"]
    assert steps[0]["result"] == "CTR-001, INV-MINT-DEC"
    alone = _handoff(client, "PO-001-001", "estimation").json()
    assert steps[4]["input"] == alone["input"]
    assert _parts(steps[4], "output")[("state/cases.json", "estimate")] == CASES[0]["estimate"]


FEB2, FEB5 = "2027-02-02T12:00:00Z", "2027-02-05T12:00:00Z"
REPLY = "REPLY-T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED"
EXPLAINED = "contract CTR-001 v2 sets 1400 from 2026-12-01: the vendor changed the price"


def _entry(at, worker, question, answer, action=""):
    return {"at": at, "worker": worker, "kind": "RULE", "question": question, "answer": answer,
            "confidence": None, "action": action}


def write_price_change(root):
    """Mintlify's December: accrued at the contract's 1200, billed 1400, the vendor asked, the reply explains."""
    log = [_entry(CLOSE_AT, "detection", "Is this PO line owed for the period?", ["PO validity covers period"]),
           _entry(CLOSE_AT, "invoice_lookup", "Is there an invoice on the AP or in the queue?", "NO_INVOICE"),
           _entry(CLOSE_AT, "classifier", "What do the PO columns say?", "RECURRING_FIXED"),
           _entry(CLOSE_AT, "estimation", "Base formula for RECURRING_FIXED?", "1200", "CONTRACT_RATE"),
           _entry(CLOSE_AT, "estimation", "1200.00 = 1200", "ESTIMATED", "ESTIMATE_REQUIRED -> ESTIMATED"),
           _entry(CLOSE_AT, "runner", "period closed", "CLOSED", "JOURNALED -> CLOSED"),
           _entry(FEB2, "settlement", "Why does the actual differ from the accrual?", "EXTERNAL_CHANGE",
                  "true-up +200.00"),
           _entry(FEB2, "settlement", "actual 1400.00 vs accrued 1200.00: EXTERNAL_CHANGE", "SETTLED",
                  "CLOSED -> SETTLED"),
           _entry(FEB5, "outreach", "Has T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED been answered?", REPLY,
                  "VARIANCE_UNEXPLAINED ANSWERED"),
           _entry(FEB5, "settlement", "Does the answer explain the variance?", True, EXPLAINED)]
    case = {**CASES[0], "decision_log": log,
            "settlement": {**CASES[0]["settlement"], "settled_at": FEB2,
                           "ticket_id": "T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED"}}
    ticket = {"ticket_id": "T-2026-12-PO-001-001-VARIANCE_UNEXPLAINED", "case_id": case["case_id"], "period": P,
              "reason": "VARIANCE_UNEXPLAINED", "asked_of": "VENDOR", "to": "Mintlify", "question": "What changed?",
              "message": None, "blocking": False, "deadline": "2027-02-12T12:00:00Z", "state": "ANSWERED",
              "opened_at": FEB2, "answered_at": FEB5, "answered_by_doc": REPLY, "expired_at": None}
    write_run(root, cases=[case], tickets=[ticket])
    docs = [d for d in DOCUMENTS if d["po_line_id"] == "PO-001-001"]
    docs = [{**d, "available_at": "2027-02-01"} if d["doc_id"] == "INV-MINT-DEC" else d for d in docs]
    docs.append({"doc_id": REPLY, "doc_type": "AMENDMENT", "vendor_id": "V001", "po_line_id": "PO-001-001",
                 "quality": "OK", "reasons": [], "applied_to": "contracts", "available_at": "2027-02-03",
                 "record": {"monthly_rate": 1400.0}})
    (root / "db" / "documents.json").write_text(json.dumps(docs))
    contracts = [CONTRACTS[0], {**CONTRACTS[1], "source_doc": REPLY, "available_at": "2027-02-03"}]
    (root / "db" / "contracts.json").write_text(json.dumps(contracts))
    invoices = [{**i, "available_at": "2027-02-01"} if i["invoice_id"] == "INV-MINT-DEC" else i for i in INVOICES]
    (root / "db" / "invoices.json").write_text(json.dumps(invoices))
    return root


@pytest.fixture
def price_change(tmp_path, monkeypatch, pdfs):
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_price_change(tmp_path / "run")))
    return TestClient(api.app)


def test_the_chain_tells_a_variance_in_the_order_it_happened(price_change):
    steps = _steps(price_change, "PO-001-001")
    assert [(s["agent"], s["at"][:10], s["result"]) for s in steps] == [
        ("evidence", CLOSE_AT[:10], "CTR-001"),
        ("detection", "2027-01-05", "PO validity covers period"),
        ("invoice-lookup", "2027-01-05", "NO_INVOICE"),
        ("classification", "2027-01-05", "RECURRING_FIXED"),
        ("estimation", "2027-01-05", "1200.00 = 1200"),
        ("close", "2027-01-05", "period closed"),
        ("evidence", "2027-02-01", "INV-MINT-DEC"),
        ("settlement", "2027-02-02", "actual 1400.00 vs accrued 1200.00: EXTERNAL_CHANGE"),
        ("outreach", "2027-02-02", "asked Mintlify: What changed?"),
        ("evidence", "2027-02-03", REPLY),
        ("outreach", "2027-02-05", "VARIANCE_UNEXPLAINED ANSWERED"),
        ("settlement", "2027-02-05", EXPLAINED)]


def test_a_step_reads_only_what_there_was_at_its_own_moment(price_change):
    steps = _steps(price_change, "PO-001-001")
    contracts = ("db/contracts.json", "contract versions of this line")
    invoices = ("db/invoices.json", "invoices on this PO line")
    estimation, first, asked, reply, _, second = steps[4], steps[7], steps[8], steps[9], steps[10], steps[11]
    assert invoices not in _parts(estimation, "input")                    # the close never saw the 1400 invoice
    assert [c["version"] for c in _parts(estimation, "input")[contracts]] == [1]
    assert [c["version"] for c in _parts(first, "input")[contracts]] == [1]        # still 1200 when it rechecked
    assert ("state/cases.json", "settlement") in _parts(asked, "input")   # the variance is why it asked
    assert [r["version"] for r in _parts(reply, "output")[("db/contracts.json", "rows written from these documents")]] == [2]
    assert [c["version"] for c in _parts(second, "input")[contracts]] == [1, 2]    # the reply brought v2
    assert [d["doc_id"] for d in _parts(second, "input")[("db/documents.json", "replies received")]] == [REPLY]


def test_a_step_writes_its_own_decisions_only(price_change):
    steps = _steps(price_change, "PO-001-001")
    first, second = steps[7], steps[11]
    log = ("state/cases.json", "decision_log")
    assert [d["at"] for d in _parts(first, "output")[log]] == [FEB2, FEB2]
    assert [d["answer"] for d in _parts(second, "output")[log]] == [True]


def test_each_step_carries_the_facts_a_reader_needs(price_change):
    """The story page writes its sentences from these; nothing in them is wording."""
    facts = [s["facts"] for s in _steps(price_change, "PO-001-001")]
    arrived, _, lookup, classified, estimated, closed, invoice, variance, asked, reply, answered, explained = facts
    assert [d["doc_id"] for d in arrived["documents"]] == ["CTR-001"] and arrived["documents"][0]["text"] is None
    assert lookup == {"kind": "invoice-lookup", "result": "NO_INVOICE", "invoice_ids": [], "invoiced_amount": 0}
    assert classified["final"] == "RECURRING_FIXED" and classified["label"] == "Recurring fixed"
    assert estimated == {"kind": "estimation", "outcome": "ESTIMATED", "estimator": "CONTRACT_RATE",
                         "estimator_label": "Contract rate", "calculation": "1200", "amount": 1200.0,
                         "missing": None, "forced": False, "basis": None}
    assert closed == {"kind": "close", "amount": 1200.0}
    assert invoice["documents"][0]["doc_id"] == "INV-MINT-DEC"
    assert variance["kind"] == "variance" and (variance["actual"], variance["accrued"], variance["true_up"]) == (
        1400.0, 1200.0, 200.0)
    assert variance["cause"] == "EXTERNAL_CHANGE" and variance["recheck"]["prior_invoice_amounts"] == [1200.0]
    assert asked["kind"] == "ask" and (asked["to"], asked["asked_of"], asked["question"]) == (
        "Mintlify", "VENDOR", "What changed?")
    assert reply["documents"][0]["is_reply"] is True
    assert answered == {"kind": "answer", "state": "ANSWERED", "to": "Mintlify", "asked_of": "VENDOR",
                        "reason": "VARIANCE_UNEXPLAINED", "answered_by_doc": REPLY}
    assert explained == {"kind": "explanation", "explained": True, "explanation": CASES[0]["settlement"]["explanation"]}


def test_a_step_that_could_not_price_says_what_it_waits_for(tmp_path, monkeypatch, pdfs):
    log = [_entry(CLOSE_AT, "estimation", "no amount yet: delivery report for the period", "OUTREACH_PENDING",
                  "ESTIMATE_REQUIRED -> OUTREACH_PENDING"),
           _entry(CLOSE_AT, "outreach", "Has T-2026-12-CAMPAIGN-004-001-MISSING_DATA been answered?", False,
                  "MISSING_DATA EXPIRED"),
           _entry(CLOSE_AT, "estimation", "30000.00 = 30000", "ESTIMATED", "FORCED_ESTIMATE -> ESTIMATED")]
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run", cases=[{**CASES[3], "decision_log": log}])))
    waiting, _, chased, forced = [s["facts"] for s in _steps(TestClient(api.app), "CAMPAIGN-004-001")]
    assert waiting["outcome"] == "OUTREACH_PENDING" and waiting["amount"] is None
    assert waiting["missing"] == "delivery report for the period"
    assert chased["kind"] == "answer" and chased["state"] == "EXPIRED"
    assert forced["outcome"] == "ESTIMATED" and forced["forced"] is True and forced["basis"] == "PO budget (overall limit)"


def test_the_chain_names_the_case_for_a_page_header(client):
    body = _chain(client, "PO-001-001").json()
    assert (body["vendor_name"], body["title"], body["period"]) == ("Mintlify", "December 2026 accrual", P)


def test_an_ask_comes_before_outreach_checks_for_its_answer(tmp_path, monkeypatch, pdfs):
    """Meta's December: the ticket was opened before the close ran, and the log says when it was chased."""
    log = [_entry(CLOSE_AT, "estimation", "no amount yet: delivery report for the period", "OUTREACH_PENDING",
                  "ESTIMATE_REQUIRED -> OUTREACH_PENDING"),
           _entry(CLOSE_AT, "outreach", "Has T-2026-12-CAMPAIGN-004-001-MISSING_DATA been answered?", False,
                  "MISSING_DATA EXPIRED"),
           _entry(CLOSE_AT, "estimation", "30000.00 = 30000", "ESTIMATED", "FORCED_ESTIMATE -> ESTIMATED")]
    case = {**CASES[3], "decision_log": log}
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run", cases=[case])))
    steps = _steps(TestClient(api.app), "CAMPAIGN-004-001")
    assert [(s["agent"], s["result"]) for s in steps] == [
        ("estimation", "no amount yet: delivery report for the period"),
        ("outreach", "asked maria.gomez: What was delivered?"),
        ("outreach", "MISSING_DATA EXPIRED"),
        ("estimation", "30000.00 = 30000")]


def test_the_chain_carries_the_situation_and_its_numbers(client):
    situation = _chain(client, "PO-001-001").json()["situation"]
    assert situation == {"category": "RECURRING_FIXED", "label": "Recurring fixed", "estimator": "CONTRACT_RATE",
                         "calculation": "1200", "amount": 1200.0, "missing": None, "flags": [],
                         "accrued": 1200.0, "actual": 1400.0, "true_up": 200.0, "cause": "EXTERNAL_CHANGE",
                         "numbers": [1200.0, 1400.0, 200.0]}


def test_the_situations_numbers_are_read_off_the_calculation(tmp_path, monkeypatch, pdfs):
    usage = _case("PO-002-001", "ESTIMATED", invoice_match=MATCH_NONE,
                  classification=_classification("RECURRING_VARIABLE"),
                  estimate=_estimate("RECURRING_VARIABLE", "USAGE_EXTRAPOLATED", 17360.0, "700000 / 25 * 31 * 0.02"))
    goods = _case("PO-003-001", "ESTIMATED", invoice_match=MATCH_NONE,
                  classification=_classification("ONE_TIME_FIXED"),
                  estimate=_estimate("ONE_TIME_FIXED", "THREE_WAY_MATCH", 32000.0, "1600 * (20 - 0)"))
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run", cases=[usage, goods])))
    client = TestClient(api.app)
    assert _chain(client, "PO-002-001").json()["situation"]["numbers"] == [700000.0, 25.0, 31.0, 0.02, 17360.0]
    assert _chain(client, "PO-003-001").json()["situation"]["numbers"] == [1600.0, 20.0, 32000.0]   # never 0


def test_the_chain_lists_the_periods_cases_to_switch_between(client):
    body = _chain(client, "PO-002-001").json()
    assert [(c["case_id"], c["vendor_name"], c["category"]) for c in body["cases"]] == [
        (f"{P}/CAMPAIGN-004-001", "Meta", "ONE_TIME_VARIABLE"), (f"{P}/PO-001-001", "Mintlify", "RECURRING_FIXED"),
        (f"{P}/PO-002-001", "OpenAI", "RECURRING_VARIABLE"), (f"{P}/PO-003-001", "ASUS", "ONE_TIME_FIXED")]
    assert all(c["label"] for c in body["cases"])
    assert _chain(client, "NOPE-001").status_code == 404


# --------------------------------------------------------------------------------------------------------------
# The vendor story: every case of one vendor on one timeline, cut at the end of a calendar month
# --------------------------------------------------------------------------------------------------------------


def _story(client, **params):
    return client.get("/api/story", params=params)


def test_a_story_shows_nothing_dated_after_the_month_it_is_cut_at(price_change):
    january = _story(price_change, vendor="V001", through="2027-01").json()
    assert [s["agent"] for s in january["steps"]] == ["evidence", "detection", "invoice-lookup", "classification",
                                                      "estimation", "close"]
    assert all(s["at"][:7] <= "2027-01" for s in january["steps"]) and january["later"] == 6
    assert (january["through"], january["through_day"], january["next_month"]) == ("2027-01", "2027-01-31", "2027-02")
    february = _story(price_change, vendor="V001", through="2027-02").json()
    assert len(february["steps"]) == 12 and february["later"] == 0 and february["next_month"] is None


def test_a_story_knows_which_case_and_which_step_each_event_is(price_change):
    steps = _story(price_change, vendor="V001", through="2027-02").json()["steps"]
    assert {s["case_id"] for s in steps} == {f"{P}/PO-001-001"} and steps[0]["case_title"] == "December 2026 accrual"
    assert [s["case_step"] for s in steps] == list(range(12))       # where the JSON drawer opens


def test_a_story_says_where_the_vendor_stands_at_the_cut(price_change):
    january = _story(price_change, vendor="V001", through="2027-01").json()["standing"]
    assert january == {"accrued_open": 1200.0, "true_ups": 0, "open_questions": 0}
    february = _story(price_change, vendor="V001", through="2027-02").json()["standing"]
    assert february == {"accrued_open": 0, "true_ups": 200.0, "open_questions": 0}


def test_a_story_offers_every_calendar_month_anything_happened_in(price_change):
    body = _story(price_change, vendor="V001").json()
    assert [m["month"] for m in body["months"]] == ["2027-01", "2027-02"]
    assert body["months"][0]["label"] == "January 2027" and body["through"] == "2027-02"   # default: the latest


def test_a_story_lists_the_vendors_for_its_panel(client):
    body = _story(client, vendor="V002", through="2027-01").json()
    assert [(v["vendor_id"], v["vendor_name"]) for v in body["vendors"]] == [
        ("V003", "ASUS"), ("V004", "Meta"), ("V001", "Mintlify"), ("V002", "OpenAI")]
    assert body["vendor_name"] == "OpenAI" and all(v["events"] > 0 for v in body["vendors"])
    assert next(v for v in body["vendors"] if v["vendor_id"] == "V002")["open_questions"] == 1


def test_a_document_arrives_once_however_many_months_cite_it(tmp_path, monkeypatch, pdfs):
    november = {**CASES[0], "case_id": "2026-11/PO-001-001", "period": "2026-11", "as_of": "2026-12-05T12:00:00Z",
                "decision_log": [_entry("2026-12-05T12:00:00Z", "detection", "owed?", ["covers period"])],
                "settlement": None}
    december = {**CASES[0], "decision_log": [_entry(CLOSE_AT, "detection", "owed?", ["covers period"])]}
    monkeypatch.setenv("TRUEUP_RUN_DIR", str(write_run(tmp_path / "run", cases=[november, december], tickets=[])))
    steps = _story(TestClient(api.app), vendor="V001").json()["steps"]
    shown = [d["doc_id"] for s in steps if s["facts"]["kind"] == "documents" for d in s["facts"]["documents"]]
    assert sorted(shown) == ["CTR-001", "INV-MINT-DEC"]
    assert [s["case_id"][:7] for s in steps if s["agent"] == "detection"] == ["2026-11", "2026-12"]


def test_a_story_opened_from_a_case_shows_that_case_whole(price_change):
    body = _story(price_change, case=f"{P}/PO-001-001").json()
    assert body["vendor_id"] == "V001" and body["through"] == "2027-02" and body["later"] == 0


def test_a_story_of_nobody_is_a_404(client):
    assert _story(client, vendor="V999").status_code == 404
    assert _story(client).status_code == 404


def test_a_case_row_opens_the_vendors_story_cut_at_the_rows_month(client):
    rows = client.get("/api/cases").json()["CASES"]
    assert next(r for r in rows if r["vendor"] == "Mintlify")["href"] == f"/close/story?vendor=V001&through={P}"


def test_an_unknown_handoff_agent_is_a_404(client):
    assert _handoff(client, "PO-001-001", "journal").status_code == 404
    assert client.get(f"/api/cases/{P}/NOPE-001/handoff/detection").status_code == 404
