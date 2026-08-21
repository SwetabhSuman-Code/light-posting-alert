"""Output sinks -- ConsoleSink, FileSink, WebhookSink.

get_sink() returns the right one based on config.OUTPUT_MODE.
main.py overrides config.OUTPUT_MODE from the --output flag before calling this.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import config


class Sink(ABC):
    @abstractmethod
    def send(self, blocks: list[dict], plain: str) -> None:
        """Deliver the alert. blocks is Slack Block Kit JSON; plain is the fallback."""
        ...


class ConsoleSink(Sink):
    def send(self, blocks: list[dict], plain: str) -> None:
        print(plain)


class FileSink(Sink):
    def send(self, blocks: list[dict], plain: str) -> None:
        path = Path(config.OUTPUT_FILE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {ts} ---\n")
            f.write(plain)
            f.write("\n")
        print(f"Alert written to {path}")


class WebhookSink(Sink):
    def send(self, blocks: list[dict], plain: str) -> None:
        if not config.SLACK_WEBHOOK_URL:
            raise EnvironmentError("SLACK_WEBHOOK_URL is not set -- add it to .env")
        payload = {"blocks": blocks, "text": plain}
        try:
            r = httpx.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=15)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300]
            raise RuntimeError(
                f"Slack rejected the post (HTTP {e.response.status_code}): {body}\n"
                "Check SLACK_WEBHOOK_URL and the Block Kit payload."
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(
                f"Could not reach Slack webhook: {e}\n"
                "Check your network connection and SLACK_WEBHOOK_URL."
            ) from e


def get_sink() -> Sink:
    mode = config.OUTPUT_MODE
    if mode == "console":
        return ConsoleSink()
    elif mode == "file":
        return FileSink()
    elif mode == "slack":
        return WebhookSink()
    else:
        raise ValueError(
            f"Unknown OUTPUT_MODE {mode!r}. Expected console, file, or slack."
        )
