# Luca -- Option B: Data, Logic & Formatting (Revised)
**Pair:** Luca + Hudson | **Deadline:** Friday EOD

**Assignment recap:** poll the demo environment via API for invoices sitting in draft or awaiting posting, and send a Slack message to this channel summarizing what needs attention (who, what, how much, how old). It should read like something a finance person actually wants. Scheduling is a stretch goal, not a requirement.

**What changed from the original plan:** the aging calculation had a bug that mock data would never expose but the real API might, plus two config values (`AGING_THRESHOLDS`, `TIMEZONE`) were defined by Hudson but never actually read anywhere. Both are fixed below. Everything else is close to the original plan.

---

## Step 0 -- Do this with Hudson first (15 min, non-negotiable)

Agree on `src/models.py` and `src/light_client.py`, commit to a shared branch. Same as before, unchanged.

Also agree with Hudson on the "how old" question: does age mean time stuck in the current status (`updatedAt`), or time past due date (`dueDate`)? Default to status age for this sprint, since that is what the agent is actually chasing, but note the decision and be ready to mention it in the demo.

---

## Your work starts here

You own **Phases 1, 2, 3**. Hudson owns 4, 5, 6, 6b, 7, 8.

---

## Phase 1 -- Mock Data and Mock Client (45 min)

Unchanged from the original plan. `data/mock_invoices.json` with 10 invoices across 5 vendors, all four target statuses represented, ages spanning every bucket (3, 10, 20, 45 days plus a mix), at least USD and EUR, one vendor with a single small invoice, one vendor with 3+ invoices.

One addition: make at least one mock invoice's `updatedAt` naive-looking versus another's explicitly `Z`-suffixed, so that Phase 2's tests catch a timezone bug locally rather than it surfacing for the first time against the real API in Phase 6b. Since Pydantic will parse both consistently based on the field type, the more useful test is described in Phase 2 below.

`src/mock_client.py`, unchanged:

```python
import json
from pathlib import Path
from .light_client import LightClient
from .models import Invoice, Vendor

class MockLightClient(LightClient):
    def __init__(self, data_dir: Path = Path("data")):
        self._data_dir = data_dir

    def list_stuck_invoices(self) -> list[Invoice]:
        raw = json.loads((self._data_dir / "mock_invoices.json").read_text())
        return [Invoice(**item) for item in raw]

    def get_vendors(self, vendor_ids: list[str]) -> dict[str, Vendor]:
        raw = json.loads((self._data_dir / "mock_vendors.json").read_text())
        vendors = {v["id"]: Vendor(**v) for v in raw}
        return {vid: vendors[vid] for vid in vendor_ids if vid in vendors}
```

---

## Phase 2 -- Aging and Grouping Logic (50 min, was 45)

**Write tests first, then implementation.** The extra 5 minutes over the original plan covers the timezone fix below.

### 2a. Tests for aging, plus one new test

`tests/test_aging.py`, same as the original plan, with one addition:

```python
def test_naive_datetime_does_not_crash():
    # simulate a live-API response that returns a naive datetime for updatedAt
    # compute_age_days must either coerce it to UTC or raise a clear, named
    # error, it must never raise a bare TypeError from datetime subtraction
    ...
```

This is the test that the original plan was missing. Mock data always uses `Z`-suffixed (timezone-aware) timestamps, so the original `compute_age_days` was never exercised against a naive value and the bug would only have appeared live, possibly during the demo.

### 2b. Implement aging.py, fixed

Read thresholds from `config.AGING_THRESHOLDS` instead of hardcoding 7/14/30 (confirm this with Hudson per Phase 4 of his plan), and coerce naive datetimes to UTC before subtracting:

```python
from datetime import datetime, timezone
from .models import Invoice, AgingBucket
from . import config

def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def compute_age_days(invoice: Invoice) -> int:
    now = datetime.now(timezone.utc)
    reference = _as_utc(invoice.updatedAt)
    delta = now - reference
    return delta.days

def classify_bucket(days: int) -> AgingBucket:
    watch, attention, overdue = config.AGING_THRESHOLDS
    if days < watch:
        return AgingBucket.FRESH
    elif days < attention:
        return AgingBucket.WATCH
    elif days < overdue:
        return AgingBucket.ATTENTION
    else:
        return AgingBucket.OVERDUE
```

