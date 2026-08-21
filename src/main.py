"""Entry point for the Light posting alert agent.

Usage:
    python -m src.main --mock --output console       # Gate 2: no credentials needed
    python -m src.main --live --output console       # Gate 3: needs LIGHT_API_KEY
    python -m src.main --live --output slack         # Gate 4: needs both keys
    python -m src.main --live --output slack --schedule  # stretch goal: daily loop
"""
import argparse
import sys
import time
from pathlib import Path

from . import config
from .grouping import build_alert_summary
from .formatter import format_blocks, format_plain
from .sinks import get_sink


def _build_client(use_live: bool):
    if use_live:
        from .live_client import LiveLightClient
        return LiveLightClient()
    else:
        from .mock_client import MockLightClient
        return MockLightClient(data_dir=Path("data"))


def run_once(client, sink) -> None:
    """Fetch invoices, build summary, format, and send. One complete cycle."""
    invoices = client.list_stuck_invoices()

    if not invoices:
        print("No stuck invoices found -- nothing to send.")
        return

    vendor_ids = list({inv.vendorId for inv in invoices})
    vendors = client.get_vendors(vendor_ids)
    summary = build_alert_summary(invoices, vendors)
    blocks = format_blocks(summary)
    plain = format_plain(summary)
    sink.send(blocks, plain)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="src.main",
        description="Poll Light for stuck invoices and send a posting alert.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true", help="Use local mock data (no API key needed)")
    mode.add_argument("--live", action="store_true", help="Call the real Light API")

    parser.add_argument(
        "--output",
        choices=["console", "file", "slack"],
        default="console",
        help="Where to send the alert (default: console)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="(Stretch goal) Run once immediately, then daily at config.SCHEDULE_TIME",
    )

    args = parser.parse_args(argv)

    # Wire --output into config so get_sink() picks it up
    config.OUTPUT_MODE = args.output

    # Validate credentials before doing any network work
    # Temporarily override USE_MOCK_DATA so validate() checks the right path
    config.USE_MOCK_DATA = not args.live
    try:
        config.validate()
    except EnvironmentError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    try:
        client = _build_client(use_live=args.live)
        sink = get_sink()
    except (EnvironmentError, ValueError) as e:
        print(f"Setup error: {e}", file=sys.stderr)
        return 1

    if args.schedule:
        try:
            import schedule as sched
        except ImportError:
            print("The 'schedule' package is required for --schedule. Run: pip install schedule", file=sys.stderr)
            return 1

        print(f"Running now, then daily at {config.SCHEDULE_TIME} ...")
        try:
            run_once(client, sink)
        except Exception as e:
            print(f"Error during initial run: {e}", file=sys.stderr)

        sched.every().day.at(config.SCHEDULE_TIME).do(run_once, client, sink)
        while True:
            sched.run_pending()
            time.sleep(30)

    else:
        try:
            run_once(client, sink)
        except PermissionError as e:
            print(f"Auth error: {e}", file=sys.stderr)
            return 1
        except RuntimeError as e:
            print(f"Runtime error: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
