"""Format an AlertSummary into Slack Block Kit blocks or plain text.

Exports exactly two functions (Hudson's main.py contract):
    format_blocks(summary: AlertSummary) -> list[dict]
    format_plain(summary: AlertSummary) -> str

Design choices recorded here so they're easy to find at the demo:
- "How old" = status age (updatedAt), not due-date age. See aging.py.
- Header date timezone comes from config.TIMEZONE ("UTC" in the stub).
  If Hudson's real config.py sets a different zone, the header date shifts
  automatically -- nothing else needs to change.
- Status labels are mapped to plain English; raw enum values never surface.
- Currency amounts use a thousands separator and currency symbol where known.
- Block cap: 50 blocks max. Vendor sections are 3 blocks each (section +
  actions + divider). With 3 header blocks and 1 optional truncation block,
  the cap allows up to 15 vendors before a "and N more" note is appended.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import AlertSummary, AgingBucket, InvoiceStatus
from .aging import compute_age_days, classify_bucket
from . import config

# ---------------------------------------------------------------------------
# Label and symbol maps -- the finance-readability contract
# ---------------------------------------------------------------------------

_STATUS_LABELS: dict[InvoiceStatus, str] = {
    InvoiceStatus.IN_DRAFT:                            "in draft",
    InvoiceStatus.APPROVAL_PENDING:                    "pending approval",
    InvoiceStatus.APPROVED_ACCOUNTING_ENTRY_PENDING:   "pending accounting entry",
    InvoiceStatus.AWAITING_PAYMENT:                    "awaiting payment",
}

_BUCKET_EMOJI: dict[AgingBucket, str] = {
    AgingBucket.FRESH:     ":large_green_circle:",
    AgingBucket.WATCH:     ":warning:",
    AgingBucket.ATTENTION: ":large_orange_circle:",
    AgingBucket.OVERDUE:   ":red_circle:",
}

_BUCKET_LABELS: dict[AgingBucket, str] = {
    AgingBucket.FRESH:     "fresh",
    AgingBucket.WATCH:     "watch",
    AgingBucket.ATTENTION: "attention",
    AgingBucket.OVERDUE:   "overdue",
}

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

# Block Kit sizing
_HEADER_BLOCKS = 3        # header + summary section + first divider
_BLOCKS_PER_VENDOR = 3    # section + actions + divider
_TRUNCATION_BLOCK = 1
_MAX_BLOCKS = 50
_MAX_VENDORS = (_MAX_BLOCKS - _HEADER_BLOCKS - _TRUNCATION_BLOCK) // _BLOCKS_PER_VENDOR

# A single vendor with hundreds of stuck invoices is real (seen live against the demo
# tenant, one vendor had 449). A Slack section's text has a hard 3000-character limit,
# and a wall of invoice lines is not finance-readable anyway, so cap per-vendor display.
_MAX_INVOICES_PER_VENDOR = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_tz():
    """Return a tzinfo for config.TIMEZONE, falling back to UTC on error."""
    try:
        return ZoneInfo(config.TIMEZONE)
    except (KeyError, ZoneInfoNotFoundError):
        return timezone.utc


def _fmt_amount(amount: float, currency: str) -> str:
    """Format a monetary amount with symbol and thousands separator."""
    sym = _CURRENCY_SYMBOLS.get(currency, "")
    if amount == int(amount):
        num = f"{int(amount):,}"
    else:
        num = f"{amount:,.2f}"
    return f"{sym}{num} {currency}" if sym else f"{num} {currency}"


def _fmt_totals(total_by_currency: dict[str, float]) -> str:
    """Format a multi-currency total dict into a readable string."""
    parts = [_fmt_amount(amt, cur) for cur, amt in sorted(total_by_currency.items())]
    return ", ".join(parts)


def _vendor_section_text(vs) -> str:
    """Build the mrkdwn text block for one vendor's summary + invoice lines."""
    n = len(vs.invoices)
    plural = "s" if n != 1 else ""
    oldest_emoji = _BUCKET_EMOJI[vs.worst_bucket]
    totals = _fmt_totals(vs.total_by_currency)

    header = (
        f"*{vs.vendor.name}*  --  {n} invoice{plural}  |  "
        f"{totals}  |  oldest: {vs.oldest_age_days} days {oldest_emoji}"
    )

    shown = vs.invoices[:_MAX_INVOICES_PER_VENDOR]
    hidden = n - len(shown)

    inv_lines = []
    for inv in shown:
        age = compute_age_days(inv)
        status_label = _STATUS_LABELS[inv.status]
        inv_lines.append(
            f"`{inv.id}`   {_fmt_amount(inv.amount, inv.currency)}   {age}d   {status_label}"
        )
    if hidden > 0:
        inv_plural = "s" if hidden != 1 else ""
        inv_lines.append(f"_+{hidden} more invoice{inv_plural} not shown_")

    return header + "\n" + "\n".join(inv_lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_blocks(summary: AlertSummary) -> list[dict]:
    """Return a Slack Block Kit payload for the given AlertSummary."""
    tz = _get_tz()
    now = summary.generated_at.astimezone(tz)
    date_str = now.strftime("%a %d %b %Y")

    bc = summary.bucket_counts
    bucket_line = (
        f"{summary.total_invoices} invoices pending  |  "
        f"{bc.get(AgingBucket.FRESH, 0)} {_BUCKET_EMOJI[AgingBucket.FRESH]}  "
        f"{bc.get(AgingBucket.WATCH, 0)} {_BUCKET_EMOJI[AgingBucket.WATCH]}  "
        f"{bc.get(AgingBucket.ATTENTION, 0)} {_BUCKET_EMOJI[AgingBucket.ATTENTION]}  "
        f"{bc.get(AgingBucket.OVERDUE, 0)} {_BUCKET_EMOJI[AgingBucket.OVERDUE]}"
    )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Posting Alert -- {date_str}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": bucket_line},
        },
        {"type": "divider"},
    ]

    vendors_to_show = summary.vendor_summaries[:_MAX_VENDORS]
    remaining = len(summary.vendor_summaries) - len(vendors_to_show)

    for vs in vendors_to_show:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": _vendor_section_text(vs)},
        })
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View in Light"},
                    "url": "https://app.light.inc/payables",
                    "action_id": "view_in_light",
                }
            ],
        })
        blocks.append({"type": "divider"})

    if remaining > 0:
        v_plural = "s" if remaining != 1 else ""
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"_and {remaining} more vendor{v_plural} not shown_",
            },
        })

    return blocks


