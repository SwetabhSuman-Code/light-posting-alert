"""Aging calculation and bucket classification.

Thresholds come from config.AGING_THRESHOLDS so Hudson's real config.py wins
at merge. The stub on this branch has [7, 14, 30].

Naive-datetime note: the Light API may return updatedAt without timezone info.
_as_utc coerces any naive datetime to UTC before subtraction so we never get a
bare TypeError at the demo. If Phase 6b finds the real API returns naive
timestamps in a non-UTC timezone, this is the one-line fix: change replace()
to a proper conversion using pytz or zoneinfo.
"""
from datetime import datetime, timezone

from .models import Invoice, AgingBucket
from . import config


def _as_utc(dt: datetime) -> datetime:
    """Return dt in UTC. Naive datetimes are assumed to already be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_age_days(invoice: Invoice) -> int:
    """Days since the invoice was last moved (updatedAt), rounded down."""
    now = datetime.now(timezone.utc)
    reference = _as_utc(invoice.updatedAt)
    return (now - reference).days


def classify_bucket(days: int) -> AgingBucket:
    """Map an age in days to the appropriate AgingBucket using config thresholds."""
    watch, attention, overdue = config.AGING_THRESHOLDS
    if days < watch:
        return AgingBucket.FRESH
    elif days < attention:
        return AgingBucket.WATCH
    elif days < overdue:
        return AgingBucket.ATTENTION
    else:
        return AgingBucket.OVERDUE
