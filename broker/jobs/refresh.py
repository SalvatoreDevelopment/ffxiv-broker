from __future__ import annotations

from collections.abc import Iterable

from ..clients.universalis import get_item_world
from ..config import settings
from ..db.cache import ns, set_json


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
