import json

import pytest

from system import events, safe_math, store
from system.workspace import Workspace, covers, days_in, period_bounds, prev_periods


def make_ws(tmp_path):
    return Workspace(
        pdf_root=tmp_path / "pdf",
        seed_dir=tmp_path / "seed",
        db_dir=tmp_path / "db",
        state_dir=tmp_path / "state",
        packages_dir=tmp_path / "close_packages",
    )


# --- workspace.py ---------------------------------------------------------


def test_period_bounds():
    assert period_bounds("2026-12") == ("2026-12-01", "2026-12-31")
    assert period_bounds("2027-02")[1] == "2027-02-28"


def test_days_in():
    assert days_in("2026-12") == 31


def test_prev_periods():
    assert prev_periods("2027-01", 3) == ["2026-10", "2026-11", "2026-12"]


def test_covers_within_bounds():
    assert covers("2026-09-01", "2027-08-31", "2026-12") is True


def test_covers_open_start_none():
    assert covers("2026-12-01", None, "2026-11") is False


def test_covers_open_end_none():
    assert covers(None, "2026-11-30", "2026-12") is False


def test_covers_partial_overlap():
    assert covers("2026-12-15", "2026-12-20", "2026-12") is True


def test_covers_no_end_date_is_open_ended():
    assert covers("2026-09-01", None, "2026-12") is True


def test_covers_no_start_and_no_end_is_always_open():
    assert covers(None, None, "2026-12") is True


def test_covers_end_before_period_still_false_with_open_start():
    assert covers(None, "2026-11-30", "2026-12") is False


def test_covers_start_after_period_still_false_with_open_end():
    assert covers("2026-12-01", None, "2026-11") is False


def test_workspace_default_paths():
    ws = Workspace.default()
    assert ws.pdf_root.name == "startup_minimal_data"
    assert ws.pdf_root.parent.name == "pdf"
    assert ws.seed_dir == (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "seed"
    )
    assert ws.db_dir.name == "db"
    assert ws.state_dir.name == "state"
    assert ws.packages_dir.name == "close_packages"


# --- store.py --------------------------------------------------------------


def test_load_table_missing_file_returns_empty_list(tmp_path):
    ws = make_ws(tmp_path)
    assert store.load_table(ws, "vendors") == []


def test_load_table_rejects_unknown_name(tmp_path):
    ws = make_ws(tmp_path)
    with pytest.raises(ValueError):
        store.load_table(ws, "not_a_real_table")


def test_save_then_load_round_trips(tmp_path):
    ws = make_ws(tmp_path)
    rows = [{"Vendor_ID": "V001", "Vendor_Name": "Mintlify"}]
    store.save_table(ws, "vendors", rows)
    assert store.load_table(ws, "vendors") == rows


def test_upsert_replaces_row_with_same_key():
    rows = [{"Vendor_ID": "V001", "Vendor_Name": "Mintlify"}]
    store.upsert(rows, {"Vendor_ID": "V001", "Vendor_Name": "Mintlify Inc"}, ("Vendor_ID",))
    assert rows == [{"Vendor_ID": "V001", "Vendor_Name": "Mintlify Inc"}]


def test_upsert_appends_new_row():
    rows = [{"Vendor_ID": "V001", "Vendor_Name": "Mintlify"}]
    store.upsert(rows, {"Vendor_ID": "V002", "Vendor_Name": "OpenAI"}, ("Vendor_ID",))
    assert rows == [
        {"Vendor_ID": "V001", "Vendor_Name": "Mintlify"},
        {"Vendor_ID": "V002", "Vendor_Name": "OpenAI"},
    ]


def test_upsert_composite_key():
    rows = [{"Program": "Ramp", "Period": "2026-12", "Settled_Balance": 100}]
    store.upsert(
        rows,
        {"Program": "Ramp", "Period": "2026-12", "Settled_Balance": 200},
        ("Program", "Period"),
    )
    assert rows == [{"Program": "Ramp", "Period": "2026-12", "Settled_Balance": 200}]

    store.upsert(
        rows,
        {"Program": "Ramp", "Period": "2027-01", "Settled_Balance": 50},
        ("Program", "Period"),
    )
    assert len(rows) == 2


def test_load_state_default_when_missing(tmp_path):
    ws = make_ws(tmp_path)
    assert store.load_state(ws, "ledger.json", []) == []
    assert store.load_state(ws, "config.json", {"a": 1}) == {"a": 1}


def test_save_then_load_state_round_trips(tmp_path):
    ws = make_ws(tmp_path)
    obj = {"cases": [1, 2, 3]}
    store.save_state(ws, "ledger.json", obj)
    assert store.load_state(ws, "ledger.json", None) == obj


