from system import classifier, detection, evidence, store
from system.tests.fakes import FakeModel, make_ws

_CATEGORY_BY_LINE = {
    "PO-001-001": "RECURRING_FIXED",
    "PO-002-001": "RECURRING_VARIABLE",
    "PO-003-001": "ONE_TIME_FIXED",
    "CAMPAIGN-004-001": "ONE_TIME_VARIABLE",
    "PO-005-001": "ONE_TIME_FIXED",
}


def _seed_december_with_contracts(ws):
    evidence.pull_seed(ws, "2026-09")
    evidence.pull_seed(ws, "2026-12")

    lines = store.load_table(ws, "po_lines")
    for line in lines:
        if line["PO_Line_ID"] == "PO-003-001":
            line["Quantity_Received"] = 20
    store.save_table(ws, "po_lines", lines)

    store.save_table(
        ws,
        "activity",
        [
            {
                "Document_ID": "META-DELIVERY-DEC",
                "PO_Line_ID": "CAMPAIGN-004-001",
                "Vendor_ID": "V004",
                "Service_Period": "2026-12",
                "Coverage_Start": "2026-12-01",
                "Coverage_End": "2026-12-31",
                "Quantity": None,
                "Value": 12000.0,
                "Replaces": None,
                "Replaced_By": None,
            }
        ],
    )

    store.save_table(
        ws,
        "contracts",
        [
            {
                "Contract_ID": "CTR-001",
                "Vendor_Name": "Mintlify",
                "Version": 1,
                "Monthly_Rate": 1200,
                "Unit_Rate": None,
                "Effective_Start": "2026-09-01",
                "Effective_End": None,
                "Status": "Active",
            },
            {
                "Contract_ID": "CTR-002",
                "Vendor_Name": "OpenAI",
                "Version": 1,
                "Monthly_Rate": None,
                "Unit_Rate": 0.02,
                "Effective_Start": "2026-09-01",
                "Effective_End": None,
                "Status": "Active",
            },
        ],
    )


# --- classifier.classify_columns --------------------------------------------


def test_classify_columns_fo_line_with_no_validity_returns_none():
    header = {"Order_Type": "FO", "Validity_Start": None, "Validity_End": None}
    line = {
        "Item_Category": "B",
        "Contract_ID": None,
        "GR_Based_IV": False,
        "Quantity_Ordered": None,
        "Unit_Price": None,
    }

    category, contradictions = classifier.classify_columns(header, line)

    assert category is None
    assert contradictions


