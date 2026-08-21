# Hudson -- Option B: Infrastructure, Live Client & CLI (Revised)
**Pair:** Luca + Hudson | **Deadline:** Friday EOD

**Assignment recap:** poll the demo environment via API for invoices sitting in draft or awaiting posting, and send a Slack message to this channel summarizing what needs attention (who, what, how much, how old). It should read like something a finance person actually wants. Scheduling is a stretch goal, not a requirement.

**What changed from the original plan:** we now have demo env access. The original plan assumed the live client would ship untested. That assumption is gone, so a verification phase has been added (Phase 6b) and a live integration test replaces "must run clean with no credentials" as the final gate. A few loose ends (timezone handling, unused config, vendor pagination, Slack bot token) are also closed out below.

---

## Step 0 -- Do this with Luca first (15 min, non-negotiable)

Agree on `src/models.py` and `src/light_client.py` together, commit to a shared branch. Same as before, unchanged.

One addition to discuss in this same 15 minutes: **decide whether "how old" means days since the invoice entered its current status, or days past due date.** The model carries both (`updatedAt` and `dueDate`), and the assignment just says "how old," which is genuinely ambiguous. Default to status age (time stuck, since that is what this agent is chasing) but flag it as a one-line callout in the demo, since a finance person may expect "how old" to mean overdue-by-due-date.

---

## Your work starts here

You own **Phases 4, 5, 6, 6b, 7, 8**. Luca owns 1, 2, 3.

---

## Phase 4 -- Config and Environment (20 min)

`src/config.py`, largely unchanged, with one fix: every constant defined here must actually be consumed somewhere, or removed. Specifically:

- `AGING_THRESHOLDS` must be read by `aging.py` (coordinate with Luca, her `classify_bucket` should take these as parameters or import them, not hardcode 7/14/30).
- `TIMEZONE` must be read by `formatter.py` for the header date (coordinate with Luca), or removed from config if you agree UTC-only is fine for this sprint. Pick one and note the decision in build-log.md.

Drop the `SLACK_BOT_TOKEN` branch from `validate()`. Only `WebhookSink` is being built this sprint; a bot-token sink is out of scope. If it stays in config as a stub, it should not be treated as satisfying `OUTPUT_MODE=slack` on its own, since nothing will consume it.

```python
import os
from dotenv import load_dotenv

load_dotenv()

USE_MOCK_DATA       = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
LIGHT_API_KEY       = os.getenv("LIGHT_API_KEY", "")
LIGHT_API_BASE_URL  = os.getenv("LIGHT_API_BASE_URL", "https://api.light.inc/v1")
LIGHT_ENTITY_ID     = os.getenv("LIGHT_COMPANY_ENTITY_ID", "")
SLACK_WEBHOOK_URL   = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL_ID    = os.getenv("SLACK_CHANNEL_ID", "C0BQ1E76QDR")
OUTPUT_MODE         = os.getenv("OUTPUT_MODE", "console")   # console | file | slack
TIMEZONE            = os.getenv("TIMEZONE", "UTC")
AGING_THRESHOLDS    = [int(x) for x in os.getenv("AGING_THRESHOLDS", "7,14,30").split(",")]
SCHEDULE_TIME       = os.getenv("SCHEDULE_TIME", "09:00")   # for daily digest, stretch goal only

def validate():
    if not USE_MOCK_DATA:
        if not LIGHT_API_KEY:
            raise EnvironmentError("LIGHT_API_KEY is required when USE_MOCK_DATA=false")
        if not LIGHT_ENTITY_ID:
            raise EnvironmentError("LIGHT_COMPANY_ENTITY_ID is required when USE_MOCK_DATA=false")
    if OUTPUT_MODE == "slack" and not SLACK_WEBHOOK_URL:
        raise EnvironmentError("SLACK_WEBHOOK_URL required when OUTPUT_MODE=slack")
```

`.env.example` -- same as before, minus `SLACK_BOT_TOKEN`. Confirm `.env` is in `.gitignore` before anything else.

---

## Phase 5 -- Output Sinks (30 min)

`src/sinks.py`, unchanged from the original plan: `ConsoleSink`, `FileSink`, `WebhookSink`, sharing one interface, selected by `get_sink()` based on `OUTPUT_MODE`.

The one addition: wrap `WebhookSink.send` failures so they surface a clear message rather than an unhandled exception, since this is the path that actually posts to the assignment's target Slack channel and needs to fail loudly if the webhook is wrong, not silently.

