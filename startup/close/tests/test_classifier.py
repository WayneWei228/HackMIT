import pytest

from close import classifier, detection, store

from .fakes import FakeLLM, make_ws

P = "2026-12"
YEAR = {"validity_start": "2026-09-01", "validity_end": "2027-08-31"}
NONE = {"validity_start": None, "validity_end": None}


def header(po, order_type, **kw):
    return {"po_number": po, "vendor_id": "V001", "order_type": order_type, "status": "Open", **NONE, **kw}


def line(po, item_category, description="", **kw):
    return {"po_line_id": f"{po}-001", "po_number": po, "item_category": item_category, "contract_id": None, "gr_required": False,
            "quantity_ordered": None, "unit_price": None, "quantity_received": None, "quantity_billed": 0,
            "line_description": description, **kw}


def says(category, confidence=0.95):
    return FakeLLM(read_description={"category": category, "confidence": confidence})


@pytest.mark.parametrize("hdr, ln, expected", [
    (header("A", "FO", **YEAR), line("A", "B"), "RECURRING_VARIABLE"),
    (header("B", "NB", validity_start="2026-12-01", validity_end="2026-12-31"), line("B", "B"), "ONE_TIME_VARIABLE"),
    (header("C", "FO", **YEAR), line("C", "P", contract_id="CTR-001", unit_price=1200), "RECURRING_FIXED"),
    (header("D", "NB"), line("D", "", contract_id="CTR-009"), "RECURRING_FIXED"),
    (header("E", "NB"), line("E", "", gr_required=True, quantity_ordered=25, unit_price=1600), "ONE_TIME_FIXED"),
    (header("F", "FO"), line("F", "B"), None),                      # framework order without validity: no branch
    (header("G", "NB"), line("G", ""), None),                       # standard item without quantity or price
])
def test_rule_tree(hdr, ln, expected):
    assert classifier.classify_columns(hdr, ln)[0] == expected


def test_contradiction_checks():
    h = header("X", "FO", total_amount=999)
    lines = [line("X", "B", quantity_received=3, quantity_ordered=5), {**line("X", "P", gr_required=True, quantity_ordered=1, unit_price=500), "po_line_id": "X-002"}]
    assert classifier.contradictions(h, lines[0], lines) == ["limit item has a received quantity", "limit item has an ordered quantity above 1",
                                                             "framework order has no validity period", "PO total 999 differs from its lines 500"]
    assert "service item is marked goods-receipt based" in classifier.contradictions(h, lines[1], lines)
    clean = header("Y", "NB", total_amount=40000)
    goods = line("Y", "", quantity_ordered=25, unit_price=1600)
    assert classifier.contradictions(clean, goods, [goods]) == []


def setup(tmp_path, headers, lines):
    ws = make_ws(tmp_path)
    store.save_table(ws, "po_headers", headers)
    store.save_table(ws, "po_lines", lines)
    detection.run(ws, P)
    return ws


def test_agreement(tmp_path):
    ws = setup(tmp_path, [header("PO-001", "FO", **YEAR)], [line("PO-001", "P", "Team documentation platform subscription, billed monthly", contract_id="CTR-001")])
    model = says("RECURRING_FIXED")
    (c,) = classifier.run(ws, model, P)
    k = c["classification"]
    assert (k["rules"], k["model"], k["agree"], k["final"], k["suggested"], k["cache_hit"]) == ("RECURRING_FIXED", "RECURRING_FIXED", True, "RECURRING_FIXED", None, False)
    assert c["flags"] == [] and [d["kind"] for d in c["decision_log"] if d["worker"] == "classifier"] == ["RULE", "LLM"]
    assert model.calls == [("read_description", {"PO_LINE_ID": "PO-001-001", "LINE_DESCRIPTION": "Team documentation platform subscription, billed monthly"})]


