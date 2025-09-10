from __future__ import annotations

from typing import Any

import asyncio
from fastapi import APIRouter, Query

from ...clients.universalis import (
    get_item_world,  # kept for potential reuse
    get_marketable_items,
    get_items_world,
)
from ...clients.xivapi import get_item_name
from ...config import settings
from ...services.advisor import rank_items
from ...services.metrics import (
    avg_price,
    flip_flag,
    median_price,
    quantile_price,
    roi as roi_fn,
    net_profit_unit as profit_unit_fn,
    trimmed_mean_price,
    sales_per_day,
    saturation_flag,
    units_sold,
)
from ...db.cache import get_redis, ns


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

    # 2) Fetch market data in batches (multi-ID) then compute metrics
    candidates: list[dict[str, Any]] = []
    try:
        data_list = await get_items_world(candidate_ids, world)
    except Exception:
        # Fallback to per-item fetch on batch failure
        data_list = []
        for iid in candidate_ids:
            try:
                data_list.append(await get_item_world(iid, world))
            except Exception:
                data_list.append({"listings": [], "recentHistory": []})

    # Concurrency for name resolutions
    sem_name = asyncio.Semaphore(max(1, min(settings.REQUESTS_RPS // 2 or 1, 10)))

    async def _name(iid: int) -> str | None:
        async with sem_name:
            try:
                return await get_item_name(iid)
            except Exception:
                return None

    names = await asyncio.gather(*[_name(i) for i in candidate_ids])

    for iid, data, name in zip(candidate_ids, data_list, names):
        try:
            listings = data.get("listings", [])
            history = data.get("recentHistory", [])
            if not (listings or history):
                continue
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
                # Robust average to avoid outliers skewing ROI
                tgt = trimmed_mean_price(history, days=7, trim=0.2) or avg_price(history, days=7)

            if lowest is None or tgt is None:
                continue
            if spd < min_spd:
                continue
            if sold < min_history:
                continue
            if tgt < float(min_price):
                continue
            flags: list[str] = []
            if saturation_flag(stock_count=len(listings), spd=spd):
                flags.append("saturo")
            if flip_flag(float(lowest), float(tgt)):
                flags.append("flip")
            r = roi_fn(net_price=float(tgt), cost_total=float(lowest))
            p_unit = profit_unit_fn(target_price=float(tgt), lowest_cost=float(lowest))
            ppd = float(spd) * p_unit
            # Anti-scam: filter unrealistic opportunities (huge ROI/profit with poor evidence)
            from ...services.metrics import price_cv
            cv = price_cv(history, days=7)
            if (
                r > settings.ADVICE_SUSPECT_ROI
                and (sold < settings.ADVICE_MIN_SALES_SAFE or (cv is not None and cv > settings.ADVICE_SUSPECT_CV))
            ) or (
                p_unit > float(settings.ADVICE_SUSPECT_ABS_PROFIT) and sold < settings.ADVICE_MIN_SALES_SAFE
            ):
                # Skip suspicious item entirely
                continue
            # Approx competition: number of listings at/below target
            comp = sum(1 for l in listings if float(l.get("pricePerUnit", 0)) <= float(tgt))
            candidates.append(
                {
                    "item_id": iid,
                    "name": name,
                    "price": float(tgt),
                    "cost": float(lowest),
                    "sales_per_day": float(spd),
                    "flags": flags,
                    "roi": r,
                    "profit_unit": p_unit,
                    "profit_per_day": ppd,
                    "competition": comp,
                }
            )
        except Exception:
            continue

    ranked = rank_items(candidates, min_roi=roi_min, min_spd=0.0)[:limit]
    return {
        "world": world,
        "items": [r.__dict__ for r in ranked],
        "count": len(ranked),
        "scanned": len(candidate_ids),
    }


@router.get("/top")
async def advice_top(
    world: str = Query(...),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Return top N precomputed advice items from cache for the given world.

    Requires the full-scan job to have populated the cache. If empty, returns
    an empty list.
    """
    r = get_redis()
    score_key = ns("adv", f"{world}:score")
    data_key = ns("adv", f"{world}:data")
    ts_key = ns("adv", f"{world}:ts")
    ids = await r.zrevrange(score_key, 0, max(0, limit - 1))
    if not ids:
        return {"world": world, "items": [], "count": 0, "scanned": 0, "source": "empty"}
    # Fetch JSONs for those ids
    vals = await r.hmget(data_key, ids)
    items: list[dict[str, Any]] = []
    for raw in vals:
        try:
            obj = raw and __import__("json").loads(raw)  # type: ignore[arg-type]
            if isinstance(obj, dict):
                items.append(obj)
        except Exception:
            continue
    # Fill missing names lazily
    for it in items:
        if not it.get("name"):
            try:
                nm = await get_item_name(int(it.get("item_id", 0)))
                it["name"] = nm
            except Exception:
                pass
    ts = await r.get(ts_key)
    return {
        "world": world,
        "items": items[:limit],
        "count": min(limit, len(items)),
        "scanned": len(items),
        "source": "cache",
        "ts": ts,
    }
