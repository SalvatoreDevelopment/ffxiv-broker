from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ...services.advisor import rank_items

router = APIRouter(prefix="/advice", tags=["advice"])


@router.get("")
async def advice(
    world: str = Query(...),
    roi_min: float = Query(0.0),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    # Minimal placeholder: rank a few static items until real data wiring
    candidates = [
        {
            "item_id": 1,
            "name": "Sample A",
            "price": 10_000,
            "cost": 6_000,
            "sales_per_day": 4.0,
            "flags": [],
        },
        {
            "item_id": 2,
            "name": "Sample B",
            "price": 5_000,
            "cost": 5_200,
            "sales_per_day": 6.0,
            "flags": ["saturo"],
        },
        {
            "item_id": 3,
            "name": "Sample C",
            "price": 20_000,
            "cost": 9_000,
            "sales_per_day": 1.0,
            "flags": [],
        },
    ]
    ranked = rank_items(candidates, min_roi=roi_min, min_spd=0.0)[:limit]
    return {
        "world": world,
        "items": [r.__dict__ for r in ranked],
        "count": len(ranked),
    }
