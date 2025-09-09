from __future__ import annotations

from collections.abc import Iterable
import asyncio
from typing import Any

from ..clients.universalis import get_item_world, get_marketable_items
from ..config import settings
from ..db.cache import get_redis, ns, set_json
from ..clients.xivapi import get_item_name


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
