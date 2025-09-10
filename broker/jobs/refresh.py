from __future__ import annotations

from collections.abc import Iterable
import asyncio
from typing import Any

from ..clients.universalis import get_item_world, get_marketable_items, get_items_world
from ..config import settings
from ..db.cache import get_redis, ns, set_json
from ..clients.xivapi import get_item_name
from ..services.metrics import (
    sales_per_day,
    units_sold,
    trimmed_mean_price,
    avg_price,
    roi as roi_fn,
    net_profit_unit as profit_unit_fn,
    saturation_flag,
    flip_flag,
    price_cv,
)
from ..services.advisor import compute_score


async def refresh_items(world: str, items: Iterable[int]) -> int:
    """Force refresh cache for given items. Returns count of keys updated."""
    count = 0
    for iid in items:
        data = await get_item_world(iid, world)
        # Re-store to ensure fresh TTLs
        listings_key = ns("u", f"{world}:{iid}:listings")
        history_key = ns("u", f"{world}:{iid}:history")
        await set_json(listings_key, data.get("listings", []), ttl=settings.CACHE_TTL_SHORT)
        await set_json(history_key, data.get("recentHistory", []), ttl=settings.CACHE_TTL_LONG)
        count += 2
    return count


async def build_id_name_catalog(concurrency: int | None = None, batch_size: int = 1000) -> int:
    """Build or refresh the Redis hash catalog of item_id -> name.

    - Pulls marketable item IDs from Universalis
    - Fetches names from XIVAPI with limited concurrency
    - Stores results into Redis hash key `x:names`

    Returns number of items processed.
    """
    ids = await get_marketable_items()
    if not ids:
        return 0
    r = get_redis()
    sem = asyncio.Semaphore(concurrency or max(1, settings.REQUESTS_RPS // 2))

    async def _one(iid: int) -> tuple[int, str | None]:
        async with sem:
            try:
                name = await get_item_name(iid)
                return iid, name
            except Exception:
                return iid, None

    processed = 0
    mapping: dict[str, str] = {}
    for fut in asyncio.as_completed([_one(i) for i in ids]):
        iid, name = await fut
        if name:
            mapping[str(iid)] = name
        # Flush in batches to Redis to avoid oversized payloads
        if len(mapping) >= batch_size:
            await r.hset("x:names", mapping=mapping)  # type: ignore[arg-type]
            processed += len(mapping)
            mapping.clear()

    if mapping:
        await r.hset("x:names", mapping=mapping)  # type: ignore[arg-type]
        processed += len(mapping)

    # Also store the raw list of ids for reference
    # Note: large list; already cached by get_marketable_items()
    return processed


async def full_scan_advice(
    world: str,
    *,
    batch_size: int = 100,
    store_top: int = 3000,
) -> int:
    """Scan all Universalis marketable items for a world and cache ranked results.

    Stores results into Redis:
      - ZSET adv:{world}:score (score -> item_id)
      - HASH adv:{world}:data (item_id -> JSON payload)
      - STRING adv:{world}:count (number of candidates considered)
      - STRING adv:{world}:ts (unix timestamp when computed)

    Returns number of items stored.
    """
    import json, time

    ids = await get_marketable_items()
    if not ids:
        return 0

    r = get_redis()
    score_key_tmp = ns("adv", f"{world}:score:tmp")
    data_key_tmp = ns("adv", f"{world}:data:tmp")
    score_key = ns("adv", f"{world}:score")
    data_key = ns("adv", f"{world}:data")
    ts_key = ns("adv", f"{world}:ts")
    count_key = ns("adv", f"{world}:count")

    # Start fresh tmp keys
    await r.delete(score_key_tmp, data_key_tmp)

    candidates: list[dict[str, Any]] = []

    async def _process_chunk(chunk: list[int]) -> None:
        try:
            data_list = await get_items_world(chunk, world)
        except Exception:
            data_list = []
            for iid in chunk:
                try:
                    data_list.append(await get_item_world(iid, world))
                except Exception:
                    data_list.append({"listings": [], "recentHistory": []})

        for iid, data in zip(chunk, data_list):
            try:
                listings = data.get("listings", [])
                history = data.get("recentHistory", [])
                if not (listings or history):
                    continue
                lowest = min((l["pricePerUnit"] for l in listings), default=None)
                if lowest is None:
                    continue
                spd = sales_per_day(history, days=7)
                sold = units_sold(history, days=7)
                tgt = trimmed_mean_price(history, days=7, trim=0.2) or avg_price(history, days=7)
                if tgt is None:
                    continue
                flags: list[str] = []
                if saturation_flag(stock_count=len(listings), spd=spd):
                    flags.append("saturo")
                if flip_flag(float(lowest), float(tgt)):
                    flags.append("flip")
                rroi = roi_fn(net_price=float(tgt), cost_total=float(lowest))
                p_unit = profit_unit_fn(target_price=float(tgt), lowest_cost=float(lowest))
                ppd = float(spd) * p_unit
                comp = sum(1 for l in listings if float(l.get("pricePerUnit", 0)) <= float(tgt))

                # Anti-scam filter
                cv = price_cv(history, days=7)
                if (
                    rroi > settings.ADVICE_SUSPECT_ROI
                    and (sold < settings.ADVICE_MIN_SALES_SAFE or (cv is not None and cv > settings.ADVICE_SUSPECT_CV))
                ) or (
                    p_unit > float(settings.ADVICE_SUSPECT_ABS_PROFIT) and sold < settings.ADVICE_MIN_SALES_SAFE
                ):
                    continue

                score, risk = compute_score(rroi, float(spd), flags, float(ppd), int(comp))
                candidates.append(
                    {
                        "item_id": iid,
                        "name": None,
                        "roi": rroi,
                        "sales_per_day": float(spd),
                        "profit_unit": float(p_unit),
                        "profit_per_day": float(ppd),
                        "score": float(score),
                        "flags": flags,
                        "risk": risk,
                    }
                )
            except Exception:
                continue

    # Iterate in batches
    for i in range(0, len(ids), batch_size):
        await _process_chunk(ids[i : i + batch_size])

    # Sort by score and keep top N
    candidates.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    if store_top and len(candidates) > store_top:
        candidates = candidates[:store_top]

    # Store to Redis (tmp keys, then swap)
    if candidates:
        # Build zset payload and hash mapping
        zmembers: dict[str, float] = {}
        mapping: dict[str, str] = {}
        for c in candidates:
            iid = str(int(c["item_id"]))
            score_v = float(c.get("score", 0.0))
            zmembers[iid] = score_v
            mapping[iid] = json.dumps(c)
        # ZADD and HSET
        await r.zadd(score_key_tmp, zmembers)
        await r.hset(data_key_tmp, mapping=mapping)  # type: ignore[arg-type]

    # Swap keys
    await r.rename(score_key_tmp, score_key) if await r.exists(score_key_tmp) else None
    await r.rename(data_key_tmp, data_key) if await r.exists(data_key_tmp) else None
    await r.set(ts_key, str(int(time.time())))
    await r.set(count_key, str(len(ids)))
    return len(candidates)
