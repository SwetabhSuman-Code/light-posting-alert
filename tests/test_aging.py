"""Tests for src/aging.py -- write first, implement second."""
from datetime import datetime, timedelta, timezone

import pytest

from src.models import Invoice, InvoiceStatus, AgingBucket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_invoice(updated_at: datetime) -> Invoice:
    """Minimal Invoice with a controlled updatedAt; all other fields are dummies."""
    return Invoice(
        id="INV-TEST",
        vendorId="v000",
        amount=100.00,
        currency="USD",
        status=InvoiceStatus.IN_DRAFT,
        updatedAt=updated_at,
    )


def days_ago(n: int, *, aware: bool = True) -> datetime:
    """Return a datetime exactly n days before now."""
    now = datetime.now(timezone.utc)
    dt = now - timedelta(days=n)
    return dt if aware else dt.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# compute_age_days
# ---------------------------------------------------------------------------

def test_compute_age_days_fresh():
    from src.aging import compute_age_days
    inv = make_invoice(days_ago(3))
    assert compute_age_days(inv) == 3


def test_compute_age_days_watch():
    from src.aging import compute_age_days
    inv = make_invoice(days_ago(10))
    assert compute_age_days(inv) == 10


def test_compute_age_days_attention():
    from src.aging import compute_age_days
    inv = make_invoice(days_ago(20))
    assert compute_age_days(inv) == 20


def test_compute_age_days_overdue():
    from src.aging import compute_age_days
    inv = make_invoice(days_ago(45))
    assert compute_age_days(inv) == 45


def test_compute_age_days_is_non_negative():
    from src.aging import compute_age_days
    inv = make_invoice(days_ago(0))
    assert compute_age_days(inv) >= 0


def test_naive_datetime_does_not_crash():
    """
    Simulate a live-API response that omits timezone info on updatedAt.
    compute_age_days must coerce it to UTC and return a valid int -- it must
    never propagate a bare TypeError from aware - naive datetime subtraction.
    """
    from src.aging import compute_age_days
    inv = make_invoice(days_ago(15, aware=False))  # naive datetime
    age = compute_age_days(inv)
    assert isinstance(age, int)
    assert age >= 0


# ---------------------------------------------------------------------------
# classify_bucket -- boundaries matter
# ---------------------------------------------------------------------------
# config.AGING_THRESHOLDS = [7, 14, 30] (stub)
# FRESH < 7 | WATCH 7-13 | ATTENTION 14-29 | OVERDUE >= 30

def test_classify_fresh():
    from src.aging import classify_bucket
    assert classify_bucket(0) == AgingBucket.FRESH
    assert classify_bucket(3) == AgingBucket.FRESH
    assert classify_bucket(6) == AgingBucket.FRESH


def test_classify_watch():
    from src.aging import classify_bucket
    assert classify_bucket(7) == AgingBucket.WATCH   # exact lower boundary
    assert classify_bucket(10) == AgingBucket.WATCH
    assert classify_bucket(13) == AgingBucket.WATCH   # one below next boundary


def test_classify_attention():
    from src.aging import classify_bucket
    assert classify_bucket(14) == AgingBucket.ATTENTION  # exact lower boundary
    assert classify_bucket(20) == AgingBucket.ATTENTION
    assert classify_bucket(29) == AgingBucket.ATTENTION  # one below next boundary


def test_classify_overdue():
    from src.aging import classify_bucket
    assert classify_bucket(30) == AgingBucket.OVERDUE  # exact lower boundary
    assert classify_bucket(45) == AgingBucket.OVERDUE
    assert classify_bucket(90) == AgingBucket.OVERDUE


def test_classify_reads_config_not_hardcoded(monkeypatch):
    """Changing config.AGING_THRESHOLDS must change bucket boundaries."""
    import src.config as cfg
    from src.aging import classify_bucket
    monkeypatch.setattr(cfg, "AGING_THRESHOLDS", [3, 10, 20])
    # with new thresholds: FRESH < 3, WATCH 3-9, ATTENTION 10-19, OVERDUE >= 20
    assert classify_bucket(2) == AgingBucket.FRESH
    assert classify_bucket(3) == AgingBucket.WATCH
    assert classify_bucket(10) == AgingBucket.ATTENTION
    assert classify_bucket(20) == AgingBucket.OVERDUE