def format_plain(summary: AlertSummary) -> str:
    """Return a plain-text version of the alert readable without Slack formatting."""
    tz = _get_tz()
    now = summary.generated_at.astimezone(tz)
    date_str = now.strftime("%a %d %b %Y")

    bc = summary.bucket_counts
    bucket_parts = [
        f"{bc.get(b, 0)} {_BUCKET_LABELS[b]}"
        for b in [AgingBucket.FRESH, AgingBucket.WATCH,
                  AgingBucket.ATTENTION, AgingBucket.OVERDUE]
        if bc.get(b, 0) > 0
    ]

    lines = [
        f"Posting Alert -- {date_str}",
        "",
        f"{summary.total_invoices} invoices pending | " + ", ".join(bucket_parts),
        "",
        "-" * 64,
    ]

    for vs in summary.vendor_summaries:
        n = len(vs.invoices)
        inv_plural = "s" if n != 1 else ""
        totals = _fmt_totals(vs.total_by_currency)
        oldest_label = _BUCKET_LABELS[vs.worst_bucket].upper()
        lines.append("")
        lines.append(
            f"{vs.vendor.name}  --  {n} invoice{inv_plural}  |  {totals}  "
            f"|  oldest: {vs.oldest_age_days}d  [{oldest_label}]"
        )
        shown = vs.invoices[:_MAX_INVOICES_PER_VENDOR]
        hidden = n - len(shown)
        for inv in shown:
            age = compute_age_days(inv)
            bucket = classify_bucket(age)
            status_label = _STATUS_LABELS[inv.status]
            bucket_label = _BUCKET_LABELS[bucket].upper()
            lines.append(
                f"  {inv.id:<12}  {_fmt_amount(inv.amount, inv.currency):<18}"
                f"  {age:>3}d  {status_label:<30}  [{bucket_label}]"
            )
        if hidden > 0:
            h_plural = "s" if hidden != 1 else ""
            lines.append(f"  ... and {hidden} more invoice{h_plural} not shown")

    lines.append("")
    return "\n".join(lines)
