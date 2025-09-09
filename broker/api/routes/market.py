from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...clients.universalis import get_item_world
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
