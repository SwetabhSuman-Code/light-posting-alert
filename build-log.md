# Build Log -- Light Posting Alert

Format per entry: what we prompted Claude Code with, what came back,
what broke, how we fixed it. Do not clean up the "what broke" entries,
those are the point.

## Setup
- [2026-08-21] Repo scaffolded, venv created, deps installed.

## Step 0 decisions (agreed with Hudson)
- "How old" = days stuck in current status (updatedAt), not days past due date.
- AGING_THRESHOLDS = [7, 14, 30] (from config stub); aging.py reads config, not hardcoded. Verified live via monkeypatch in test_classify_reads_config_not_hardcoded.
- TIMEZONE = "UTC" (config stub); formatter.py reads it via ZoneInfo(config.TIMEZONE) with fallback to timezone.utc. Verified final state: both config values are wired in, not left as unused stubs.
- tzdata note: ZoneInfo("UTC") works without the tzdata package. If Hudson's real config.py sets a non-UTC IANA timezone (e.g. "America/New_York"), add tzdata to requirements.txt at merge -- otherwise ZoneInfoNotFoundError on Windows. The fallback in formatter._get_tz() will catch it gracefully, but the date will silently shift to UTC.

## Phase 1 -- Mock Data and MockLightClient
- [2026-08-21] Prompted: create src/models.py and src/light_client.py (Step 0 shared files), then data/mock_invoices.json (10 invoices, 5 vendors, all 4 statuses, ages 3/7/10/12/16/20/25/45 days, USD + EUR, Acme with 3 invoices, Hooli with 1 small invoice), data/mock_vendors.json, and src/mock_client.py per spec.
- GitHub was private/unreachable and gh CLI not installed, so models.py and light_client.py were written from spec rather than pulled.
- First run: ModuleNotFoundError for pydantic -- venv had not been created yet. Fixed by running `python -m venv .venv && pip install -r requirements.txt`.
- Second run: all 10 invoices parsed cleanly as Invoice objects; INV-1003 and INV-1007 correctly show as NAIVE (no tzinfo), the rest as timezone-aware. All 5 vendors loaded. MockLightClient smoke test green.

## Phase 2 -- Aging and Grouping Logic
- [2026-08-21] Prompted: tests first (test_aging.py and test_grouping.py including test_naive_datetime_does_not_crash), then implement src/aging.py and src/grouping.py; aging.py must read config.AGING_THRESHOLDS not hardcode thresholds.
- Run 1 (before implementation): 22 failed, all ModuleNotFoundError for src.aging and src.grouping. Expected; confirmed tests are actually running and failing for the right reason.
- Implemented src/aging.py: _as_utc coerces naive datetimes via replace(tzinfo=utc), compute_age_days uses timedelta.days, classify_bucket unpacks config.AGING_THRESHOLDS into watch/attention/overdue and uses < comparisons at each boundary. test_classify_reads_config_not_hardcoded confirmed thresholds are live via monkeypatch.
- Implemented src/grouping.py: groups invoices with defaultdict, computes total_by_currency per vendor (multi-currency safe), tracks oldest_age_days and worst_bucket via _BUCKET_RANK, sorts vendor_summaries by (bucket_rank, oldest_age_days) descending.
- Run 2: 22 passed, 0 failed. No iteration needed. test_naive_datetime_does_not_crash passed: _as_utc absorbed the naive datetime without a TypeError.

## Phase 3 -- Message Formatting
- [2026-08-21] Prompted: tests first (test_formatter.py including test_bucket_labels_read_like_finance_not_engineering), then implement src/formatter.py exporting format_blocks and format_plain. Header date from config.TIMEZONE. Status labels mapped to plain English. 50-block cap with truncation.
- Run 1 (before implementation): 17 failed, all ModuleNotFoundError for src.formatter.
- Implemented formatter.py: _STATUS_LABELS maps all four InvoiceStatus values to plain English (in draft, pending approval, pending accounting entry, awaiting payment). _fmt_amount uses currency symbols and thousands separators, suppresses .00 on whole numbers. Block structure is header + summary section + divider + (section + actions + divider) per vendor. _MAX_VENDORS = (50-3-1)//3 = 15. ZoneInfo(config.TIMEZONE) with fallback to timezone.utc if zone unknown.
- Run 2: 17 passed, 0 failed. No iteration needed.
- Full suite: 39 passed, 0 failed across test_aging.py, test_formatter.py, test_grouping.py.
- Block Kit output: 18 blocks for 5 vendors. Confirmed format_plain reads like a finance alert not an engineering log (no raw enum values).

