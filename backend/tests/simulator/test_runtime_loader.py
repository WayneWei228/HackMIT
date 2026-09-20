from datetime import datetime

import pytest
from sqlalchemy import select

from trueup.simulator import generator, seed_loader
from trueup.simulator.scenario_models import APInvoiceRecord
from trueup.simulator.seed_loader import ORM_MODELS, SeedError, load_static, record_to_row
from trueup.simulator.simulator import Simulator, table_counts
from trueup.store.models import CompanyAPInvoice, CompanyServiceEvidence
from trueup.store.session import create_all, get_session, make_engine


def test_every_static_and_event_record_inserts_into_the_store(sim_world, sim):
    sim.advance_to("2027-12-31T00:00:00Z")
    inserts = {table: 0 for table in ORM_MODELS}
    for event in sim_world.events:
        inserts[event.table] += event.operation == "INSERT"
    with sim.session() as session:
        counts = table_counts(session)
    for table in ORM_MODELS:
        static_rows = len(getattr(sim_world.static, table))
        assert counts[table] == static_rows + inserts[table], table


def test_day_one_has_history_but_nothing_from_the_future(sim):
    now = sim.now()
    with sim.session() as session:
        invoices = list(session.scalars(select(CompanyAPInvoice)))
        evidence = list(session.scalars(select(CompanyServiceEvidence)))
    assert len(invoices) == 7 and len(evidence) == 3
    assert all(inv.received_at <= now for inv in invoices)
    assert all(row.created_at <= now for row in evidence)


def test_static_seed_carrying_a_future_row_is_refused(sim_world):
    invoice_event = next(e for e in sim_world.events if e.table == "company_ap_invoices")
    future = APInvoiceRecord.model_validate(invoice_event.record)
    tainted = sim_world.static.model_copy(deep=True)
    tainted.company_ap_invoices.append(future)
    engine = make_engine()
    create_all(engine)
    with pytest.raises(SeedError, match="future rows belong in scenario events"):
        with get_session(engine) as session:
            load_static(session, tainted)


def test_record_to_row_keeps_json_columns_plain_and_money_exact(sim_world):
    po = next(r for r in sim_world.static.company_purchase_orders if r.po_id == "PO-ASUS-2026")
    row = record_to_row("company_purchase_orders", po)
    line = row.line_items_json[0]
    assert isinstance(line["unit_price"], str)
    assert isinstance(row.approved_total, type(po.approved_total))
    entry = record_to_row("company_gl_entries", sim_world.static.company_gl_entries[0])
    assert all(isinstance(line["debit"], str) for line in entry.lines_json)


def test_field_values_rejects_an_unknown_column():
    with pytest.raises(SeedError, match="no column"):
        seed_loader.field_values("company_ap_invoices", {"amount_due": "1"})


def test_fixtures_written_to_disk_load_the_same_world(sim_world, tmp_path):
    generator.write_files(sim_world, tmp_path)
    from_files = Simulator.initialize(seed=42, seed_dir=tmp_path)
    with from_files.session() as session:
        counts = table_counts(session)
    for table in ORM_MODELS:
        assert counts[table] == len(getattr(sim_world.static, table)), table
    assert from_files.now() == datetime.fromisoformat("2026-12-01T08:00:00+00:00")
