import json
import re
from decimal import Decimal
from pathlib import Path

from trueup.ingest.manifest import FileUniverse
from trueup.simulator.files.build import build_universe
from trueup.simulator.files.common import CLOSE
from trueup.simulator.files.models import RelevanceTruth
from trueup.simulator.files.scoring import score_selection, visible_files
from trueup.simulator.files.text import usd, usd2

VENDORS = ("Mintlify", "OpenAI", "ASUS", "Meta", "Notability")
RELEVANT = ("SUPPORTS_AMOUNT", "SUPPORTS_DISCREPANCY")
LEAKY = ("relevant", "noise", "negative", "supports_", "late_arrival", "in_universe", "role")


def _close_files(universe, case_id):
    return [f for f in universe.for_case(case_id) if f.available_at <= CLOSE]


def test_every_case_has_ten_files_and_three_to_four_relevant(built):
    universe, truth, _ = built
    assert [c.vendor_name for c in universe.cases] == list(VENDORS)
    for case in universe.cases:
        assert 9 <= len(_close_files(universe, case.case_id)) <= 11
        wanted = [e for e in truth.for_case(case.case_id) if e.in_universe and e.relevant]
        expected = 3 if case.vendor_name == "Mintlify" else range(3, 5)
        assert (len(wanted) == expected) if isinstance(expected, int) else len(wanted) in expected


def test_mintlify_relevant_files_match_the_comp(built):
    universe, truth, _ = built
    case = universe.cases[0]
    wanted = sorted(
        next(f.kind for f in universe.files if f.file_id == e.file_id)
        for e in truth.for_case(case.case_id)
        if e.relevant and e.in_universe
    )
    assert wanted == ["agreement", "ap", "prior"]


def test_manifest_carries_no_relevance_information(built):
    universe, _, _ = built
    dumped = universe.model_dump_json().lower()
    assert not [word for word in LEAKY if word in dumped]
    assert not {"relevant", "role", "reason"} & set(type(universe.files[0]).model_fields)


def test_manifest_and_truth_cover_the_same_files(built):
    universe, truth, out = built
    assert {f.file_id for f in universe.files} == set(truth.entries)
    assert all((out / f.path).is_file() for f in universe.files)
    assert len({f.path for f in universe.files}) == len(universe.files)


def test_every_preview_has_a_known_card_style_and_title(built):
    universe, _, _ = built
    styles = {"clause", "table", "memo", "record", "email", "chat", "skeleton"}
    for f in universe.files:
        assert f.preview["card"] in styles
        assert f.preview["title"]


def test_mintlify_files_carry_the_amended_price_and_the_stale_one(built, texts, view, case_texts):
    vendor = view.vendor("Mintlify").vendor_id
    old, new = view.contracts(vendor)[0], view.contracts(vendor)[-1]
    relevant = case_texts("Mintlify", RELEVANT)
    joined = "\n".join(relevant.values())
    assert f"from {usd(old.base_rate)} to {usd(new.base_rate)} per month" in joined
    assert usd(new.base_rate) == "$1,400"
    for invoice in view.invoices(vendor):
        assert usd2(invoice.amount) in joined
    stale_po = next(t for t in case_texts("Mintlify").values() if "Purchase Order" in t)
    assert usd2(view.pos(vendor)[0].line_items_json[0].unit_price) in stale_po
    assert usd(new.base_rate) not in stale_po


def test_openai_files_show_the_rate_step_up_and_only_partial_usage(
    built, texts, view, world, case_texts
):
    vendor = view.vendor("OpenAI").vendor_id
    contract = view.contracts(vendor)[-1]
    december = [e for e in view.evidence(vendor) if e.service_start_date.month == 12][-1]
    relevant = case_texts("OpenAI", RELEVANT)
    joined = "\n".join(relevant.values())
    assert "$0.02" in joined and usd(contract.base_rate) in joined
    assert "PARTIAL" in joined
    assert f"{int(december.quantity):,}" in joined
    full_total = next(r for r in world.outreach if "OPENAI" in r.outreach_key.upper())
    total = f"{int(Decimal(str(full_total.parsed_truth['quantity']))):,}"
    assert total not in "\n".join(case_texts("OpenAI").values())


def test_asus_files_show_ordered_received_and_price(built, texts, view, case_texts):
    vendor = view.vendor("ASUS").vendor_id
    line = view.pos(vendor)[0].line_items_json[0]
    receipt = next(e for e in view.evidence(vendor) if e.evidence_type == "GOODS_RECEIPT")
    joined = "\n".join(case_texts("ASUS", RELEVANT).values())
    assert line.quantity_ordered == 25 and receipt.quantity == 20
    assert usd2(line.unit_price) in joined
    assert usd2(receipt.quantity * line.unit_price) == "$32,000.00" and "$32,000.00" in joined
    assert usd2(line.quantity_ordered * line.unit_price) == "$40,000.00" and "$40,000.00" in joined


def test_meta_files_show_budget_and_delivered_amount(built, texts, view, case_texts):
    vendor = view.vendor("Meta").vendor_id
    budget = view.pos(vendor)[0].approved_total
    delivered = next(e for e in view.evidence(vendor) if e.accepted_amount).accepted_amount
    joined = "\n".join(case_texts("Meta", RELEVANT).values())
    assert (budget, delivered) == (Decimal("30000.00"), Decimal("24700.00"))
    assert usd2(budget) in joined and usd2(delivered) in joined