---

## Phase 6 -- Live Client, first pass (45 min)

Write `src/live_client.py` against the Light API docs, same as the original plan, marking assumptions clearly. This is now a first pass only, not a final version, since Phase 6b will correct it against real responses.

```python
import httpx
from .light_client import LightClient
from .models import Invoice, Vendor, InvoiceStatus
from . import config

STUCK_STATUSES = [
    InvoiceStatus.IN_DRAFT,
    InvoiceStatus.APPROVAL_REQUESTED,
    InvoiceStatus.APPROVAL_PENDING,
    InvoiceStatus.APPROVED_ACCOUNTING_ENTRY_PENDING,
]

class LiveLightClient(LightClient):
    def __init__(self):
        if not config.LIGHT_API_KEY:
            raise EnvironmentError("LIGHT_API_KEY is not set")
        self._base = config.LIGHT_API_BASE_URL
        self._headers = {
            "Authorization": f"Bearer {config.LIGHT_API_KEY}",
            "Content-Type": "application/json",
        }
        self._entity_id = config.LIGHT_ENTITY_ID
        self._vendor_cache: dict[str, Vendor] = {}

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self._base}{path}"
        for attempt in range(3):
            try:
                r = httpx.get(url, headers=self._headers, params=params, timeout=15)
                if r.status_code in (401, 403):
                    raise PermissionError(f"Auth error {r.status_code}: check LIGHT_API_KEY")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500 or attempt == 2:
                    raise
                import time; time.sleep(2 ** attempt)

    def list_stuck_invoices(self) -> list[Invoice]:
        # NOTE: field names below are best guesses pending Phase 6b verification
        results = []
        for status in STUCK_STATUSES:
            page = 1
            while True:
                data = self._get("/invoice-payables", params={
                    "status": status.value,
                    "companyEntityId": self._entity_id,
                    "page": page,
                    "limit": 100,
                })
                items = data.get("data", data.get("items", []))
                results.extend([Invoice(**item) for item in items])
                if not data.get("hasNextPage", False):
                    break
                page += 1
        return results

    def get_vendors(self, vendor_ids: list[str]) -> dict[str, Vendor]:
        # NOTE: paginated the same way as invoices, do not assume a single page
        missing = [vid for vid in vendor_ids if vid not in self._vendor_cache]
        if missing:
            page = 1
            while True:
                data = self._get("/vendors", params={
                    "companyEntityId": self._entity_id,
                    "page": page,
                    "limit": 100,
                })
                for v in data.get("data", data.get("items", [])):
                    vendor = Vendor(**v)
                    self._vendor_cache[vendor.id] = vendor
                if not data.get("hasNextPage", False):
                    break
                page += 1
        return {vid: self._vendor_cache[vid] for vid in vendor_ids if vid in self._vendor_cache}
```

Note in `build-log.md` that this is a first pass, pending live verification.

---

## Phase 6b -- Live Verification (30 min, new, do not skip)

Now that demo credentials exist, this replaces the old "cannot be tested, move on" instruction.

1. Set `USE_MOCK_DATA=false`, fill `LIGHT_API_KEY` and `LIGHT_COMPANY_ENTITY_ID` in `.env`.
2. Run `python -m src.main --live --output console` (this flag combination is new, see Phase 8) against the demo env.
3. Compare the actual JSON response shape against the guesses in `list_stuck_invoices` and `get_vendors`: is it `data` or `items`? Is pagination `hasNextPage`, a `next` cursor, or something else? Fix the code to match reality, do not leave guesses in place once you have seen a real response.
4. Check whether `updatedAt` and `createdAt` come back timezone-aware (with an offset or `Z`) or naive. If naive, flag this to Luca immediately, since `aging.py`'s subtraction against `datetime.now(timezone.utc)` will crash on a naive value. Do not let this surface for the first time during the demo.
5. Confirm the 401/403 path actually triggers a `PermissionError` and not a stack trace, by briefly testing with a deliberately wrong key, then restoring the real one.
6. Update the note in `build-log.md` from "untested" to what was actually verified, and list every field name or pagination assumption that turned out wrong.

If the demo env is unreachable or incomplete in some way, record that as a blocker in build-log.md and fall back to mock mode for the demo, this is an acceptable outcome, but it must be a documented decision, not a silent one.

---

## Phase 7 -- CLI Entry Point and Scheduling (30 min)

