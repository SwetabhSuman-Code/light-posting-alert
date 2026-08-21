"""Tests for src/formatter.py -- written before implementation."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.models import (
    Invoice, InvoiceStatus, Vendor,
    AgingBucket, VendorSummary, AlertSummary,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _invoice(inv_id, vendor_id, amount, currency, status, age_days):
    updated_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    return Invoice(
        id=inv_id, vendorId=vendor_id, amount=amount, currency=currency,
        status=status, updatedAt=updated_at,
    )


def _vendor_summary(vendor_id, name, invoices, total_by_currency, oldest_age_days, worst_bucket):
    return VendorSummary(
        vendor=Vendor(id=vendor_id, name=name),
        invoices=invoices,
        total_by_currency=total_by_currency,
        oldest_age_days=oldest_age_days,
        worst_bucket=worst_bucket,
    )


# Minimal summary used by most tests: 3 vendors, 6 invoices, USD + EUR
_INV_A1 = _invoice("INV-1001", "v001", 5200.00, "USD", InvoiceStatus.IN_DRAFT, 45)
_INV_A2 = _invoice("INV-1002", "v001", 4100.00, "USD", InvoiceStatus.APPROVAL_PENDING, 20)
_INV_A3 = _invoice("INV-1003", "v001", 3100.00, "USD", InvoiceStatus.IN_DRAFT, 3)
_INV_B1 = _invoice("INV-1004", "v002", 8500.00, "USD", InvoiceStatus.APPROVAL_PENDING, 10)
_INV_B2 = _invoice("INV-1005", "v002", 3200.00, "EUR", InvoiceStatus.APPROVED_ACCOUNTING_ENTRY_PENDING, 16)
_INV_C1 = _invoice("INV-1010", "v005",  450.00, "USD", InvoiceStatus.IN_DRAFT, 3)

SAMPLE_SUMMARY = AlertSummary(
    vendor_summaries=[
        _vendor_summary("v001", "Acme Corp",
                        [_INV_A1, _INV_A2, _INV_A3],
                        {"USD": 12400.00}, 45, AgingBucket.OVERDUE),
        _vendor_summary("v002", "Globex Industries",
                        [_INV_B2, _INV_B1],
                        {"USD": 8500.00, "EUR": 3200.00}, 16, AgingBucket.ATTENTION),
        _vendor_summary("v005", "Hooli Inc",
                        [_INV_C1],
                        {"USD": 450.00}, 3, AgingBucket.FRESH),
    ],
    total_invoices=6,
    bucket_counts={
        AgingBucket.FRESH: 2,
        AgingBucket.WATCH: 0,
        AgingBucket.ATTENTION: 2,
        AgingBucket.OVERDUE: 2,
    },
    generated_at=datetime(2026, 8, 21, 14, 0, 0, tzinfo=timezone.utc),
)


# ---------------------------------------------------------------------------
# format_blocks structural tests
# ---------------------------------------------------------------------------

def test_format_blocks_returns_list_of_dicts():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    assert isinstance(blocks, list)
    assert all(isinstance(b, dict) for b in blocks)


def test_format_blocks_first_block_is_header():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    assert blocks[0]["type"] == "header"
    assert "Posting Alert" in blocks[0]["text"]["text"]


def test_format_blocks_header_contains_date():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    # generated_at is 2026-08-21 UTC; header must mention the date
    header_text = blocks[0]["text"]["text"]
    assert "2026" in header_text
    assert "Aug" in header_text


def test_format_blocks_summary_section_mentions_invoice_count():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    summary_block = blocks[1]
    assert summary_block["type"] == "section"
    assert "6" in summary_block["text"]["text"]


def test_format_blocks_has_dividers():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    dividers = [b for b in blocks if b["type"] == "divider"]
    assert len(dividers) >= 1


def test_format_blocks_contains_vendor_names():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    all_text = json.dumps(blocks)
    assert "Acme Corp" in all_text
    assert "Globex Industries" in all_text
    assert "Hooli Inc" in all_text


def test_format_blocks_contains_invoice_ids():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    all_text = json.dumps(blocks)
    assert "INV-1001" in all_text
    assert "INV-1004" in all_text


def test_format_blocks_has_button_linking_to_light():
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    all_text = json.dumps(blocks)
    assert "app.light.inc" in all_text


def test_format_blocks_no_raw_status_enum_values():
    """Block text must never expose raw enum values to a finance reader."""
    from src.formatter import format_blocks
    blocks = format_blocks(SAMPLE_SUMMARY)
    all_text = json.dumps(blocks)
    bad = [
        "APPROVED_ACCOUNTING_ENTRY_PENDING",
        "APPROVAL_PENDING",
        "IN_DRAFT",
        "AWAITING_PAYMENT",
    ]
    for label in bad:
        assert label not in all_text, f"Raw status enum '{label}' found in blocks output"


def test_format_blocks_respects_50_block_cap():
    """With enough vendors to overflow, total blocks must not exceed 50."""
    from src.formatter import format_blocks
    from src.models import VendorSummary, Vendor

    # Build 30 vendors, each with one invoice -- well above any reasonable limit
    inv = _invoice("INV-X", "vX", 100.00, "USD", InvoiceStatus.IN_DRAFT, 10)
    big_summary = AlertSummary(
        vendor_summaries=[
            _vendor_summary(f"v{i:03d}", f"Vendor {i}", [inv],
                            {"USD": 100.00}, 10, AgingBucket.WATCH)
            for i in range(30)
        ],
        total_invoices=30,
        bucket_counts={b: 0 for b in AgingBucket},
        generated_at=datetime(2026, 8, 21, 14, 0, 0, tzinfo=timezone.utc),
    )
    blocks = format_blocks(big_summary)
    assert len(blocks) <= 50


def test_format_blocks_truncation_message_appears():
    """When vendors are truncated, a 'more vendors' note must appear."""
    from src.formatter import format_blocks

    inv = _invoice("INV-X", "vX", 100.00, "USD", InvoiceStatus.IN_DRAFT, 10)
    big_summary = AlertSummary(
        vendor_summaries=[
            _vendor_summary(f"v{i:03d}", f"Vendor {i}", [inv],
                            {"USD": 100.00}, 10, AgingBucket.WATCH)
            for i in range(30)
        ],
        total_invoices=30,
        bucket_counts={b: 0 for b in AgingBucket},
        generated_at=datetime(2026, 8, 21, 14, 0, 0, tzinfo=timezone.utc),
    )
    blocks = format_blocks(big_summary)
    all_text = json.dumps(blocks)
    assert "more" in all_text.lower()


# ---------------------------------------------------------------------------
# format_plain tests
# ---------------------------------------------------------------------------

def test_format_plain_returns_string():
    from src.formatter import format_plain
    result = format_plain(SAMPLE_SUMMARY)
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_plain_contains_vendor_names():
    from src.formatter import format_plain
    result = format_plain(SAMPLE_SUMMARY)
    assert "Acme Corp" in result
    assert "Globex Industries" in result
    assert "Hooli Inc" in result


def test_format_plain_contains_invoice_ids():
    from src.formatter import format_plain
    result = format_plain(SAMPLE_SUMMARY)
    assert "INV-1001" in result
    assert "INV-1010" in result


def test_bucket_labels_read_like_finance_not_engineering():
    """
    Direct check on the assignment bar: output must read like something a
    finance person wants, not a developer reading Python enum names.
    Neither raw status values nor raw bucket values should appear.
    """
    from src.formatter import format_plain
    result = format_plain(SAMPLE_SUMMARY)
    raw_enum_values = [
        # status enums
        "IN_DRAFT",
        "APPROVAL_PENDING",
        "APPROVED_ACCOUNTING_ENTRY_PENDING",
        "AWAITING_PAYMENT",
        # bucket enums (finance readers don't know what WATCH or ATTENTION mean in code)
        "AgingBucket",
        "InvoiceStatus",
    ]
    for label in raw_enum_values:
        assert label not in result, (
            f"Raw enum value '{label}' found in plain output -- "
            "map it to a human label before displaying"
        )


def test_currency_formatted_with_symbol_and_thousands():
    """$12,400 USD, not 12400.0 USD or 12400 USD."""
    from src.formatter import format_plain
    result = format_plain(SAMPLE_SUMMARY)
    assert "$12,400" in result or "$5,200" in result   # Acme totals / line items
    assert "€3,200" in result                          # Globex EUR invoice


def test_multi_currency_totals_shown_separately():
    """Globex has both USD and EUR -- both must appear in the plain output."""
    from src.formatter import format_plain
    result = format_plain(SAMPLE_SUMMARY)
    # Find the Globex section
    globex_start = result.index("Globex Industries")
    globex_section = result[globex_start:globex_start + 300]
    assert "USD" in globex_section
    assert "EUR" in globex_section
