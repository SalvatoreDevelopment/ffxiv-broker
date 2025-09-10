from __future__ import annotations

import asyncio
from typing import Any, cast, Iterable

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


def _chunks(seq: Iterable[int], size: int) -> Iterable[list[int]]:
    buf: list[int] = []
    for x in seq:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


async def get_items_world(item_ids: list[int], world: str) -> list[dict[str, Any]]:
    """Batch fetch items for a world using Universalis multi-ID endpoint.

    - Calls /v2/{world}/{ids_csv} in chunks (max ~100 per request for safety)
    - Stores per-item listings/history in cache with the same keys as get_item_world
    - Returns a list aligned to the input order; each element has keys 'listings' and 'recentHistory'
    """
    if not item_ids:
        return []

    # Prepare result slots aligned to input order
    order = {iid: idx for idx, iid in enumerate(item_ids)}
    out: list[dict[str, Any]] = [
        {"listings": [], "recentHistory": []} for _ in range(len(item_ids))
    ]

    # Limit per-request item count conservatively
    max_per_req = 100

    async with _client() as client:
        # Process in chunks to respect endpoint limits
        for group in _chunks(item_ids, max_per_req):
            ids_csv = ",".join(str(i) for i in group)
            async for attempt in _retryer():
                with attempt:
                    resp = await client.get(f"/v2/{world}/{ids_csv}")
                    resp.raise_for_status()
                    data = resp.json()

                    # Universalis multi endpoint can return:
                    #  - { items: { "123": {...}, "456": {...} }, itemIDs: [...] }
                    #  - or legacy { items: [ {...}, ... ] }
                    items_list: list[dict[str, Any]] = []
                    if isinstance(data, dict):
                        items_val = data.get("items")
                        if isinstance(items_val, dict):
                            for k, v in items_val.items():
                                try:
                                    iid_k = int(k)
                                except Exception:
                                    iid_k = None
                                if isinstance(v, dict):
                                    # Ensure itemID present for downstream logic
                                    if iid_k is not None and "itemID" not in v:
                                        v = {**v, "itemID": iid_k}
                                    items_list.append(cast(dict[str, Any], v))
                        elif isinstance(items_val, list):
                            items_list = cast(list[dict[str, Any]], items_val)  # type: ignore[assignment]
                        else:
                            # Single item object fallback
                            items_list = [cast(dict[str, Any], data)]

                    for item in items_list:
                        # Be defensive on key names
                        iid_any = (
                            item.get("itemID")
                            or item.get("itemId")
                            or item.get("item_id")
                            or item.get("item")
                        )
                        try:
                            iid = int(iid_any) if iid_any is not None else None
                        except Exception:
                            iid = None
                        if iid is None or iid not in order:
                            continue

                        listings = item.get("listings", [])
                        history = item.get("recentHistory", [])

                        # Update cache for each item, matching single fetch behavior
                        try:
                            listings_key = ns("u", f"{world}:{iid}:listings")
                            history_key = ns("u", f"{world}:{iid}:history")
                            await set_json(listings_key, listings, ttl=settings.CACHE_TTL_SHORT)
                            await set_json(history_key, history, ttl=settings.CACHE_TTL_LONG)
                        except Exception:
                            # Cache failures should not break data return
                            pass

                        out_idx = order[iid]
                        out[out_idx] = {"listings": listings, "recentHistory": history}

                    _log.info(
                        "universalis_items_fetched",
                        world=world,
                        count=len(items_list),
                        requested=len(group),
                    )

    return out


async def get_marketable_items() -> list[int]:
    """Fetch the Universalis global list of marketable (tradable) item IDs.

    Cached under key: u:marketable
    """
    key = ns("u", "marketable")
    cached = await get_json(key)
    if cached is not None:
        try:
            return [int(x) for x in cast(list[Any], cached)]
        except Exception:
            # fall through to refetch on malformed cache
            pass

    async with _client() as client:
        async for attempt in _retryer():
            with attempt:
                resp = await client.get("/marketable")
                resp.raise_for_status()
                data = resp.json()
                ids = [int(x) for x in data] if isinstance(data, list) else []
                # Store without TTL to make this job-driven and persistent
                await set_json(key, ids, ttl=None)
                _log.info("universalis_marketable_loaded", count=len(ids))
                return ids

    return []
