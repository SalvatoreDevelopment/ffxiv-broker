from __future__ import annotations

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    item_id: int
    quantity: int = Field(..., ge=1)
    hq_allowed: bool = True


class Recipe(BaseModel):
    result_item_id: int
    amount_result: int = 1
    ingredients: list[Ingredient]
