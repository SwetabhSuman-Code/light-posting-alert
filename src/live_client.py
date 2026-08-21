"""Live Light API client -- first pass written against docs.light.inc.
Every NOTE below is a guess pending Phase 6b live verification against the real demo env.
"""
import time
import httpx

from .light_client import LightClient
from .models import Invoice, InvoiceStatus, Vendor
from . import config

# The real API's invoice `state` field has ~21 values; our shared InvoiceStatus enum
# has 4. Mapping decided with the team (broad interpretation of "stuck"): an early-stage
# approval request counts the same as pending approval, and every payment-stage state
# short of actually paid counts as awaiting payment.
STUCK_STATE_MAP: dict[str, InvoiceStatus] = {
    "IN_DRAFT": InvoiceStatus.IN_DRAFT,
    "APPROVAL_REQUESTED": InvoiceStatus.APPROVAL_PENDING,
    "APPROVAL_PENDING": InvoiceStatus.APPROVAL_PENDING,
    "APPROVED_ACCOUNTING_ENTRY_PENDING": InvoiceStatus.APPROVED_ACCOUNTING_ENTRY_PENDING,
    "READY_FOR_PAYMENT_RELEASE": InvoiceStatus.AWAITING_PAYMENT,
    "PENDING_PAYMENT_APPROVAL": InvoiceStatus.AWAITING_PAYMENT,
    "PAYMENT_PENDING": InvoiceStatus.AWAITING_PAYMENT,
    "UNPAID": InvoiceStatus.AWAITING_PAYMENT,
}

# NOTE: docs say multiple values for one filter condition are pipe-separated
# ("state:in:IN_DRAFT|SCHEDULED|PAID"), unverified against the real endpoint.
_STATE_FILTER_VALUE = "|".join(STUCK_STATE_MAP.keys())


class LiveLightClient(LightClient):
    def __init__(self):
        if not config.LIGHT_API_KEY:
            raise EnvironmentError("LIGHT_API_KEY is not set")
        self._base = config.LIGHT_API_BASE_URL.rstrip("/")
        # NOTE: docs.light.inc/getting-started/authentication documents API-key auth as
        # "Authorization: Basic <key>", not the more common Bearer scheme -- unverified,
        # this is the first thing to check in Phase 6b if every call 401s.
        self._headers = {
            "Authorization": f"Basic {config.LIGHT_API_KEY}",
            "Accept": "application/json",
        }
        self._vendor_cache: dict[str, Vendor] = {}

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self._base}{path}"
        for attempt in range(3):
            try:
                r = httpx.get(url, headers=self._headers, params=params, timeout=15)
            except httpx.RequestError as e:
                if attempt == 2:
                    raise RuntimeError(f"Could not reach Light API at {url}: {e}") from e
                time.sleep(2 ** attempt)
                continue

            if r.status_code in (401, 403):
                raise PermissionError(f"Auth error {r.status_code} calling {path}: check LIGHT_API_KEY")
            if r.status_code == 429 and attempt < 2:
                time.sleep(int(r.headers.get("Retry-After", 2 ** attempt)))
                continue
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError:
                if r.status_code < 500 or attempt == 2:
                    raise
                time.sleep(2 ** attempt)
                continue
            return r.json()
        raise RuntimeError(f"Giving up on {path} after 3 attempts")

    def _paginate(self, path: str, params: dict):
        # NOTE: envelope per docs is {"records": [...], "hasMore": bool, "nextCursor": str|null},
        # not the data/items + hasNextPage shape originally guessed. Cursor starts at "0" per docs.
        cursor = "0"
        while True:
            data = self._get(path, params={**params, "cursor": cursor, "limit": 200})
            for record in data.get("records", []):
                yield record
            if not data.get("hasMore") or not data.get("nextCursor"):
                break
            cursor = data["nextCursor"]

    def list_stuck_invoices(self) -> list[Invoice]:
        params = {"filter": f"state:in:{_STATE_FILTER_VALUE}"}
        return [self._to_invoice(raw) for raw in self._paginate("/v1/bff/invoice-payables", params)]

    def _to_invoice(self, raw: dict) -> Invoice:
        real_state = raw["state"]
        status = STUCK_STATE_MAP.get(real_state)
        if status is None:
            raise ValueError(f"Unmapped invoice state {real_state!r} for invoice {raw.get('id')}")
        vendor_ref = raw.get("vendor") or {}
        # NOTE: amount is documented as int64 -- guessing minor units (cents) and dividing
        # by 100. Confirm against a real invoice's known amount in Phase 6b.
        amount = raw["amount"] / 100 if raw.get("amount") is not None else 0.0
        return Invoice(
            id=raw["id"],
            vendorId=vendor_ref.get("vendorId", ""),
            amount=amount,
            currency=raw.get("currency") or "USD",
            status=status,
            updatedAt=raw["updatedAt"],
            dueDate=raw.get("dueDate"),
            description=raw.get("invoiceNumber"),
        )

    def get_vendors(self, vendor_ids: list[str]) -> dict[str, Vendor]:
        missing = [vid for vid in vendor_ids if vid not in self._vendor_cache]
        if missing:
            # NOTE: no documented "filter by ids" example found, so this fetches every
            # vendor page by page and caches. Fine for a small demo tenant; revisit if slow.
            for raw in self._paginate("/v1/vendors", {}):
                vendor = Vendor(id=raw["vendorId"], name=raw["name"])
                self._vendor_cache[vendor.id] = vendor
        return {vid: self._vendor_cache[vid] for vid in vendor_ids if vid in self._vendor_cache}