## Phase 4 -- Config (Hudson)
- [2026-08-21] Pulled Luca's branch (luca/data-logic-formatting, the only branch pushed -- Step 0 files and Phases 1-3 all landed in one commit, no separate main). Created hudson/infra-client-cli off it. Ran `pytest tests/`: 39 passed before touching anything, confirmed the branch works before building on top of it.
- Prompted: replace the config.py stub with a real version reading everything from .env via python-dotenv. Drop any SLACK_BOT_TOKEN handling since only the webhook path is being built.
- Checked whether AGING_THRESHOLDS and TIMEZONE are actually used before deleting them, per the plan's cleanup note -- Luca's build log already confirms both are wired into aging.py and formatter.py, not dead stubs. Kept both, made them env-overridable (AGING_THRESHOLDS as comma-separated string parsed to ints, TIMEZONE as a plain string) with the same defaults as the stub, so behavior doesn't change unless .env sets something different.
- Added LIGHT_API_BASE_URL, LIGHT_API_KEY, SLACK_WEBHOOK_URL, OUTPUT_FILE_PATH for the phases ahead (live_client, sinks). No bot token anywhere.
- Created .env.example (committed, placeholder values) and a local .env (gitignored, confirmed via `git status` that only .env.example shows up as untracked, .env itself is invisible to git).
- Verified: `python -c "from src import config; print(...)"` loads all five values correctly. Re-ran `pytest tests/`: still 39 passed, config.py swap didn't break anything Luca built on the stub.
- Noted for later: Luca's build log flags that a non-UTC IANA TIMEZONE needs `tzdata` added to requirements.txt on Windows or ZoneInfo throws. Staying on the default "UTC" for this sprint per the Step 0 decision, so not adding tzdata now -- revisit if that default changes.
- **Caught before Phase 5:** re-read hudson-plan_revised.md while starting sinks.py and realized the first config.py pass was missing USE_MOCK_DATA, LIGHT_COMPANY_ENTITY_ID, OUTPUT_MODE, SLACK_CHANNEL_ID, SCHEDULE_TIME, and validate() -- all needed by later phases (live_client.py reads LIGHT_ENTITY_ID, sinks.py/main.py read OUTPUT_MODE and call validate()). Rewrote config.py to match the plan's spec, updated .env.example and .env to add the missing keys without touching the already-set LIGHT_API_KEY. Re-verified: config loads, validate() passes with defaults (mock mode, console output), pytest still 39/39.
- LIGHT_COMPANY_ENTITY_ID is still blank in .env -- need this from Hudson/whoever has the demo env details before Phase 6b live verification can run.

## Phase 5 -- Output Sinks (Hudson)
- [2026-08-21] Prompted: src/sinks.py with ConsoleSink, FileSink, WebhookSink behind one Sink interface, get_sink() selecting by config.OUTPUT_MODE. WebhookSink.send must catch httpx failures and raise a clear message, not let a raw traceback surface, since this is the path that posts live during the demo.
- Implemented: ConsoleSink prints the plain-text summary. FileSink appends a timestamped block to config.OUTPUT_FILE_PATH (opened with encoding="utf-8" explicitly, creates parent dirs). WebhookSink posts {"blocks": ..., "text": ...} to config.SLACK_WEBHOOK_URL, catches httpx.HTTPStatusError and httpx.RequestError separately and re-raises as RuntimeError with a specific, readable message (status code + truncated response body, or the connection error). get_sink() raises ValueError on an unrecognized OUTPUT_MODE instead of a KeyError.
- Smoke-tested against Luca's real pipeline end to end (MockLightClient -> build_alert_summary -> format_blocks/format_plain -> sinks), since her code already exists on this branch: ConsoleSink and FileSink both produced correct output on the first run, no iteration needed. get_sink() with default OUTPUT_MODE correctly returned ConsoleSink.
- One scare, not a bug: the EUR amounts printed as a mangled "?" character in this shell and when read back from the file. Verified with ord() that the actual character in memory is U+20AC (correct euro sign) and that the file's bytes decode as valid UTF-8 with no error -- this is the terminal's display encoding, not a data or file-writing bug. No code change made.
- WebhookSink not live-tested yet, SLACK_WEBHOOK_URL is still blank -- covered in Phase 7b.