def test_notability_files_show_prepaid_amount_and_twelve_service_months(
    built, texts, view, case_texts
):
    vendor = view.vendor("Notability").vendor_id
    contract = view.contracts(vendor)[-1]
    amount = view.invoices(vendor)[-1].amount
    relevant = case_texts("Notability", RELEVANT)
    joined = "\n".join(relevant.values())
    assert usd(amount) == "$21,600"
    assert "12 months" in joined
    assert contract.effective_start_date.strftime("%B") in joined
    assert joined.count("$21,600.00") >= 4


def test_answer_amounts_live_only_in_relevant_files(built, texts, view, case_texts):
    checks = {"Mintlify": "$1,400", "ASUS": "$32,000", "Meta": "$24,700"}
    for vendor, amount in checks.items():
        others = case_texts(vendor, ("NOISE", "HARD_NEGATIVE"))
        assert not [fid for fid, text in others.items() if amount in text], vendor
    at_close = "\n".join(case_texts("OpenAI").values())
    assert usd(Decimal("18600")) not in at_close


def test_late_files_are_gated_by_the_clock_and_are_late_arrivals(built):
    universe, truth, _ = built
    late = [f for f in universe.files if f.available_at > CLOSE]
    assert late and all(truth.entries[f.file_id].role == "LATE_ARRIVAL" for f in late)
    assert all(not truth.entries[f.file_id].in_universe for f in late)
    at_close = {f.file_id for f in visible_files(universe, CLOSE)}
    assert not {f.file_id for f in late} & at_close
    january = max(f.available_at for f in late)
    assert {f.file_id for f in late} <= {f.file_id for f in visible_files(universe, january)}
    invoices = [f for f in late if f.kind == "invoice"]
    assert sorted(f.case_id.split("-")[1] for f in invoices) == [
        "ASUS",
        "META",
        "META",
        "MINTLIFY",
        "OPENAI",
    ]


def test_late_invoice_amounts_match_the_scheduled_events(built, texts, world):
    universe, _, _ = built
    by_number = {
        event.record["invoice_number"]: Decimal(event.record["amount"])
        for event in world.events
        if event.table == "company_ap_invoices"
        and event.operation == "INSERT"
        and event.available_at > CLOSE
    }
    for f in universe.files:
        if f.available_at > CLOSE and f.kind == "invoice":
            number = f.preview["title"].removeprefix("Invoice ")
            assert usd2(by_number[number]) in texts[f.file_id]


def test_perfect_selection_scores_one_and_wrong_selection_scores_lower(built):
    universe, truth, _ = built
    for case in universe.cases:
        wanted = [e.file_id for e in truth.for_case(case.case_id) if e.in_universe and e.relevant]
        assert score_selection(wanted, truth, case.case_id)["f1"] == 1.0
        everything = [f.file_id for f in _close_files(universe, case.case_id)]
        assert score_selection(everything, truth, case.case_id)["precision"] < 1.0
        assert score_selection(everything[:1], truth, case.case_id)["f1"] < 1.0


def test_generation_is_deterministic_down_to_the_bytes(world, built, tmp_path):
    universe, truth, out = built
    again_universe, again_truth = build_universe(world, 42, tmp_path)
    assert again_universe.model_dump_json() == universe.model_dump_json()
    assert again_truth.model_dump_json() == truth.model_dump_json()
    for f in universe.files:
        assert (tmp_path / f.path).read_bytes() == (out / f.path).read_bytes(), f.path


def test_shipped_seed_files_match_a_fresh_build(built):
    seed = Path(__file__).resolve().parents[3] / "seed"
    universe, truth, _ = built
    assert FileUniverse.model_validate_json((seed / "file_universe.json").read_text()) == universe
    assert RelevanceTruth.model_validate_json((seed / "relevance_truth.json").read_text()) == truth


def test_generated_text_has_no_em_or_en_dashes(texts):
    assert not [
        fid for fid, text in texts.items() if re.search(f"[{chr(0x2013)}{chr(0x2014)}]", text)
    ]


def test_file_ids_do_not_reveal_relevance(built):
    universe, truth, _ = built
    for case in universe.cases:
        entries = sorted(
            (e for e in truth.for_case(case.case_id) if e.in_universe), key=lambda e: e.file_id
        )
        flags = [e.relevant for e in entries]
        assert flags != sorted(flags, reverse=True), "relevant files must not all be listed first"


def test_size_labels_agree_with_the_rendered_files(built, texts):
    universe, _, _ = built
    for f in universe.files:
        count = int(f.size_label.split()[0])
        if f.format == "XLSX":
            data_lines = [
                ln for ln in texts[f.file_id].splitlines() if ln and not ln.startswith("#")
            ]
            assert count == len(data_lines) - 1
        if f.format == "TXT":
            assert count == len([ln for ln in texts[f.file_id].splitlines() if ln.startswith("[")])
        assert count >= 1


def test_truth_file_is_never_referenced_by_agent_or_store_code():
    root = Path(__file__).resolve().parents[3] / "trueup"
    forbidden = ("relevance_truth", "simulator.files", "RelevanceTruth")
    offenders = []
    for package in ("agents", "store", "ingest", "gateway"):
        for path in (root / package).rglob("*.py"):
            source = path.read_text()
            offenders += [f"{path.name}:{word}" for word in forbidden if word in source]
    assert not offenders
    assert json.loads((root.parent / "seed" / "relevance_truth.json").read_text())["entries"]