Note: `_as_utc` assumes a naive timestamp from the API is already UTC, which is a reasonable default but is itself an assumption. If Phase 6b (Hudson's live verification) finds the real API returns naive timestamps in a different timezone, this needs a one-line fix, flag it in build-log.md either way.

### 2c/2d. Grouping tests and implementation

Unchanged from the original plan: `tests/test_grouping.py` covering vendor grouping, sort order, multi-currency totals, empty list, single invoice, and `src/grouping.py` implementing `build_alert_summary`.

Run tests: `pytest tests/test_aging.py tests/test_grouping.py`

---

## Phase 3 -- Message Formatting (60 min)

`src/formatter.py`, largely unchanged from the original plan, with one addition: read `config.TIMEZONE` for the header date instead of assuming UTC (confirm this with Hudson, or explicitly agree to skip it and stay UTC-only for the sprint, either is fine as long as it is a stated decision, not a leftover unused variable).

### Bucket emoji map, target output structure, Block Kit constraints, and plain text fallback

All unchanged from the original plan:

```
[Header]  Posting Alert -- Thu 20 Aug 2026

[Section] 12 invoices pending  |  4 :large_green_circle:  3 :warning:  3 :large_orange_circle:  2 :red_circle:

[Divider]

[Section] *Acme Corp*  --  3 invoices  |  $12,400 USD  |  oldest: 18 days :large_orange_circle:
           INV-1042   $5,200 USD   18d   IN_DRAFT
           INV-1058   $4,100 USD    9d   APPROVAL_PENDING
           INV-1061   $3,100 USD    3d   IN_DRAFT
[Button]   View in Light -> https://app.light.inc/payables

[Divider]

... repeat per vendor ...
```

Max 50 blocks total, truncate to top vendors by urgency with a "and X more" note if exceeded, each vendor section is roughly 3 blocks.

### Test it

Paste the Block Kit JSON into `app.slack.com/block-kit-builder`, confirm it renders without errors.

`tests/test_formatter.py`, unchanged, plus one addition:

```python
def test_bucket_labels_read_like_finance_not_engineering():
    # sanity check: the plain-text output should say something like
    # "18 days in draft" or "18 days pending", not just the raw enum
    # value APPROVED_ACCOUNTING_ENTRY_PENDING, since a finance person
    # is the target reader per the assignment
    ...
```

This is a direct check against the assignment's own bar, "something a finance person would actually want to read," rather than just structural correctness.

---

## Integration handoff to Hudson

Once Phase 3 is done, tell Hudson:
- `src/models.py`, `src/mock_client.py`, `src/aging.py`, `src/grouping.py`, `src/formatter.py` are all committed.
- `formatter.py` exports `format_blocks(summary: AlertSummary) -> list[dict]` and `format_plain(summary: AlertSummary) -> str`.
- All tests pass, including the new naive-datetime test.
- Confirm whether `aging.py` ended up reading `config.AGING_THRESHOLDS` and whether `formatter.py` ended up reading `config.TIMEZONE`, so build-log.md reflects the actual final state rather than the plan's intent.

Hudson's `main.py` calls your code exactly as before:
```python
from src.mock_client import MockLightClient
from src.grouping import build_alert_summary
from src.formatter import format_blocks, format_plain
```

Stick to that contract. When Hudson reaches Phase 6b (live verification against the demo env), be available in case the real API's timestamp format needs a quick fix to `_as_utc`, since that is your file.

---

## Build Log

Keep `build-log.md` updated as you go, Petr asked for it explicitly. For each phase: what you prompted Claude Code with, what came back, what broke, how you fixed it. The naive-datetime bug, if it turns out to matter against the real API, belongs here in detail.

---

## Your file ownership

```
src/models.py            (shared, agreed with Hudson in Step 0)
src/light_client.py      (shared, agreed with Hudson in Step 0)
src/mock_client.py       (yours)
src/aging.py             (yours)
src/grouping.py          (yours)
src/formatter.py         (yours)
data/mock_invoices.json  (yours)
data/mock_vendors.json   (yours)
tests/test_aging.py      (yours)
tests/test_grouping.py   (yours)
tests/test_formatter.py  (yours)
```
