"""Abstract client interface -- agreed with Hudson in Step 0."""
from abc import ABC, abstractmethod
from .models import Invoice, Vendor


class LightClient(ABC):

    @abstractmethod
    def list_stuck_invoices(self) -> list[Invoice]:
        """Return all invoices currently stuck in a non-terminal status."""
        ...

    @abstractmethod
    def get_vendors(self, vendor_ids: list[str]) -> dict[str, Vendor]:
        """Fetch vendor records by ID. Returns a dict keyed by vendor ID."""
        ...
