from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..clients.universalis import get_item_world
from ..clients.xivapi import get_recipe
from ..models.recipe import Ingredient, Recipe


@dataclass
class CraftCost:
    total_cost_nq: float
    total_cost_hq: float
    breakdown: list[dict[str, Any]]


async def resolve_recipe(item_id: int) -> Recipe | None:
    data = await get_recipe(item_id)
    if not data:
        return None
    # TODO: Convert XIVAPI response to Recipe model precisely. Minimal mapping for now.
    # Expecting data to contain Ingredients as list of {ItemIngredient: {ID}, AmountIngredient}
    ingredients: list[Ingredient] = []
    for ing in data.get("Ingredients", []) or []:
        iid = int(ing.get("ItemIngredient", {}).get("ID", 0))
        qty = int(ing.get("AmountIngredient", 0))
        if iid and qty:
            ingredients.append(Ingredient(item_id=iid, quantity=qty, hq_allowed=True))
    return Recipe(
        result_item_id=item_id,
        amount_result=int(data.get("AmountResult", 1) or 1),
        ingredients=ingredients,
    )


async def estimate_market_price(item_id: int, world: str) -> tuple[float, float]:
    """Return (nq_price, hq_price) estimates using current lowest listings.
    This is a naive estimator; refine as needed.
    """
    data = await get_item_world(item_id, world)
    listings = data.get("listings", [])
    if not listings:
        return (0.0, 0.0)
    nq = min((entry["pricePerUnit"] for entry in listings if not entry.get("hq")), default=None)
    hq = min((entry["pricePerUnit"] for entry in listings if entry.get("hq")), default=None)
    # Fallback: if one is None, use the other
    if nq is None and hq is None:
        return (0.0, 0.0)
    if nq is None:
        # hq must be set because not both None
        assert hq is not None
        nq = hq
    if hq is None:
        # nq must be set because not both None
        assert nq is not None
        hq = nq
    return (float(nq), float(hq))


async def compute_craft_cost(item_id: int, world: str, depth: int = 3) -> CraftCost:
    """Resolve multi-tier crafting costs with recursion guard and memoization.
    Currently uses market prices only; vendor prices TODO.
    """
    memo: dict[int, CraftCost] = {}

    async def _cost(iid: int, lvl: int) -> CraftCost:
        if iid in memo:
            return memo[iid]
        if lvl <= 0:
            nq, hq = await estimate_market_price(iid, world)
            cc = CraftCost(
                total_cost_nq=nq,
                total_cost_hq=hq,
                breakdown=[{"item_id": iid, "qty": 1, "nq": nq, "hq": hq}],
            )
            memo[iid] = cc
            return cc

        recipe = await resolve_recipe(iid)
        if not recipe or not recipe.ingredients:
            nq, hq = await estimate_market_price(iid, world)
            cc = CraftCost(
                total_cost_nq=nq,
                total_cost_hq=hq,
                breakdown=[{"item_id": iid, "qty": 1, "nq": nq, "hq": hq}],
            )
            memo[iid] = cc
            return cc

        parts: list[dict[str, Any]] = []
        total_nq = 0.0
        total_hq = 0.0
        for ing in recipe.ingredients:
            sub = await _cost(ing.item_id, lvl - 1)
            parts.extend(sub.breakdown)
            total_nq += sub.total_cost_nq * ing.quantity
            total_hq += sub.total_cost_hq * ing.quantity

        result = CraftCost(total_cost_nq=total_nq, total_cost_hq=total_hq, breakdown=parts)
        memo[iid] = result
        return result

    return await _cost(item_id, depth)
