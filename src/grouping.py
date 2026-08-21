"""Group invoices by vendor and build the AlertSummary for the formatter.

Sort order: vendors with the worst (highest) bucket come first.
Within the same bucket, the vendor with the oldest invoice comes first.
"""
from collections import defaultdict
from datetime import datetime, timezone

from .models import (
    Invoice,
    Vendor,
    AgingBucket,
    VendorSummary,
    AlertSummary,
)
from .aging import compute_age_days, classify_bucket

# Bucket rank for sorting: higher = more urgent
_BUCKET_RANK: dict[AgingBucket, int] = {
    AgingBucket.FRESH: 0,
    AgingBucket.WATCH: 1,
    AgingBucket.ATTENTION: 2,
    AgingBucket.OVERDUE: 3,
}


def build_alert_summary(
    invoices: list[Invoice],
    vendors: dict[str, Vendor],
) -> AlertSummary:
    """Group invoices by vendor, compute per-vendor stats, and return AlertSummary."""
    # --- group invoices by vendorId ---
    grouped: dict[str, list[Invoice]] = defaultdict(list)
    for inv in invoices:
        grouped[inv.vendorId].append(inv)

    # --- build per-vendor summaries ---
    vendor_summaries: list[VendorSummary] = []
    overall_bucket_counts: dict[AgingBucket, int] = {b: 0 for b in AgingBucket}

    for vendor_id, vendor_invoices in grouped.items():
        total_by_currency: dict[str, float] = defaultdict(float)
        ages: list[int] = []
        buckets: list[AgingBucket] = []

        for inv in vendor_invoices:
            age = compute_age_days(inv)
            bucket = classify_bucket(age)
            ages.append(age)
            buckets.append(bucket)
            total_by_currency[inv.currency] += inv.amount
            overall_bucket_counts[bucket] += 1

        oldest_age = max(ages)
        worst_bucket = max(buckets, key=lambda b: _BUCKET_RANK[b])

        # sort this vendor's invoices oldest-first for display
        sorted_invoices = sorted(vendor_invoices, key=lambda inv: compute_age_days(inv), reverse=True)

        vendor_summaries.append(
            VendorSummary(
                vendor=vendors[vendor_id],
                invoices=sorted_invoices,
                total_by_currency=dict(total_by_currency),
                oldest_age_days=oldest_age,
                worst_bucket=worst_bucket,
            )
        )

    # --- sort vendors: most urgent first, then oldest ---
    vendor_summaries.sort(
        key=lambda vs: (_BUCKET_RANK[vs.worst_bucket], vs.oldest_age_days),
        reverse=True,
    )

    return AlertSummary(
        vendor_summaries=vendor_summaries,
        total_invoices=len(invoices),
        bucket_counts=overall_bucket_counts,
        generated_at=datetime.now(timezone.utc),
    )
