# light-posting-alert

A daily digest agent that polls the [Light](https://light.inc) AP demo environment for invoices stuck in draft or awaiting posting, then sends a formatted Slack alert so the finance team knows exactly what needs action.

---

## What it does

1. Calls the Light API and fetches every invoice in a "stuck" state (drafts, pending approval, pending accounting entry, awaiting payment).
2. Groups invoices by vendor and computes how long each one has been sitting (age from `updatedAt`).
3. Buckets them: **Fresh** (<7 d), **Watch** (7-13 d), **Attention** (14-29 d), **Overdue** (30+ d).
4. Sends a Slack Block Kit message with vendor-level summaries, invoice lines, and deep-links that open the exact vendor's bills in Light.

### Sample Slack output

```
Posting Alert -- Fri 22 Aug 2025

47 invoices pending | 12 🟢  18 ⚠️  11 🟠  6 🔴
──────────────────────────────────────────────────
Acme Corp  --  9 invoices  |  $42,300 USD  |  oldest: 38 days 🔴
  INV-1001   $12,000.00 USD    38d   pending approval
  INV-1002   $8,500.00 USD     22d   pending accounting entry
  ...
  [View in Light]        ← opens Light filtered to "Acme Corp"
```

---

## Project layout

```
light-posting-alert/
├── src/
│   ├── models.py        # Pydantic models (Invoice, Vendor, AlertSummary, ...)
│   ├── config.py        # Env-var config with validation
│   ├── aging.py         # Age calculation + bucket classification
│   ├── grouping.py      # Group invoices by vendor, build AlertSummary
│   ├── formatter.py     # Slack Block Kit + plain-text renderers
│   ├── light_client.py  # Abstract base class
│   ├── mock_client.py   # Reads data/ JSON files, no network
│   ├── live_client.py   # Real Light API client (cursor pagination, retry)
│   ├── sinks.py         # ConsoleSink, FileSink, WebhookSink (Slack)
│   └── main.py          # CLI entry point
├── tests/
│   ├── test_aging.py
│   ├── test_grouping.py
│   └── test_formatter.py
├── data/
│   ├── mock_invoices.json
│   └── mock_vendors.json
├── .env.example         # Copy to .env and fill in credentials
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/SwetabhSuman-Code/light-posting-alert.git
cd light-posting-alert
python -m venv .venv
```

Activate it:

- **Windows:** `.venv\Scripts\activate`
- **macOS/Linux:** `source .venv/bin/activate`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Then open `.env` and fill in:

| Variable | Description |
|---|---|
| `LIGHT_API_KEY` | Your Light API key (Basic auth) |
| `LIGHT_API_BASE_URL` | API root (default `https://api.light.inc`) |
| `SLACK_WEBHOOK_URL` | Incoming webhook URL from your Slack app |
| `SLACK_CHANNEL_ID` | Target channel (used for display only) |
| `USE_MOCK_DATA` | `true` to use local JSON fixtures, `false` for live |
| `OUTPUT_MODE` | `console`, `file`, or `slack` |
| `AGING_THRESHOLDS` | Comma-separated day boundaries: watch,attention,overdue (default `7,14,30`) |
| `TIMEZONE` | Display timezone for the alert header (default `UTC`) |

`.env` is gitignored and must never be committed.

---

## Running the agent

### Mock data (no credentials needed)

```bash
python -m src.main --mock --output console
```

### Live API, console output

```bash
python -m src.main --live --output console
```

### Live API, post to Slack

```bash
python -m src.main --live --output slack
```

### Write to a file instead of Slack

```bash
python -m src.main --live --output file
```

Output path is controlled by `OUTPUT_FILE_PATH` in `.env` (default `output/alert.txt`).

---

## Running tests

```bash
python -m pytest tests/ -v
```

39 tests covering aging logic, vendor grouping, multi-currency totals, Slack block structure, the 50-block cap, and finance-readable label formatting.

---

## Architecture notes

### Invoice states

The Light API exposes ~21 invoice states. We map them down to 4 meaningful "stuck" categories in `live_client.STUCK_STATE_MAP`:

| API state | Our label |
|---|---|
| `IN_DRAFT` | In Draft |
| `APPROVAL_REQUESTED`, `APPROVAL_PENDING` | Pending Approval |
| `APPROVED_ACCOUNTING_ENTRY_PENDING` | Pending Accounting Entry |
| `READY_FOR_PAYMENT_RELEASE`, `PAYMENT_PENDING`, `UNPAID`, ... | Awaiting Payment |

### Aging

Age is measured from `updatedAt` (not due date). Naive datetimes from the API are treated as UTC. Bucket thresholds are configurable via `AGING_THRESHOLDS`.

### Slack limits

- **50-block cap:** capped at 15 vendors per alert (3 blocks each + 3 header blocks + 1 overflow note).
- **3000-char section limit:** capped at 10 invoices per vendor; a "+N more not shown" line is appended.

### Deep-links

Vendor names and "View in Light" buttons link directly to:
```
https://app.light.inc/payables?search={vendor_name}
```
Vendor names are URL-encoded with `urllib.parse.quote_plus`.

---

## Team

| Who | Owns |
|---|---|
| Luca | `models.py`, `mock_client.py`, `aging.py`, `grouping.py`, `formatter.py`, mock data, tests |
| Hudson | `config.py`, `live_client.py`, `sinks.py`, `main.py` |

---

## Branch

Active development: `luca/data-logic-formatting`
