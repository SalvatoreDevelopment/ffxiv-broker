from __future__ import annotations

from typing import Any

import asyncio
from fastapi import APIRouter, Query

from ...clients.universalis import get_item_world, get_marketable_items
from ...clients.xivapi import get_item_name
from ...config import settings
from ...services.advisor import rank_items
from ...services.metrics import (
    avg_price,
    flip_flag,
    median_price,
    quantile_price,
    roi as roi_fn,
    sales_per_day,
    saturation_flag,
    units_sold,
)


router = APIRouter(prefix="/advice", tags=["advice"])


@router.get("")
async def advice(
    world: str = Query(...),
    roi_min: float = Query(0.0),
    limit: int = Query(20, ge=1, le=100),
    max_candidates: int = Query(150, ge=10, le=1000),
    offset: int = Query(0, ge=0),
    ids: str | None = Query(None, description="Comma-separated item IDs to restrict candidates"),
    min_spd: float = Query(0.0, ge=0.0, description="Minimum sales/day to consider"),
    min_price: int = Query(0, ge=0, description="Minimum target price (gil)"),
    min_history: int = Query(0, ge=0, description="Minimum units sold in window"),
    target: str = Query(
        "avg",
        description="Target price baseline: avg|median|q (use quantile with q param)",
    ),
    q: float | None = Query(None, ge=0.0, le=1.0, description="Quantile for target=q"),
) -> dict[str, Any]:
    """Compute real advice using market data.

    Strategy:
      - Build candidates from `ids` or from Universalis marketable list (windowed by offset/max_candidates)
      - For each candidate: fetch Universalis data (cached), compute lowest, avg7, spd, flags
      - Estimate flip ROI: sell at avg7 (net after fees), buy at lowest
      - Rank via advisor.compute_score and return top `limit`
    """
    # 1) Resolve candidate IDs
    candidate_ids: list[int]
    if ids:
        try:
            candidate_ids = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            candidate_ids = []
    else:
        all_ids = await get_marketable_items()
        if offset < 0:
            offset = 0
        start = min(offset, max(0, len(all_ids) - 1))
        end = min(len(all_ids), start + max_candidates)
        candidate_ids = all_ids[start:end]

    # 2) Fetch and compute metrics with bounded concurrency
    sem = asyncio.Semaphore(max(1, min(settings.REQUESTS_RPS, 20)))

    async def _one(iid: int) -> dict[str, Any] | None:
        async with sem:
            try:
                data = await get_item_world(iid, world)
                listings = data.get("listings", [])
                history = data.get("recentHistory", [])
                if not (listings or history):
                    return None
                lowest = min((l["pricePerUnit"] for l in listings), default=None)
                spd = sales_per_day(history, days=7)
                sold = units_sold(history, days=7)
                # Select target price according to requested baseline
                tgt: float | None
                if q is not None:
                    tgt = quantile_price(history, q=q, days=7)
                elif target == "median":
                    tgt = median_price(history, days=7)
                else:
                    tgt = avg_price(history, days=7)

                if lowest is None or tgt is None:
                    return None
                if spd < min_spd:
                    return None
                if sold < min_history:
                    return None
                if tgt < float(min_price):
                    return None
                flags: list[str] = []
                if saturation_flag(stock_count=len(listings), spd=spd):
                    flags.append("saturo")
                if flip_flag(float(lowest), float(tgt)):
                    flags.append("flip")
                # Estimate ROI: sell at avg7, buy at lowest
                r = roi_fn(net_price=float(tgt), cost_total=float(lowest))
                name = await get_item_name(iid)
                return {
                    "item_id": iid,
                    "name": name,
                    "price": float(tgt),
                    "cost": float(lowest),
                    "sales_per_day": float(spd),
                    "flags": flags,
                    "roi": r,
                }
            except Exception:
                return None

    raw = await asyncio.gather(*[_one(i) for i in candidate_ids])
    candidates = [c for c in raw if c is not None]

    ranked = rank_items(candidates, min_roi=roi_min, min_spd=0.0)[:limit]
    return {
        "world": world,
        "items": [r.__dict__ for r in ranked],
        "count": len(ranked),
        "scanned": len(candidate_ids),
    }
