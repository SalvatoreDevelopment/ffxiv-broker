from __future__ import annotations

from pydantic import BaseModel, Field


class Listing(BaseModel):
    price_per_unit: int = Field(..., alias="pricePerUnit", ge=0)
    quantity: int = Field(..., ge=1)
    hq: bool = False


class Sale(BaseModel):
    price_per_unit: int = Field(..., alias="pricePerUnit", ge=0)
    quantity: int = Field(..., ge=1)
    timestamp: int = Field(..., ge=0)  # Unix epoch seconds
    hq: bool = False


class ItemStats(BaseModel):
    item_id: int
    world: str
    lowest: int | None
    avg_price_7d: float | None
    sales_per_day_7d: float
    flags: list[str] = []
    notes: list[str] = []
