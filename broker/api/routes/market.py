from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Query

from ...clients.universalis import get_item_world, get_items_world
from .dashboard import FFXIV_DATA_CENTERS  # reuse DC mapping
from ...config import settings
from ...models.market import ItemStats
from ...services.metrics import avg_price, flip_flag, sales_per_day, saturation_flag

router = APIRouter(prefix="/market", tags=["market"])


def _validate_world(world: str) -> None:
    allowed = settings.allowed_worlds()
    if allowed is not None and world not in allowed:
        raise HTTPException(status_code=400, detail="world not allowed")


@router.get("/item/{item_id}")
async def item_stats(
    item_id: int,
    world: str = Query(..., description="World name e.g. Phoenix"),
) -> ItemStats:
    _validate_world(world)
    data = await get_item_world(item_id, world)
    listings = data.get("listings", [])
    history = data.get("recentHistory", [])
    lowest = min((listing["pricePerUnit"] for listing in listings), default=None)
    a7 = avg_price(history, days=7)
    spd = sales_per_day(history, days=7)
    flags: list[str] = []
    if lowest is not None and saturation_flag(stock_count=len(listings), spd=spd):
        flags.append("saturo")
    if lowest is not None and a7 is not None and flip_flag(float(lowest), float(a7)):
        flags.append("flip")
    return ItemStats(
        item_id=item_id,
        world=world,
        lowest=lowest,
        avg_price_7d=a7,
        sales_per_day_7d=spd,
        flags=flags,
    )


@router.get("/item/{item_id}/raw")
async def item_raw(
    item_id: int,
    world: str = Query(..., description="World name e.g. Phoenix"),
) -> dict[str, object]:
    """Return raw Universalis data (listings + recentHistory) for charting/frontend."""
    _validate_world(world)
    data = await get_item_world(item_id, world)
    return {
        "item_id": item_id,
        "world": world,
        "listings": data.get("listings", []),
        "recentHistory": data.get("recentHistory", []),
    }


@router.get("/items")
async def items_raw(
    ids: str = Query(..., description="Comma-separated item IDs"),
    world: str = Query(..., description="World name e.g. Phoenix"),
) -> dict[str, object]:
    """Return raw Universalis data for multiple items in one call.

    Response shape aligns with single-item raw endpoint but for many items:
    {
      "world": "Phoenix",
      "count": N,
      "items": [ {"item_id": 1675, "listings": [...], "recentHistory": [...]}, ... ]
    }
    """
    _validate_world(world)
    try:
        item_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid ids parameter")
    if not item_ids:
        raise HTTPException(status_code=400, detail="ids required")

    data_list = await get_items_world(item_ids, world)
    items = []
    for iid, data in zip(item_ids, data_list):
        items.append(
            {
                "item_id": iid,
                "listings": data.get("listings", []),
                "recentHistory": data.get("recentHistory", []),
            }
        )
    return {"world": world, "count": len(items), "items": items}


@router.get("/arbitrage/{item_id}")
async def arbitrage_dc(
    item_id: int,
    dc: str = Query(..., description="Data Center name e.g. Light"),
) -> dict[str, object]:
    """Compare lowest prices for an item across all Worlds in a Data Center.

    Returns median of the lowest prices and a per-world list with optional lows.
    """
    if dc not in FFXIV_DATA_CENTERS:
        raise HTTPException(status_code=400, detail="unknown data center")

    worlds = list(FFXIV_DATA_CENTERS[dc])
    # Apply optional whitelist
    allowed = settings.allowed_worlds()
    if allowed is not None and len(allowed) > 0:
        worlds = [w for w in worlds if w in allowed]
    if not worlds:
        return {"item_id": item_id, "data_center": dc, "median": None, "results": []}

    async def _one(w: str) -> tuple[str, int | None]:
        try:
            data = await get_item_world(item_id, w)
            listings = data.get("listings", [])
            low = min((l["pricePerUnit"] for l in listings), default=None)
            return w, (int(low) if low is not None else None)
        except Exception:
            return w, None

    pairs = await asyncio.gather(*[_one(w) for w in worlds])
    results = [{"world": w, "lowest": v} for w, v in pairs]
    vals = sorted([v for _, v in pairs if v is not None])
    median = None
    if vals:
        median = vals[len(vals) // 2]
    # Sort by price asc, Nones at end
    results.sort(key=lambda r: (r["lowest"] is None, r["lowest"] if r["lowest"] is not None else 10**18))
    return {"item_id": item_id, "data_center": dc, "median": median, "results": results}
