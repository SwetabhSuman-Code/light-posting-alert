"""Shared data models -- agreed with Hudson in Step 0."""
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class InvoiceStatus(str, Enum):
    IN_DRAFT = "IN_DRAFT"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED_ACCOUNTING_ENTRY_PENDING = "APPROVED_ACCOUNTING_ENTRY_PENDING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"


class AgingBucket(str, Enum):
    FRESH = "FRESH"        # < 7 days
    WATCH = "WATCH"        # 7-13 days
    ATTENTION = "ATTENTION"  # 14-29 days
    OVERDUE = "OVERDUE"    # 30+ days


class Invoice(BaseModel):
    id: str
    vendorId: str
    amount: float
    currency: str
    status: InvoiceStatus
    updatedAt: datetime
    dueDate: Optional[datetime] = None
    description: Optional[str] = None


class Vendor(BaseModel):
    id: str
    name: str


class VendorSummary(BaseModel):
    vendor: Vendor
    invoices: list[Invoice]
    total_by_currency: dict[str, float]
    oldest_age_days: int
    worst_bucket: AgingBucket


class AlertSummary(BaseModel):
    vendor_summaries: list[VendorSummary]
    total_invoices: int
    bucket_counts: dict[AgingBucket, int]
    generated_at: datetime
