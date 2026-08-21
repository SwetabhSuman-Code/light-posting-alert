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
