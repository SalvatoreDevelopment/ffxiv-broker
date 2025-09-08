from __future__ import annotations

from fastapi import APIRouter, Query

from ...services.craft import compute_craft_cost

router = APIRouter(prefix="/craft", tags=["craft"])


@router.get("/{item_id}")
async def craft_breakdown(item_id: int, world: str = Query(...)) -> dict[str, object]:
    cost = await compute_craft_cost(item_id, world)
    return {
        "item_id": item_id,
        "world": world,
        "total_cost_nq": cost.total_cost_nq,
        "total_cost_hq": cost.total_cost_hq,
        "breakdown": cost.breakdown,
    }
