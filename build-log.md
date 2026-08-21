# Build Log -- Light Posting Alert

Combined log covering all phases. Luca owned Phases 1-3 (mock data, aging/grouping logic,
message formatting). Hudson owned Phases 4-7 (config, sinks, live client, CLI).

Format per entry: what was prompted, what came back, what broke, how it was fixed.
"What broke" entries are kept in full, not cleaned up -- those are the point.

---

## Setup
- [2026-08-21] Repo scaffolded, venv created, deps installed.

---

## Step 0 -- Shared decisions (agreed between Luca and Hudson)
- "How old" = days stuck in current status (`updatedAt`), not days past due date. This is
  what the agent is chasing, but a finance person could reasonably read it the other way --
  worth flagging in the demo.
- `AGING_THRESHOLDS = [7, 14, 30]` (from config stub); `aging.py` reads config, not hardcoded.
  Verified live via monkeypatch in `test_classify_reads_config_not_hardcoded`.
- `TIMEZONE = "UTC"` (config stub); `formatter.py` reads it via `ZoneInfo(config.TIMEZONE)`
  with fallback to `timezone.utc`. Both config values are wired in, not dead stubs.
- tzdata note: `ZoneInfo("UTC")` works without the `tzdata` package. If config sets a non-UTC
  IANA timezone (e.g. `"America/New_York"`), add `tzdata` to `requirements.txt` -- otherwise
  `ZoneInfoNotFoundError` on Windows. The fallback in `formatter._get_tz()` catches it
  gracefully but the date silently shifts to UTC.
- Agreed on two shared files (`src/models.py` and `src/light_client.py`) so both sides' code
  would connect without surprises.

---

## Phase 1 -- Mock Data and MockLightClient (Luca)
- [2026-08-21] Prompted: create `src/models.py` and `src/light_client.py` (Step 0 shared
  files), then `data/mock_invoices.json` (10 invoices, 5 vendors, all 4 statuses, ages
  3/7/10/12/16/20/25/45 days, USD + EUR, Acme with 3 invoices, Hooli with 1 small invoice),
  `data/mock_vendors.json`, and `src/mock_client.py` per spec.
- GitHub was private/unreachable and gh CLI not installed, so `models.py` and
  `light_client.py` were written from spec rather than pulled.
- First run: `ModuleNotFoundError` for pydantic -- venv had not been created yet. Fixed by
  running `python -m venv .venv && pip install -r requirements.txt`.
- Second run: all 10 invoices parsed cleanly as `Invoice` objects; INV-1003 and INV-1007
  correctly show as NAIVE (no tzinfo), the rest timezone-aware. All 5 vendors loaded.
  `MockLightClient` smoke test green.

---

## Phase 2 -- Aging and Grouping Logic (Luca)
- [2026-08-21] Prompted: tests first (`test_aging.py` and `test_grouping.py` including
  `test_naive_datetime_does_not_crash`), then implement `src/aging.py` and `src/grouping.py`;
  `aging.py` must read `config.AGING_THRESHOLDS`, not hardcode thresholds.
- Run 1 (before implementation): 22 failed, all `ModuleNotFoundError` for `src.aging` and
  `src.grouping`. Expected; confirmed tests are running and failing for the right reason.
- Implemented `src/aging.py`: `_as_utc` coerces naive datetimes via `replace(tzinfo=utc)`,
  `compute_age_days` uses `timedelta.days`, `classify_bucket` unpacks
  `config.AGING_THRESHOLDS` into `watch/attention/overdue` and uses `<` comparisons at each
  boundary. `test_classify_reads_config_not_hardcoded` confirmed thresholds are live via
  monkeypatch.
- Implemented `src/grouping.py`: groups invoices with `defaultdict`, computes
  `total_by_currency` per vendor (multi-currency safe), tracks `oldest_age_days` and
  `worst_bucket` via `_BUCKET_RANK`, sorts `vendor_summaries` by
  `(bucket_rank, oldest_age_days)` descending.
- Run 2: 22 passed, 0 failed. No iteration needed. `test_naive_datetime_does_not_crash`
  passed: `_as_utc` absorbed the naive datetime without a `TypeError`.

---

## Phase 3 -- Message Formatting (Luca)
- [2026-08-21] Prompted: tests first (`test_formatter.py` including
  `test_bucket_labels_read_like_finance_not_engineering`), then implement `src/formatter.py`
  exporting `format_blocks` and `format_plain`. Header date from `config.TIMEZONE`. Status
  labels mapped to plain English. 50-block cap with truncation.
- Run 1 (before implementation): 17 failed, all `ModuleNotFoundError` for `src.formatter`.
- Implemented `formatter.py`: `_STATUS_LABELS` maps all four `InvoiceStatus` values to plain
  English (in draft, pending approval, pending accounting entry, awaiting payment).
  `_fmt_amount` uses currency symbols and thousands separators, suppresses `.00` on whole
  numbers. Block structure: header + summary section + divider + (section + actions + divider)
  per vendor. `_MAX_VENDORS = (50-3-1)//3 = 15`. `ZoneInfo(config.TIMEZONE)` with fallback
  to `timezone.utc` if zone unknown.