`src/main.py`, same structure as the original plan, with two additions: a `--live` mode that is now expected to actually work (not just parse), and a try/except around `run_once` so an auth failure or network error produces a clean message instead of a raw traceback, since this could run live in front of the room during the demo.

```python
import argparse
import schedule
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .mock_client import MockLightClient
from .live_client import LiveLightClient
from .grouping import build_alert_summary
from .formatter import format_blocks, format_plain
from .sinks import get_sink

def run_once(client, sink):
    print(f"[{datetime.now(timezone.utc).isoformat()}] Polling Light API...")
    try:
        invoices = client.list_stuck_invoices()
    except PermissionError as e:
        print(f"Could not reach Light API: {e}")
        return
    except Exception as e:
        print(f"Unexpected error while polling Light API: {e}")
        return

    if not invoices:
        print("No stuck invoices found. Nothing to send.")
        return
    vendor_ids = list({inv.businessPartnerId for inv in invoices})
    vendors = client.get_vendors(vendor_ids)
    summary = build_alert_summary(invoices, vendors)
    blocks = format_blocks(summary)
    plain = format_plain(summary)
    sink.send(blocks, plain)

def main():
    parser = argparse.ArgumentParser(description="Light posting-alert agent")
    parser.add_argument("--mock", action="store_true", help="Use mock data (default if USE_MOCK_DATA=true)")
    parser.add_argument("--live", action="store_true", help="Use live Light API")
    parser.add_argument("--output", choices=["console", "file", "slack"], default=None)
    parser.add_argument("--schedule", action="store_true", help="Run on a daily schedule (stretch goal)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    use_mock = config.USE_MOCK_DATA
    if args.live:
        use_mock = False
    if args.mock:
        use_mock = True

    if args.output:
        config.OUTPUT_MODE = args.output

    config.validate()

    client = MockLightClient(Path("data")) if use_mock else LiveLightClient()
    sink = get_sink()

    if args.schedule:
        print(f"Scheduled mode: running daily at {config.SCHEDULE_TIME} UTC")
        schedule.every().day.at(config.SCHEDULE_TIME).do(run_once, client, sink)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_once(client, sink)

if __name__ == "__main__":
    main()
```

`requirements.txt`, `README.md`: same as the original plan. Add a fifth README section: "Verified against demo env on [date], see build-log.md for what changed from the initial guesses."

---

## Phase 7b -- Slack App Setup (20 min, hard timebox)

Unchanged from the original plan. Create the app at `api.slack.com/apps`, add an Incoming Webhook, point it at the assignment's channel, copy the URL into `.env`. Test with `python -m src.main --mock --output slack` first, since that isolates whether the sink itself works before layering the live client on top. If workspace settings block app creation, record the blocker in build-log.md and rely on console or file output for the demo.

---

## Phase 8 -- Integration and Live Test (new)

Two gates now, not one:

```bash
# Gate 1: must run clean with no credentials
python -m src.main --mock --output console

# Gate 2: must run clean against the real demo environment
python -m src.main --live --output console
```

Gate 2 is the one that actually proves the assignment: polling the demo environment and producing a real summary. Do not treat Gate 1 alone as done, that was correct when there were no credentials, it is not correct anymore.

Once both gates pass, run the real end-to-end path once before the demo recording:

```bash
python -m src.main --live --output slack
```

Confirm the message lands in the assignment's Slack channel and is readable.

---

## Integration -- connecting with Luca's work

Same contract as before:

```python
from src.formatter import format_blocks, format_plain
# format_blocks(summary: AlertSummary) -> list[dict]
# format_plain(summary: AlertSummary) -> str
```

Additionally, confirm with Luca whether `aging.py` now takes `config.AGING_THRESHOLDS` and whether `formatter.py` now takes `config.TIMEZONE`, per the Phase 4 note. If either was left hardcoded, that is fine for the sprint, just make sure build-log.md says so explicitly rather than leaving it as a silent gap.

---

## Build Log

Keep `build-log.md` as you go, Petr asked for it explicitly: what you prompted Claude Code with, what came back, what broke, how you fixed it. The Phase 6b entries (what the real API actually looked like versus the guesses) are the most valuable ones in this revision, do not clean them up or shorten them.

---

## Your file ownership

```
src/config.py          (yours)
src/sinks.py            (yours)
src/live_client.py      (yours)
src/main.py             (yours)
requirements.txt        (yours)
.env.example            (yours)
README.md               (yours)
build-log.md            (both of you, add entries as you go)
```

Shared (agreed in Step 0):
```
src/models.py
src/light_client.py
```
