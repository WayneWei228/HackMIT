from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import StatementError

from trueup.store import enums as e
from trueup.store import models as m
from trueup.store.types import coerce_money

NOW = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)


def _vendor(vendor_id="V1", **overrides):
    fields = dict(
        vendor_id=vendor_id,
        vendor_name="Acme",
        vendor_category=e.VendorCategory.SAAS,
        billing_cadence=e.BillingCadence.MONTHLY,
        default_currency="USD",
    )
    return m.CompanyVendor(**{**fields, **overrides})


def _config(key, value, at=NOW):
    return m.CompanyConfig(config_key=key, config_value_json=value, updated_at=at)


def _contract(**overrides):
    fields = dict(
        contract_row_id="C1-V1",
        contract_id="C1",
        contract_version=1,
        vendor_id="V1",
        contract_name="Acme",
        status=e.ContractStatus.ACTIVE,
        effective_start_date=NOW.date(),
        billing_model=e.BillingModel.USAGE_BASED,
        billing_frequency=e.BillingFrequency.VARIABLE,
        contract_text="",
    )
    return m.CompanyContract(**{**fields, **overrides})


@pytest.mark.parametrize("value", [Decimal("0.00525"), 42, "1200.50"])
def test_coerce_money_accepts_exact_inputs(value):
    assert coerce_money(value) == Decimal(str(value))


@pytest.mark.parametrize("value", [0.1, True, None, [1]])
def test_coerce_money_rejects_floats_and_other_types(value):
    with pytest.raises(TypeError):
        coerce_money(value)


@pytest.mark.parametrize("value", ["twelve", "NaN", "Infinity"])
def test_coerce_money_rejects_non_finite_or_garbage(value):
    with pytest.raises(ValueError):
        coerce_money(value)


def test_money_round_trips_without_rounding(store_session):
    store_session.add_all([_vendor(), _contract(base_rate=Decimal("0.00525"))])
    store_session.commit()
    store_session.expire_all()
    rate = store_session.get(m.CompanyContract, "C1-V1").base_rate
    assert rate == Decimal("0.00525")
    assert isinstance(rate, Decimal)


def test_money_column_rejects_float_on_write(store_session):
    store_session.add_all([_vendor(), _contract(base_rate=0.005)])
    with pytest.raises(StatementError, match="never float"):
        store_session.flush()
    store_session.rollback()


def test_money_column_keeps_null(store_session):
    store_session.add_all([_vendor(), _contract()])
    store_session.commit()
    store_session.expire_all()
    assert store_session.get(m.CompanyContract, "C1-V1").base_rate is None


def test_enum_column_returns_members_and_rejects_unknown_values(store_session):
    store_session.add(_vendor())
    store_session.commit()
    store_session.expire_all()
    vendor = store_session.get(m.CompanyVendor, "V1")
    assert vendor.vendor_category is e.VendorCategory.SAAS
    assert vendor.vendor_category == "SAAS"

    store_session.add(_vendor("V2", vendor_category="WIDGETS"))
    with pytest.raises(StatementError, match="not a valid VendorCategory"):
        store_session.flush()
    store_session.rollback()


def test_timestamps_come_back_as_utc(store_session):
    eastern = timezone(timedelta(hours=-5))
    stamp = datetime(2027, 1, 4, 4, 0, tzinfo=eastern)
    store_session.add(_config("a", {}, stamp))
    store_session.commit()
    store_session.expire_all()
    loaded = store_session.get(m.CompanyConfig, "a").updated_at
    assert loaded == datetime(2027, 1, 4, 9, 0, tzinfo=UTC)
    assert loaded.tzinfo is not None


def test_naive_timestamp_is_treated_as_utc(store_session):
    store_session.add(_config("a", {}, datetime(2027, 1, 4, 9, 0)))
    store_session.commit()
    store_session.expire_all()
    assert store_session.get(m.CompanyConfig, "a").updated_at == datetime(
        2027, 1, 4, 9, 0, tzinfo=UTC
    )


def test_json_none_is_sql_null(store_session):
    store_session.add_all([_vendor(), _contract()])
    store_session.commit()
    row = store_session.execute(
        m.CompanyContract.__table__.select().where(m.CompanyContract.contract_row_id == "C1-V1")
    ).one()
    assert row.rate_unit is None