- Run 2: 17 passed, 0 failed. No iteration needed.
- Full suite: 39 passed, 0 failed across `test_aging.py`, `test_formatter.py`,
  `test_grouping.py`.
- Block Kit output: 18 blocks for 5 vendors. Confirmed `format_plain` reads like a finance
  alert, not an engineering log (no raw enum values).

### Phase 3 fix -- Vendor deep-links (Luca)
- [2026-08-21] Found that the "View in Light" button and vendor name in section headers both
  linked to the generic `https://app.light.inc/payables`, not the specific vendor's bills.
- Confirmed the Light search URL pattern: `https://app.light.inc/payables?search={vendor_name}`.
- Added `_vendor_url(name)` helper using `urllib.parse.quote_plus`. Updated vendor name in
  section headers to Slack mrkdwn link format (`<url|text>`). Updated button URL per vendor.
- Re-ran full suite: still 39 passed. Ran `--live --output slack`: Slack message posted,
  both vendor names and buttons are clickable deep-links into the correct vendor view.

---

## Phase 4 -- Config (Hudson)
- [2026-08-21] Pulled Luca's branch (`luca/data-logic-formatting`). Created
  `hudson/infra-client-cli` off it. Ran `pytest tests/`: 39 passed before touching anything,
  confirming the branch worked before building on top of it.
- Prompted: replace the `config.py` stub with a real version reading everything from `.env`
  via `python-dotenv`. Drop any `SLACK_BOT_TOKEN` handling -- only the webhook path was
  being built.
- Checked whether `AGING_THRESHOLDS` and `TIMEZONE` were actually used before deleting them
  -- Luca's build log confirmed both are wired into `aging.py` and `formatter.py`. Kept both
  as env-overridable with the same defaults as the stub.
- Added `LIGHT_API_BASE_URL`, `LIGHT_API_KEY`, `SLACK_WEBHOOK_URL`, `OUTPUT_FILE_PATH`.
  Created `.env.example` (committed, placeholder values) and local `.env` (gitignored).
  Confirmed via `git status` that only `.env.example` shows up as untracked.
- Verified: loading `config` prints all values correctly. Re-ran `pytest tests/`: still 39
  passed.
- **Caught before Phase 5:** re-reading the plan while starting `sinks.py` revealed the first
  `config.py` pass was missing `USE_MOCK_DATA`, `OUTPUT_MODE`, `SLACK_CHANNEL_ID`,
  `SCHEDULE_TIME`, and `validate()`. Rewrote `config.py` to match the plan spec. Re-verified
  39/39 still passed.
- Later confirmed with the team that `LIGHT_COMPANY_ENTITY_ID` is not required by the real
  API at all -- removed entirely in Phase 6 rather than leaving an unused stub.

---

## Phase 5 -- Output Sinks (Hudson)
- [2026-08-21] Prompted: `src/sinks.py` with `ConsoleSink`, `FileSink`, `WebhookSink` behind
  one `Sink` interface, `get_sink()` selecting by `config.OUTPUT_MODE`. `WebhookSink.send`
  must catch `httpx` failures and raise a clear message, not let a raw traceback surface.
- `ConsoleSink` prints the plain-text summary. `FileSink` appends a timestamped block to
  `config.OUTPUT_FILE_PATH` (opened with `encoding="utf-8"`, creates parent dirs).
  `WebhookSink` posts `{"blocks": ..., "text": ...}` to `config.SLACK_WEBHOOK_URL`, catches
  `httpx.HTTPStatusError` and `httpx.RequestError` separately, re-raises as `RuntimeError`
  with a readable message. `get_sink()` raises `ValueError` on an unrecognized `OUTPUT_MODE`.
- Smoke-tested end to end (mock client -> grouping -> formatting -> sinks): `ConsoleSink` and
  `FileSink` both produced correct output on the first run.
- **One scare, not a bug:** EUR amounts printed as a mangled character in the terminal.
  Verified with `ord()` that the actual character in memory is U+20AC and the file bytes
  decode as valid UTF-8 -- terminal display encoding, not a data or file-writing bug. No code
  change made.

---

## Phase 6 -- Live Client, first pass (Hudson)
- [2026-08-21] Confirmed `LIGHT_COMPANY_ENTITY_ID` not required by the real API. Removed it
  from `config.py`, `validate()`, `.env.example`, and `.env`.
- Read the real API docs at docs.light.inc (authentication, invoice-payables listing, vendor
  listing, rate limits) before writing any code.
- **Found a real mismatch before hitting the live API:** the real invoice `state` field has
  ~21 possible values; the shared `InvoiceStatus` enum has 4. `APPROVAL_REQUESTED` and
  several payment-stage states (`READY_FOR_PAYMENT_RELEASE`, `PENDING_PAYMENT_APPROVAL`,
  `PAYMENT_PENDING`, `UNPAID`) had no home in the enum. Flagged to the team before writing
  `live_client.py`.
