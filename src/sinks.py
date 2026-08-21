"""Output sinks -- console, file, Slack webhook. Selected via config.OUTPUT_MODE."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import config


class Sink(ABC):
    @abstractmethod
    def send(self, blocks: list[dict], plain: str) -> None:
        """Deliver the alert. blocks is Slack Block Kit JSON, plain is the finance-readable fallback."""
        ...


class ConsoleSink(Sink):
    def send(self, blocks: list[dict], plain: str) -> None:
        print(plain)


class FileSink(Sink):
    def __init__(self, path: str = None):
        self._path = Path(path or config.OUTPUT_FILE_PATH)

    def send(self, blocks: list[dict], plain: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._path.open("a", encoding="utf-8") as f:
            f.write(f"--- {timestamp} ---\n{plain}\n\n")
        print(f"Wrote alert to {self._path}")


class WebhookSink(Sink):
    def __init__(self, url: str = None):
        self._url = url or config.SLACK_WEBHOOK_URL
        if not self._url:
            raise EnvironmentError("SLACK_WEBHOOK_URL is not set")

    def send(self, blocks: list[dict], plain: str) -> None:
        payload = {"blocks": blocks, "text": plain}
        try:
            r = httpx.post(self._url, json=payload, timeout=15)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Slack rejected the webhook post (HTTP {e.response.status_code}): "
                f"{e.response.text[:300]!r}. Check SLACK_WEBHOOK_URL and the Block Kit payload."
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(
                f"Could not reach the Slack webhook URL: {e}. Check SLACK_WEBHOOK_URL and your network."
            ) from e
        print("Posted alert to Slack.")


_SINKS = {
    "console": ConsoleSink,
    "file": FileSink,
    "slack": WebhookSink,
}


def get_sink() -> Sink:
    try:
        sink_cls = _SINKS[config.OUTPUT_MODE]
    except KeyError:
        raise ValueError(
            f"Unknown OUTPUT_MODE '{config.OUTPUT_MODE}', expected one of {list(_SINKS)}"
        )
    return sink_cls()
