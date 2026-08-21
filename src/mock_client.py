"""MockLightClient -- reads from data/ JSON files, no network required."""
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
