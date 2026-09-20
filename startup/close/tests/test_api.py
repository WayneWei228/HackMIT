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
EVIDENCE_KEYS = {"CASE", "FACTS", "MATCH"}
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


def test_href_is_the_url_encoded_case_id(client):
    hrefs = {r["vendor"]: r["href"] for r in client.get("/api/cases").json()["CASES"]}
    assert hrefs["Mintlify"] == "/close?case=2026-12%2FPO-001-001"


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