def test_mismatch_columns_win_and_the_model_is_the_suggestion(tmp_path):
    twilio = line("PO-005", "", "Monthly SMS usage charges billed per message sent", gr_required=True, quantity_ordered=1, unit_price=5000, quantity_received=1)
    ws = setup(tmp_path, [header("PO-005", "NB")], [twilio])
    (c,) = classifier.run(ws, says("RECURRING_VARIABLE", 0.86), P)
    k = c["classification"]
    assert (k["rules"], k["model"], k["model_confidence"], k["agree"], k["final"], k["suggested"]) == \
        ("ONE_TIME_FIXED", "RECURRING_VARIABLE", 0.86, False, "ONE_TIME_FIXED", "RECURRING_VARIABLE")
    assert c["flags"] == ["CLASSIFICATION_MISMATCH"]


def test_low_confidence_disagreement_is_not_a_mismatch(tmp_path):
    ws = setup(tmp_path, [header("PO-001", "FO", **YEAR)], [line("PO-001", "P", "Services")])
    (c,) = classifier.run(ws, says("ONE_TIME_FIXED", 0.34), P)
    assert c["classification"]["agree"] is None and c["classification"]["final"] == "RECURRING_FIXED" and c["flags"] == []


def test_low_confidence_agreement_still_agrees(tmp_path):
    ws = setup(tmp_path, [header("PO-003", "NB", **YEAR)], [line("PO-003", "", "Laptop packages for new hires", gr_required=True, quantity_ordered=25, unit_price=1600, quantity_received=20)])
    (c,) = classifier.run(ws, says("ONE_TIME_FIXED", 0.46), P)
    assert c["classification"]["agree"] is True and c["flags"] == []


def test_no_rule_fits_the_model_decides_only_when_sure(tmp_path):
    rows = ([header("PO-030", "FO")], [line("PO-030", "B", "Cloud hosting billed monthly on consumption", service_start="2026-12-01", service_end="2026-12-31")])
    (c,) = classifier.run(setup(tmp_path / "a", *rows), says("RECURRING_VARIABLE", 0.96), P)
    assert c["classification"]["rules"] is None and c["classification"]["final"] == "RECURRING_VARIABLE"
    assert c["flags"] == ["CLASSIFICATION_CONTRADICTION"]
    (c,) = classifier.run(setup(tmp_path / "b", *rows), says("RECURRING_VARIABLE", 0.7), P)
    assert c["classification"]["final"] is None and c["flags"] == ["CLASSIFICATION_CONTRADICTION", "CLASSIFICATION_UNKNOWN"]


def test_cache_by_description_and_rerun_is_clean(tmp_path):
    ws = setup(tmp_path, [header("PO-001", "FO", **YEAR)], [line("PO-001", "P", "Subscription, billed monthly")])
    model = says("RECURRING_FIXED")
    classifier.run(ws, model, P)
    (c,) = classifier.run(ws, model, P)
    assert len(model.calls) == 1 and c["classification"]["cache_hit"] is True
    assert [d["worker"] for d in c["decision_log"]].count("classifier") == 2

    rows = store.load_table(ws, "po_lines")
    rows[0]["line_description"] = "Subscription, billed per seat used"
    store.save_table(ws, "po_lines", rows)
    classifier.run(ws, model, P)
    assert len(model.calls) == 2  # the row changed: ask again


def test_model_failure_or_bad_category_falls_back_to_the_columns(tmp_path):
    def down(prompt_name, variables):
        raise RuntimeError("bedrock down")

    ws = setup(tmp_path, [header("PO-001", "FO", **YEAR)], [line("PO-001", "P", "Subscription")])
    (c,) = classifier.run(ws, down, P)
    k = c["classification"]
    assert (k["rules"], k["model"], k["agree"], k["final"]) == ("RECURRING_FIXED", None, None, "RECURRING_FIXED") and c["flags"] == []
    assert store.load_state(ws, classifier.CACHE, {}) == {}  # a failure is never cached
    (c,) = classifier.run(ws, says("SOMETHING_ELSE"), P)
    assert c["classification"]["model"] is None and c["classification"]["final"] == "RECURRING_FIXED"
