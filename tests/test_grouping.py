"""Tests for src/grouping.py -- write first, implement second."""
from datetime import datetime, timedelta, timezone

import pytest

from src.models import Invoice, InvoiceStatus, Vendor, AgingBucket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_invoice(
    inv_id: str,
    vendor_id: str,
    amount: float,
    currency: str,
    status: InvoiceStatus,
    age_days: int,
) -> Invoice:
    updated_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    return Invoice(
        id=inv_id,
        vendorId=vendor_id,
        amount=amount,
        currency=currency,
        status=status,
        updatedAt=updated_at,
    )


def make_vendor(vendor_id: str, name: str) -> Vendor:
    return Vendor(id=vendor_id, name=name)


# ---------------------------------------------------------------------------
# Shared fixture: 5 vendors, 10 invoices (mirrors mock JSON)
# ---------------------------------------------------------------------------

VENDORS = {
    "v001": make_vendor("v001", "Acme Corp"),
    "v002": make_vendor("v002", "Globex Industries"),
    "v003": make_vendor("v003", "Initech"),
    "v004": make_vendor("v004", "Umbrella Ltd"),
    "v005": make_vendor("v005", "Hooli Inc"),
}

# ages chosen to hit all four buckets
INVOICES = [
    make_invoice("INV-1001", "v001", 5200.00, "USD", InvoiceStatus.IN_DRAFT, 45),             # OVERDUE
    make_invoice("INV-1002", "v001", 4100.00, "USD", InvoiceStatus.APPROVAL_PENDING, 20),      # ATTENTION
    make_invoice("INV-1003", "v001", 3100.00, "USD", InvoiceStatus.IN_DRAFT, 3),               # FRESH
    make_invoice("INV-1004", "v002", 8500.00, "USD", InvoiceStatus.APPROVAL_PENDING, 10),      # WATCH
    make_invoice("INV-1005", "v002", 3200.00, "EUR", InvoiceStatus.APPROVED_ACCOUNTING_ENTRY_PENDING, 16),  # ATTENTION
    make_invoice("INV-1006", "v003", 2800.00, "USD", InvoiceStatus.APPROVED_ACCOUNTING_ENTRY_PENDING, 45),  # OVERDUE
    make_invoice("INV-1007", "v003", 1500.00, "USD", InvoiceStatus.IN_DRAFT, 7),               # WATCH
    make_invoice("INV-1008", "v004", 6400.00, "EUR", InvoiceStatus.APPROVAL_PENDING, 25),      # ATTENTION
    make_invoice("INV-1009", "v004", 1200.00, "EUR", InvoiceStatus.AWAITING_PAYMENT, 12),      # WATCH
    make_invoice("INV-1010", "v005",  450.00, "USD", InvoiceStatus.IN_DRAFT, 3),               # FRESH
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_group_by_vendor():
    """Each VendorSummary must contain only invoices belonging to that vendor."""
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    for vs in summary.vendor_summaries:
        for inv in vs.invoices:
            assert inv.vendorId == vs.vendor.id


def test_all_vendors_represented():
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    vendor_ids = {vs.vendor.id for vs in summary.vendor_summaries}
    assert vendor_ids == set(VENDORS.keys())


def test_three_plus_invoices_rolled_up():
    """Acme Corp (v001) has 3 invoices -- all must appear in its summary."""
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    acme = next(vs for vs in summary.vendor_summaries if vs.vendor.id == "v001")
    assert len(acme.invoices) == 3
    ids = {inv.id for inv in acme.invoices}
    assert ids == {"INV-1001", "INV-1002", "INV-1003"}


def test_single_small_invoice_vendor():
    """Hooli (v005) has exactly one invoice."""
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    hooli = next(vs for vs in summary.vendor_summaries if vs.vendor.id == "v005")
    assert len(hooli.invoices) == 1
    assert hooli.invoices[0].id == "INV-1010"


def test_multi_currency_totals():
    """
    Globex (v002) has USD 8500 and EUR 3200.
    total_by_currency must have both, not mixed into one.
    """
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    globex = next(vs for vs in summary.vendor_summaries if vs.vendor.id == "v002")
    assert globex.total_by_currency.get("USD") == pytest.approx(8500.00)
    assert globex.total_by_currency.get("EUR") == pytest.approx(3200.00)


def test_oldest_age_days():
    """Acme worst invoice is 45 days old."""
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    acme = next(vs for vs in summary.vendor_summaries if vs.vendor.id == "v001")
    assert acme.oldest_age_days == 45


def test_worst_bucket_per_vendor():
    """
    Acme has FRESH (3d), ATTENTION (20d), OVERDUE (45d) -> worst = OVERDUE.
    Hooli has only FRESH (3d) -> worst = FRESH.
    """
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    acme  = next(vs for vs in summary.vendor_summaries if vs.vendor.id == "v001")
    hooli = next(vs for vs in summary.vendor_summaries if vs.vendor.id == "v005")
    assert acme.worst_bucket  == AgingBucket.OVERDUE
    assert hooli.worst_bucket == AgingBucket.FRESH


def test_sort_order_by_urgency():
    """
    Vendors with the worst (highest) bucket come first.
    OVERDUE > ATTENTION > WATCH > FRESH.
    Among same bucket, older (larger oldest_age_days) comes first.
    """
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    buckets = [vs.worst_bucket for vs in summary.vendor_summaries]
    # bucket rank: OVERDUE=3, ATTENTION=2, WATCH=1, FRESH=0
    rank = {AgingBucket.OVERDUE: 3, AgingBucket.ATTENTION: 2,
            AgingBucket.WATCH: 1, AgingBucket.FRESH: 0}
    ranks = [rank[b] for b in buckets]
    assert ranks == sorted(ranks, reverse=True)


def test_total_invoices_count():
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    assert summary.total_invoices == 10


def test_bucket_counts_in_summary():
    """
    From INVOICES fixture:
    FRESH:     INV-1003, INV-1010           -> 2
    WATCH:     INV-1004, INV-1007, INV-1009 -> 3
    ATTENTION: INV-1002, INV-1005, INV-1008 -> 3
    OVERDUE:   INV-1001, INV-1006           -> 2
    """
    from src.grouping import build_alert_summary
    summary = build_alert_summary(INVOICES, VENDORS)
    bc = summary.bucket_counts
    assert bc[AgingBucket.FRESH]     == 2
    assert bc[AgingBucket.WATCH]     == 3
    assert bc[AgingBucket.ATTENTION] == 3
    assert bc[AgingBucket.OVERDUE]   == 2


def test_empty_invoice_list():
    from src.grouping import build_alert_summary
    summary = build_alert_summary([], {})
    assert summary.total_invoices == 0
    assert summary.vendor_summaries == []
    assert all(v == 0 for v in summary.bucket_counts.values())
