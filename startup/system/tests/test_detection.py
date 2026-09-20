from system import detection, evidence, invoice_lookup, store
from system.tests.fakes import make_ws


# --- invoice_lookup.find_invoice --------------------------------------------


def test_find_invoice_matches_po_line_and_period(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    store.save_table(
        ws,
        "ap_invoices",
        [
            {
                "Invoice_ID": "INV-MINTLIFY-SEP",
                "Vendor_ID": "V001",
                "PO_Line_ID": "PO-001-001",
                "Service_Period": "2026-09",
                "Amount": 1200,
                "Received_Date": "2026-09-28",
            }
        ],
    )

    row = invoice_lookup.find_invoice(ws, "PO-001-001", "2026-09")
    assert row["Invoice_ID"] == "INV-MINTLIFY-SEP"


def test_find_invoice_returns_none_when_no_match(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    assert invoice_lookup.find_invoice(ws, "PO-001-001", "2026-09") is None


def test_find_invoice_ignores_wrong_period(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    store.save_table(
        ws,
        "ap_invoices",
        [
            {
                "Invoice_ID": "INV-MINTLIFY-OCT",
                "Vendor_ID": "V001",
                "PO_Line_ID": "PO-001-001",
                "Service_Period": "2026-10",
                "Amount": 1200,
                "Received_Date": "2026-10-28",
            }
        ],
    )
    assert invoice_lookup.find_invoice(ws, "PO-001-001", "2026-09") is None


# --- detection.detect --------------------------------------------------------


def test_september_invoices_produce_two_invoiced_cases(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    store.save_table(
        ws,
        "ap_invoices",
        [
            {
                "Invoice_ID": "INV-MINTLIFY-SEP",
                "Vendor_ID": "V001",
                "PO_Line_ID": "PO-001-001",
                "Service_Period": "2026-09",
                "Amount": 1200,
                "Received_Date": "2026-09-28",
            },
            {
                "Invoice_ID": "INV-OPENAI-SEP",
                "Vendor_ID": "V002",
                "PO_Line_ID": "PO-002-001",
                "Service_Period": "2026-09",
                "Amount": 14200,
                "Received_Date": "2026-09-28",
            },
        ],
    )

    cases = detection.detect(ws, "2026-09")

    assert len(cases) == 2
    by_line = {c["po_line_id"]: c for c in cases}
    assert by_line["PO-001-001"]["state"] == "INVOICED"
    assert by_line["PO-001-001"]["amount"] == 1200.0
    assert by_line["PO-001-001"]["evidence"] == ["INV-MINTLIFY-SEP"]
    assert by_line["PO-002-001"]["state"] == "INVOICED"
    assert by_line["PO-002-001"]["amount"] == 14200.0
    assert by_line["PO-002-001"]["evidence"] == ["INV-OPENAI-SEP"]


def _seed_december(ws):
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


def test_december_with_no_invoices_produces_six_open_cases(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december(ws)

    cases = detection.detect(ws, "2026-12")

    case_ids = {c["case_id"] for c in cases}
    assert case_ids == {
        "2026-12/PO-001-001",
        "2026-12/PO-002-001",
        "2026-12/PO-003-001",
        "2026-12/CAMPAIGN-004-001",
        "2026-12/PO-005-001",
        "2026-12/CARD/Ramp",
    }
    assert all(c["state"] == "OPEN" for c in cases)


def test_po_003_with_zero_quantity_received_produces_no_case(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    evidence.pull_seed(ws, "2026-12")
    # PO-003-001 keeps its seeded Quantity_Received of 0.

    cases = detection.detect(ws, "2026-12")

    po_line_ids = {c["po_line_id"] for c in cases}
    assert "PO-003-001" not in po_line_ids


def test_closed_header_produces_no_case(tmp_path):
    ws = make_ws(tmp_path)
    evidence.pull_seed(ws, "2026-09")
    evidence.pull_seed(ws, "2026-12")

    headers = store.load_table(ws, "po_headers")
    headers.append(
        {
            "PO_Number": "PO-999",
            "Vendor_ID": "V001",
            "Order_Type": "FO",
            "Validity_Start": "2026-01-01",
            "Validity_End": "2027-01-01",
            "Requester": "sam.lee",
            "Cost_Center_Owner": "priya.shah",
            "Created_Date": "2026-01-01",
            "Status": "Closed",
            "Total_Amount": 1000,
        }
    )
    store.save_table(ws, "po_headers", headers)

    lines = store.load_table(ws, "po_lines")
    lines.append(
        {
            "PO_Line_ID": "PO-999-001",
            "PO_Number": "PO-999",
            "Item_Category": "P",
            "Contract_ID": None,
            "GR_Based_IV": False,
            "GL_Account_Code": "610200",
            "Quantity_Ordered": None,
            "Unit_Price": 100,
            "Quantity_Received": None,
            "Quantity_Billed": 0,
            "Line_Description": "closed header line",
        }
    )
    store.save_table(ws, "po_lines", lines)

    cases = detection.detect(ws, "2026-12")

    po_line_ids = {c["po_line_id"] for c in cases}
    assert "PO-999-001" not in po_line_ids


def test_detect_is_idempotent(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december(ws)

    detection.detect(ws, "2026-12")
    cases = detection.detect(ws, "2026-12")

    case_ids = [c["case_id"] for c in cases]
    assert sorted(case_ids) == sorted(set(case_ids))
    assert len(case_ids) == 6


def test_settled_case_is_left_untouched(tmp_path):
    ws = make_ws(tmp_path)
    _seed_december(ws)

    settled_case = {
        "case_id": "2026-12/PO-001-001",
        "period": "2026-12",
        "kind": "PO_LINE",
        "po_line_id": "PO-001-001",
        "po_number": "PO-001",
        "vendor_id": "V001",
        "vendor_name": "Mintlify",
        "state": "SETTLED",
        "category": "RECURRING_FIXED",
        "classification": {"columns": "RECURRING_FIXED", "model": "RECURRING_FIXED", "confidence": 0.9, "contradictions": []},
        "amount": 1200.0,
        "calculation": "1200",
        "complete": True,
        "missing": None,
        "evidence": ["INV-MINTLIFY-DEC"],
        "lessons_applied": [],
        "explanation": "settled from prior run",
        "settlement": {"actual": 1200.0, "variance": 0.0, "settled_by": "INV-MINTLIFY-DEC", "root_cause": None, "lesson_id": None},
    }
    store.save_state(ws, "ledger.json", [settled_case])

    cases = detection.detect(ws, "2026-12")

    by_id = {c["case_id"]: c for c in cases}
    assert by_id["2026-12/PO-001-001"] == settled_case
    assert len(cases) == 6
