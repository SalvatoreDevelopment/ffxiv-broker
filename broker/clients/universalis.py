from __future__ import annotations

import asyncio
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings
from ..db.cache import get_json, ns, set_json
from ..logging import get_logger

_log = get_logger()


def _retryer() -> AsyncRetrying:
    return AsyncRetrying(
        reraise=True,
        stop=stop_after_attempt(settings.RETRY_MAX),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=3),
        retry=retry_if_exception_type(
            (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.HTTPStatusError)
        ),
    )


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=str(settings.UNIVERSALIS_BASE),
        timeout=httpx.Timeout(10.0, read=10.0),
        headers={"User-Agent": settings.USER_AGENT},
        http2=True,
    )


async def get_item_world(item_id: int, world: str) -> dict[str, Any]:
    """Fetch item market data (listings + recentHistory) for a world, with caching.

    Cache keys:
      - u:{world}:{item_id}:listings
      - u:{world}:{item_id}:history
    """
    listings_key = ns("u", f"{world}:{item_id}:listings")
    history_key = ns("u", f"{world}:{item_id}:history")

    cached_listings = await get_json(listings_key)
    cached_history = await get_json(history_key)
    if cached_listings is not None and cached_history is not None:
        return {"listings": cached_listings, "recentHistory": cached_history}

    async with _client() as client:
        async for attempt in _retryer():
            with attempt:
                resp = await client.get(f"/v2/{world}/{item_id}")
                resp.raise_for_status()
                data = resp.json()
                listings = data.get("listings", [])
                history = data.get("recentHistory", [])
                await set_json(listings_key, listings, ttl=settings.CACHE_TTL_SHORT)
                await set_json(history_key, history, ttl=settings.CACHE_TTL_LONG)
                _log.info(
                    "universalis_item_fetched",
                    world=world,
                    item_id=item_id,
                    listings=len(listings),
                    history=len(history),
                )
                return {"listings": listings, "recentHistory": history}
    # Fallback to avoid mypy complaints; in practice, above paths return or raise
    return {"listings": [], "recentHistory": []}


async def get_items_world(item_ids: list[int], world: str) -> list[dict[str, Any]]:
    """Batch fetch items for a world.

    Universalis supports multi-item requests up to a limit; implement chunking/gather as needed.
    TODO: refine to use /v2/{world}/{comma_separated_ids} if appropriate.
    """
    # Simple concurrency guard to roughly respect RPS
    sem = asyncio.Semaphore(settings.REQUESTS_RPS)

    async def _fetch_one(iid: int) -> dict[str, Any]:
        async with sem:
            return await get_item_world(iid, world)

    results = await asyncio.gather(*[_fetch_one(i) for i in item_ids])
    return results