- Decision: broad mapping. `APPROVAL_REQUESTED` counts as `APPROVAL_PENDING`; every
  payment-stage-short-of-paid state counts as `AWAITING_PAYMENT`.
- Implemented `src/live_client.py` against the real docs:
  - Endpoint: `GET /v1/bff/invoice-payables` (not `/invoice-payables`).
  - Envelope: `{"records": [...], "hasMore": bool, "nextCursor": str|null}`. Cursor starts
    at `"0"`.
  - Filter syntax: `filter=state:in:A|B|C` (pipe-separated within one condition).
  - Vendor is a nested object on the invoice (`vendor.vendorId`, `vendor.vendorName`).
  - Vendor list endpoint returns `vendorId`/`name`, not `id`/`name`.
  - Auth header, amount units: marked as NOTE comments, unverified until Phase 6b.
- Suite: still 39 passed.

---

## Phase 6b -- Live Verification (Hudson)
- [2026-08-21] Ran a raw call against the real invoice-payables endpoint with the real key.
  Result: 200, real data from "Light Demo UK". Corrected the base URL to the docs' literal
  value (not a separate demo subdomain).
- **Auth confirmed:** `Authorization: Basic <raw key>` (no base64, not Bearer) authenticates.
  Surprising given normal HTTP semantics, but the docs were right.
- **Pagination confirmed:** `records` / `hasMore` / `nextCursor` exactly as documented.
  `nextCursor` is an opaque token, not a page number.
- **`updatedAt` is timezone-aware.** Every record checked came back with a `Z` suffix.
  Luca's naive-datetime coercion in `_as_utc()` is defensive but wasn't actually needed
  against this endpoint. No crash risk found.
- **Two concrete data-shape issues found on real records:**
  1. Draft invoices can have `amount: null`, `currency: null`. Already defaulted safely
     (amount 0, currency falls back to USD) -- the defensive guess was correct.
  2. Draft invoices can have a completely empty vendor object -- no vendor ID. NOT handled
     safely: the grouping step does a plain dict lookup by vendor ID, which would crash.
     Confirmed real: 24 out of the first batch had this shape. Fixed at the client boundary:
     invoices with no vendor are skipped with a visible message. Nothing silently dropped.
- **Amount units:** docs say integer; guessed minor units (cents) and divided by 100. A real
  GBP invoice came back as 144400 -> plausible £1,444.00, but no independent ground-truth to
  fully confirm. Flagged honestly as "probably right, not proven."
- **Full live end-to-end run:** 521 real stuck invoices across 40 vendors (after skipping 24
  vendor-less drafts). Grouped by vendor, sorted by urgency, ages and currency totals all
  correct-looking.
- **Found and fixed a real scale bug:** one real vendor (Adobe Inc.) had 449 stuck invoices.
  The formatter capped how many *vendors* it displayed, not invoices per vendor. A 449-line
  block would have blown past Slack's section size limit and gotten the entire post rejected --
  possibly during the live demo itself. Fixed in `formatter.py`: capped each vendor's display
  at 10 invoices with a "+N more not shown" note. Reran full test suite: still 39/39 (no
  existing test used more than 3 invoices per vendor).
- **Verified against real payload limits post-fix:** the 521-invoice live run produces 49
  blocks (limit 50), max single section length 943 characters (limit 3000). Safe to post.
- **Tested a deliberately wrong API key:** clean, readable auth error returned, not a raw
  crash. Real key was only overridden in memory, never touched on disk.

---

## Phase 7 -- CLI Entry Point (Hudson)
- [2026-08-21] Implemented `src/main.py`: each stage (poll, group/format, send) wrapped in
  its own error handling so a failure prints a short, clear message and exits cleanly instead
  of a raw traceback. CLI resolves `--mock`/`--live`, applies `--output` before validating
  config, builds the right client and sink. `--schedule` runs once immediately then loops on
  a daily schedule.
- Pushed the branch to GitHub before starting this phase.
- **Gate 1** (`python -m src.main --mock --output console`): clean run, 10 mock invoices
  across 5 vendors, correctly grouped and aged. No changes needed.
- **Gate 2** (`python -m src.main --live --output console`): clean run against the real demo
  tenant. 521 real stuck invoices, 24 vendor-less drafts skipped with a visible message,
  40 vendors resolved. Adobe Inc.'s section correctly shows 10 invoices then
  "+439 more not shown".
- Both required gates pass clean.

---

## Final state
- **39 tests, 0 failures** across `test_aging.py`, `test_formatter.py`, `test_grouping.py`.
- **Gate 3** (`--live --output slack`): Slack message posted successfully. Every vendor name
  and "View in Light" button is a deep-link to that vendor's filtered payables view in Light.
- Branch `luca/data-logic-formatting` contains the complete merged codebase.
