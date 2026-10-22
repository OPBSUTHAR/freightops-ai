"""Request/response schemas. Domain records are plain dicts in the store."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["LTL", "FTL", "Parcel", "Intermodal"]
DocKind = Literal["bol", "invoice", "packing_list", "auto"]


class RateRequest(BaseModel):
    origin: str = Field(min_length=2, examples=["Chicago, IL"])
    destination: str = Field(min_length=2, examples=["Dallas, TX"])
    mode: Mode = "LTL"
    weight_lb: float = Field(default=1200, gt=0, le=48000)
    equipment: str = "Dry Van 53'"
    commodity: str = "General freight"


class QuoteRequest(RateRequest):
    carrier_code: str
    margin_pct: float | None = Field(default=None, ge=0, le=60)


class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=400, examples=["Quote and book Chicago to Dallas, 1200 lb"])
    shipment_ref: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool
    note: str | None = None


class ResolveRequest(BaseModel):
    action: str = "manual_review"
    note: str | None = None


class ExtractRequest(BaseModel):
    text: str = Field(min_length=10)
    kind: DocKind = "auto"
    shipment_ref: str | None = None
    filename: str | None = None