## Phase 6 -- Live Client, first pass (Hudson)
- [2026-08-21] Confirmed with the team: LIGHT_COMPANY_ENTITY_ID is not required by the real API. Removed it from config.py, validate(), .env.example, and .env entirely rather than leaving an unused stub.
- Read the real API docs at docs.light.inc (getting-started/authentication, api-reference/v1--invoice-payables/list-invoice-payables, api-reference/v1--vendors/list-vendors, getting-started/rate-limits) before writing any code, instead of guessing blind like the plan's original example.
- **Found a real mismatch before even hitting the live API:** the real invoice `state` field has ~21 possible values; our shared InvoiceStatus enum has 4. Some line up exactly (IN_DRAFT, APPROVAL_PENDING, APPROVED_ACCOUNTING_ENTRY_PENDING) but APPROVAL_REQUESTED and several payment-stage states (READY_FOR_PAYMENT_RELEASE, PENDING_PAYMENT_APPROVAL, PAYMENT_PENDING, UNPAID) have no home in our enum. Feeding any of those straight into Invoice(**item) would throw a Pydantic ValidationError. Flagged this to the team before writing live_client.py rather than after, since it changes what "stuck" means, not just a field-name typo.
- Decision made: broad mapping. APPROVAL_REQUESTED counts as APPROVAL_PENDING; every payment-stage-short-of-paid state (READY_FOR_PAYMENT_RELEASE, PENDING_PAYMENT_APPROVAL, PAYMENT_PENDING, UNPAID) counts as AWAITING_PAYMENT. This matches the assignment's own wording ("draft or awaiting posting/approval") more literally than a narrow 1:1 name match would. Implemented as STUCK_STATE_MAP in live_client.py.
- Implemented src/live_client.py against the docs (not the plan's example code, since the plan's example was a guess written before docs access):
  - Endpoint is GET /v1/bff/invoice-payables, not /invoice-payables.
  - Envelope is {"records": [...], "hasMore": bool, "nextCursor": str|null}, not data/items + hasNextPage. Cursor pagination starts at "0" per docs.
  - Filter syntax is `filter=state:in:A|B|C` (pipe-separated within one condition, comma-separated between different conditions) -- one call for all stuck states instead of the plan's per-status loop.
  - Vendor is a nested object on the invoice (vendor.vendorId, vendor.vendorName), not a flat vendorId string -- _to_invoice() extracts it explicitly.
  - Vendor list endpoint returns `vendorId`/`name`, not `id`/`name` -- mapped explicitly when building Vendor objects.
- Everything still unverified against the real endpoint, marked with NOTE comments in the code, to be confirmed in Phase 6b:
  - Auth header: docs say "Authorization: Basic <key>", not the far more common Bearer scheme. This is the first thing to check if every live call 401s.
  - amount is documented as int64; guessed minor units (cents) and divided by 100. Could be wrong.
  - LIGHT_API_BASE_URL corrected from my own earlier guess (https://demo.light.inc/api, invented in Phase 4 before I had docs access) to the docs' literal base (https://api.light.inc). Still don't know if the "demo environment" is this same base URL with a demo API key, or a different subdomain -- first thing Phase 6b's live call will tell us.
- Constructed LiveLightClient() successfully with the real key loaded from .env (no network call yet). Full suite still 39 passed, config.py's entity-ID removal didn't break anything.
