"""Tests for pdf_generator.py.

generate_pdf is a pure function — it takes plain Python values and returns
bytes. No mocking required.
"""

from datetime import date

import pandas as pd

from pdf_generator import generate_pdf


COMPANY_SETTINGS = {
    "company_name":    "Test Company",
    "company_address": "123 Main St\nSpringfield, CO 80000",
    "handling_fee":    "0.08",
}

SAMPLE_COUPONS = pd.DataFrame([
    {"coupon_id": "A001", "amount": 1.00, "handling_fee": True,  "collected_date": date(2026, 1, 5)},
    {"coupon_id": "A001", "amount": 0.75, "handling_fee": False, "collected_date": date(2026, 1, 6)},
    {"coupon_id": "B002", "amount": 2.00, "handling_fee": True,  "collected_date": date(2026, 1, 7)},
])


def test_generate_pdf_returns_bytes():
    result = generate_pdf(
        company_settings=COMPANY_SETTINGS,
        manufacturer="Acme Corp",
        manufacturer_address="456 Industry Rd\nAcmeville, CA 90001",
        ref_number="REF-20260101-ACM",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        coupons=SAMPLE_COUPONS,
    )
    assert isinstance(result, bytes)


def test_generate_pdf_produces_valid_pdf_header():
    result = generate_pdf(
        company_settings=COMPANY_SETTINGS,
        manufacturer="Acme Corp",
        manufacturer_address="",
        ref_number="REF-20260101-ACM",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        coupons=SAMPLE_COUPONS,
    )
    # All PDFs begin with this magic bytes signature
    assert result[:4] == b"%PDF"


def test_generate_pdf_non_empty_output():
    result = generate_pdf(
        company_settings=COMPANY_SETTINGS,
        manufacturer="Acme Corp",
        manufacturer_address="",
        ref_number="REF-20260101-ACM",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        coupons=SAMPLE_COUPONS,
    )
    assert len(result) > 1024  # A real PDF will be well over 1KB


def test_generate_pdf_with_no_manufacturer_address():
    """Should not raise when manufacturer_address is empty."""
    result = generate_pdf(
        company_settings=COMPANY_SETTINGS,
        manufacturer="Acme Corp",
        manufacturer_address="",
        ref_number="REF-20260101-ACM",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        coupons=SAMPLE_COUPONS,
    )
    assert result[:4] == b"%PDF"


def test_generate_pdf_with_single_coupon():
    single = pd.DataFrame([
        {"coupon_id": "Z999", "amount": 0.50, "handling_fee": False, "collected_date": date(2026, 2, 1)},
    ])
    result = generate_pdf(
        company_settings=COMPANY_SETTINGS,
        manufacturer="Solo Mfr",
        manufacturer_address="",
        ref_number="REF-20260201-SOL",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        coupons=single,
    )
    assert result[:4] == b"%PDF"


def test_generate_pdf_with_missing_company_settings():
    """Should fall back gracefully when settings keys are absent."""
    result = generate_pdf(
        company_settings={},
        manufacturer="Acme Corp",
        manufacturer_address="",
        ref_number="REF-20260101-ACM",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        coupons=SAMPLE_COUPONS,
    )
    assert result[:4] == b"%PDF"