def test_classify_columns_branch_order_openai_limit_and_contract_linked_is_rv(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    header = next(h for h in store.load_table(ws, "po_headers") if h["PO_Number"] == "PO-002")
    line = next(l for l in store.load_table(ws, "po_lines") if l["PO_Line_ID"] == "PO-002-001")

    category, contradictions = classifier.classify_columns(header, line)

    assert category == "RECURRING_VARIABLE"
    assert contradictions == []


def test_classify_columns_five_seed_lines(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    headers = {h["PO_Number"]: h for h in store.load_table(ws, "po_headers")}
    lines = {l["PO_Line_ID"]: l for l in store.load_table(ws, "po_lines")}

    for line_id, expected in _CATEGORY_BY_LINE.items():
        line = lines[line_id]
        header = headers[line["PO_Number"]]
        category, contradictions = classifier.classify_columns(header, line)
        assert category == expected, f"{line_id}: expected {expected}, got {category}"
        assert contradictions == []


# --- classifier.extra_checks -------------------------------------------------


def test_extra_checks_limit_line_with_quantity_received_is_contradiction(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    header = next(h for h in store.load_table(ws, "po_headers") if h["PO_Number"] == "CAMPAIGN-004")
    line = dict(next(l for l in store.load_table(ws, "po_lines") if l["PO_Line_ID"] == "CAMPAIGN-004-001"))
    line["Quantity_Received"] = 3

    contradictions = classifier.extra_checks(ws, header, line, "2026-12")

    assert any("Quantity_Received" in c for c in contradictions)


def test_extra_checks_contract_id_missing_from_contracts_is_contradiction(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    header = next(h for h in store.load_table(ws, "po_headers") if h["PO_Number"] == "PO-001")
    line = next(l for l in store.load_table(ws, "po_lines") if l["PO_Line_ID"] == "PO-001-001")
    # contracts table is empty: CTR-001 was never ingested.

    contradictions = classifier.extra_checks(ws, header, line, "2026-09")

    assert any("CTR-001" in c for c in contradictions)


def test_extra_checks_header_total_mismatch_is_contradiction(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    header = dict(next(h for h in store.load_table(ws, "po_headers") if h["PO_Number"] == "PO-003"))
    header["Total_Amount"] = 99
    line = next(l for l in store.load_table(ws, "po_lines") if l["PO_Line_ID"] == "PO-003-001")

    contradictions = classifier.extra_checks(ws, header, line, "2026-12")

    assert any("99" in c for c in contradictions)


def test_extra_checks_clean_for_seed_lines_no_contradictions(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    headers = {h["PO_Number"]: h for h in store.load_table(ws, "po_headers")}
    lines = {l["PO_Line_ID"]: l for l in store.load_table(ws, "po_lines")}

    for line_id in _CATEGORY_BY_LINE:
        line = lines[line_id]
        header = headers[line["PO_Number"]]
        assert classifier.extra_checks(ws, header, line, "2026-12") == []


# --- classifier.run ----------------------------------------------------------


def test_run_classifies_five_seed_lines_and_card_case(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    detection.detect(ws, "2026-12")

    fake = FakeModel(
        read_description={
            line_id: {"category": category, "confidence": 0.9}
            for line_id, category in _CATEGORY_BY_LINE.items()
        }
    )

    classifier.run(ws, fake, "2026-12")

    ledger = store.load_state(ws, "ledger.json", [])
    by_id = {c["case_id"]: c for c in ledger}

    for line_id, expected in _CATEGORY_BY_LINE.items():
        case = by_id[f"2026-12/{line_id}"]
        assert case["category"] == expected
        assert case["classification"]["columns"] == expected
        assert case["classification"]["model"] == expected
        assert case["classification"]["confidence"] == 0.9
        assert case["classification"]["contradictions"] == []

    card_case = by_id["2026-12/CARD/Ramp"]
    assert card_case["category"] == "NON_PO"


def test_run_model_disagreement_keeps_columns_category_and_opens_ticket(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    detection.detect(ws, "2026-12")

    ticket_calls = []

    def fake_open_ticket(ws, case, reason, detail, suggested=None):
        ticket_calls.append((case["case_id"], reason, suggested))

    monkeypatch.setattr(classifier, "_open_ticket", fake_open_ticket)

    answers = dict(_CATEGORY_BY_LINE)
    answers["PO-005-001"] = "RECURRING_VARIABLE"  # disagrees with columns' ONE_TIME_FIXED
    fake = FakeModel(
        read_description={
            line_id: {"category": category, "confidence": 0.8} for line_id, category in answers.items()
        }
    )

    classifier.run(ws, fake, "2026-12")

    ledger = store.load_state(ws, "ledger.json", [])
    po_005 = next(c for c in ledger if c["po_line_id"] == "PO-005-001")
    assert po_005["category"] == "ONE_TIME_FIXED"
    assert po_005["classification"]["model"] == "RECURRING_VARIABLE"

    assert ticket_calls == [("2026-12/PO-005-001", "CLASSIFICATION_DISAGREEMENT", "RECURRING_VARIABLE")]

    calls_after_first_run = len(fake.calls)
    assert calls_after_first_run > 0

    classifier.run(ws, fake, "2026-12")
    assert len(fake.calls) == calls_after_first_run  # cached: no new model calls


def test_run_invalid_model_category_is_treated_as_no_answer(tmp_path, monkeypatch):
    ws = make_ws(tmp_path)
    _seed_december_with_contracts(ws)
    detection.detect(ws, "2026-12")

    ticket_calls = []
    monkeypatch.setattr(
        classifier, "_open_ticket", lambda ws, case, reason, detail, suggested=None: ticket_calls.append(case["case_id"])
    )

    answers = dict(_CATEGORY_BY_LINE)
    answers["PO-005-001"] = "NOT_A_REAL_CATEGORY"
    fake = FakeModel(
        read_description={
            line_id: {"category": category, "confidence": 0.5} for line_id, category in answers.items()
        }
    )

    classifier.run(ws, fake, "2026-12")

    ledger = store.load_state(ws, "ledger.json", [])
    po_005 = next(c for c in ledger if c["po_line_id"] == "PO-005-001")
    assert po_005["category"] == "ONE_TIME_FIXED"
    assert po_005["classification"]["model"] is None
    assert "2026-12/PO-005-001" not in ticket_calls