def test_save_table_creates_parent_dirs(tmp_path):
    ws = make_ws(tmp_path)
    assert not ws.db_dir.exists()
    store.save_table(ws, "vendors", [])
    assert ws.db_dir.exists()


def test_save_state_creates_parent_dirs(tmp_path):
    ws = make_ws(tmp_path)
    assert not ws.state_dir.exists()
    store.save_state(ws, "ledger.json", [])
    assert ws.state_dir.exists()


# --- events.py ---------------------------------------------------------


def test_events_log_and_read_since(tmp_path):
    ws = make_ws(tmp_path)
    events.log(ws, "evidence", 1, "first message", period="2026-12")
    events.log(ws, "detection", 4, "second message", period="2026-12")
    result = events.read(ws, since=1)
    assert len(result) == 1
    assert result[0]["n"] == 2
    assert result[0]["agent"] == "detection"
    assert result[0]["step"] == 4
    assert result[0]["period"] == "2026-12"
    assert result[0]["message"] == "second message"
    assert "ts" in result[0]


def test_events_read_all_when_since_zero(tmp_path):
    ws = make_ws(tmp_path)
    events.log(ws, "evidence", 1, "first")
    events.log(ws, "evidence", 2, "second")
    result = events.read(ws, since=0)
    assert len(result) == 2
    assert result[0]["n"] == 1
    assert result[1]["n"] == 2


# --- safe_math.py --------------------------------------------------------


def test_evaluate_division_multiplication():
    assert safe_math.evaluate("700000 / 25 * 31 * 0.02") == 17360.0


def test_evaluate_parentheses_average():
    assert safe_math.evaluate("(14200 + 16800 + 15500) / 3") == 15500.0


def test_evaluate_strips_dollar_and_commas():
    assert safe_math.evaluate("$1,600 * 20") == 32000.0


def test_evaluate_rejects_import():
    with pytest.raises(ValueError):
        safe_math.evaluate("__import__('os')")


def test_evaluate_rejects_power():
    with pytest.raises(ValueError):
        safe_math.evaluate("2 ** 8")


# --- seed files --------------------------------------------------------


def seed_path(name):
    return (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "seed"
        / name
    )


def test_seed_vendors():
    rows = json.loads(seed_path("vendors.json").read_text())
    assert len(rows) == 5
    by_id = {r["Vendor_ID"]: r["Vendor_Name"] for r in rows}
    assert by_id == {
        "V001": "Mintlify",
        "V002": "OpenAI",
        "V003": "ASUS",
        "V004": "Meta",
        "V005": "Twilio",
    }


def test_seed_po_headers():
    rows = json.loads(seed_path("po_headers.json").read_text())
    assert len(rows) == 5
    by_po = {r["PO_Number"]: r for r in rows}
    assert by_po["PO-001"] == {
        "PO_Number": "PO-001",
        "Vendor_ID": "V001",
        "Order_Type": "FO",
        "Validity_Start": "2026-09-01",
        "Validity_End": "2027-08-31",
        "Requester": "sam.lee",
        "Cost_Center_Owner": "priya.shah",
        "Created_Date": "2026-08-25",
        "Status": "Open",
        "Total_Amount": 14400,
    }
    assert by_po["PO-003"]["Validity_Start"] is None
    assert by_po["PO-003"]["Validity_End"] is None
    assert by_po["CAMPAIGN-004"]["Vendor_ID"] == "V004"
    assert by_po["PO-005"]["Total_Amount"] == 5000


def test_seed_po_lines():
    rows = json.loads(seed_path("po_lines.json").read_text())
    assert len(rows) == 5
    by_id = {r["PO_Line_ID"]: r for r in rows}
    assert set(by_id) == {
        "PO-001-001",
        "PO-002-001",
        "PO-003-001",
        "CAMPAIGN-004-001",
        "PO-005-001",
    }
    for r in rows:
        assert r["Quantity_Billed"] == 0
    asus = by_id["PO-003-001"]
    assert asus["Item_Category"] == ""
    assert asus["Contract_ID"] is None
    assert asus["GR_Based_IV"] is True
    assert asus["Quantity_Ordered"] == 25
    assert asus["Unit_Price"] == 1600
    assert asus["Quantity_Received"] == 0
    openai_line = by_id["PO-002-001"]
    assert openai_line["Contract_ID"] == "CTR-002"
    assert openai_line["GR_Based_IV"] is False
    assert openai_line["Quantity_Ordered"] is None


def test_seed_card_statements():
    rows = json.loads(seed_path("card_statements.json").read_text())
    assert len(rows) == 1
    assert rows[0] == {
        "Program": "Ramp",
        "Period": "2026-12",
        "Settled_Balance": 8450.25,
        "Pending_Balance": 1210.00,
    }
