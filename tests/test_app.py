"""Tests for app.py helper functions.

app.py imports streamlit and auth at module level, so both must be mocked
before the module is imported. The sys.modules approach handles this cleanly
without needing conftest.py.
"""

import sys
from datetime import date
from types import ModuleType
from unittest.mock import MagicMock, patch

import pandas as pd


def _mock_streamlit_module() -> ModuleType:
    """Return a minimal mock of the streamlit module."""
    st = MagicMock()
    st.secrets = {}
    return st


def _mock_auth_module() -> ModuleType:
    auth = MagicMock()
    auth.require_login = MagicMock(return_value=MagicMock(email="test@example.com"))
    return auth


# Patch st and auth before any import of app touches them.
sys.modules.setdefault("streamlit", _mock_streamlit_module())
sys.modules.setdefault("auth", _mock_auth_module())

from app import STATUS_LABELS, _build_pdf_from_snapshot, _save_report  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_conn_mock():
    cursor = MagicMock()
    cursor.fetchone.return_value = (42,)  # simulate RETURNING id
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


SAMPLE_COUPONS = pd.DataFrame([
    {"coupon_id": "A001", "amount": 1.00, "handling_fee": True,  "collected_date": date(2026, 1, 5)},
    {"coupon_id": "B002", "amount": 2.00, "handling_fee": False, "collected_date": date(2026, 1, 6)},
])

SAMPLE_SETTINGS = {
    "company_name":    "Test Co",
    "company_address": "1 Test St",
    "handling_fee":    "0.08",
}


# ---------------------------------------------------------------------------
# STATUS_LABELS
# ---------------------------------------------------------------------------

def test_status_labels_contains_all_statuses():
    assert set(STATUS_LABELS.keys()) == {"draft", "sent", "responded"}


def test_status_labels_values_are_non_empty_strings():
    for key, label in STATUS_LABELS.items():
        assert isinstance(label, str) and label.strip(), \
            f"Status label for '{key}' must be a non-empty string"


# ---------------------------------------------------------------------------
# _save_report
# ---------------------------------------------------------------------------

def test_save_report_returns_report_id():
    conn, cursor = _make_conn_mock()
    report_id = _save_report(
        conn=conn,
        ref_number="REF-001",
        manufacturer="Acme",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_face=3.00,
        total_handling=0.08,
        grand_total=3.08,
        coupons=SAMPLE_COUPONS,
        handling_fee_val=0.08,
    )
    assert report_id == 42


def test_save_report_inserts_report_row():
    conn, cursor = _make_conn_mock()
    _save_report(
        conn=conn,
        ref_number="REF-001",
        manufacturer="Acme",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_face=3.00,
        total_handling=0.08,
        grand_total=3.08,
        coupons=SAMPLE_COUPONS,
        handling_fee_val=0.08,
    )
    first_call_sql = cursor.execute.call_args_list[0].args[0]
    assert "INSERT INTO reports" in first_call_sql
    assert "RETURNING id" in first_call_sql


def test_save_report_inserts_correct_coupon_count():
    conn, cursor = _make_conn_mock()
    _save_report(
        conn=conn,
        ref_number="REF-001",
        manufacturer="Acme",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_face=3.00,
        total_handling=0.08,
        grand_total=3.08,
        coupons=SAMPLE_COUPONS,
        handling_fee_val=0.08,
    )
    # First execute call params: (..., coupon_count, ...)
    params = cursor.execute.call_args_list[0].args[1]
    assert len(SAMPLE_COUPONS) in params


def test_save_report_inserts_one_snapshot_row_per_coupon():
    conn, cursor = _make_conn_mock()
    _save_report(
        conn=conn,
        ref_number="REF-001",
        manufacturer="Acme",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_face=3.00,
        total_handling=0.08,
        grand_total=3.08,
        coupons=SAMPLE_COUPONS,
        handling_fee_val=0.08,
    )
    snapshot_calls = [
        c for c in cursor.execute.call_args_list
        if "INSERT INTO report_coupons" in c.args[0]
    ]
    assert len(snapshot_calls) == len(SAMPLE_COUPONS)


def test_save_report_commits_and_closes_cursor():
    conn, cursor = _make_conn_mock()
    _save_report(
        conn=conn,
        ref_number="REF-001",
        manufacturer="Acme",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_face=3.00,
        total_handling=0.08,
        grand_total=3.08,
        coupons=SAMPLE_COUPONS,
        handling_fee_val=0.08,
    )
    conn.commit.assert_called_once()
    cursor.close.assert_called_once()


def test_save_report_rounds_totals_to_two_decimal_places():
    conn, cursor = _make_conn_mock()
    _save_report(
        conn=conn,
        ref_number="REF-001",
        manufacturer="Acme",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        total_face=1.005,
        total_handling=0.004,
        grand_total=1.009,
        coupons=SAMPLE_COUPONS,
        handling_fee_val=0.08,
    )
    params = cursor.execute.call_args_list[0].args[1]
    assert round(1.005, 2) in params
    assert round(0.004, 2) in params
    assert round(1.009, 2) in params


# ---------------------------------------------------------------------------
# _build_pdf_from_snapshot
# ---------------------------------------------------------------------------

def test_build_pdf_returns_none_for_missing_report():
    conn = MagicMock()

    with patch("app.pd.read_sql", return_value=pd.DataFrame()):
        result = _build_pdf_from_snapshot(report_id=999, conn=conn, settings=SAMPLE_SETTINGS)

    assert result is None


def test_build_pdf_returns_pdf_bytes_for_valid_report():
    report_df = pd.DataFrame([{
        "id": 1,
        "ref_number": "REF-001",
        "manufacturer": "Acme",
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "generated_date": date(2026, 1, 31),
        "coupon_count": 2,
        "total_face": 3.00,
        "total_handling": 0.08,
        "grand_total": 3.08,
        "status": "draft",
        "sent_date": None,
        "response_date": None,
        "payment_amount": None,
        "check_reference": None,
        "notes": None,
    }])
    snapshot_df = pd.DataFrame([
        {"coupon_id": "A001", "amount": 1.00, "handling_fee": True,  "collected_date": date(2026, 1, 5)},
        {"coupon_id": "B002", "amount": 2.00, "handling_fee": False, "collected_date": date(2026, 1, 6)},
    ])
    mfr_df = pd.DataFrame([{"address": "456 Industry Rd"}])

    read_sql_returns = [report_df, snapshot_df, mfr_df]

    conn = MagicMock()
    with patch("app.pd.read_sql", side_effect=read_sql_returns):
        result = _build_pdf_from_snapshot(report_id=1, conn=conn, settings=SAMPLE_SETTINGS)

    assert isinstance(result, bytes)
    assert result[:4] == b"%PDF"