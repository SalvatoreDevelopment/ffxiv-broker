from __future__ import annotations

from typing import Any, cast

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings
from ..db.cache import get_json, get_redis, ns, set_json
from ..logging import get_logger

_log = get_logger()
HTTP_NOT_FOUND = 404


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
        base_url=str(settings.XIVAPI_BASE),
        timeout=httpx.Timeout(10.0, read=10.0),
        headers={"User-Agent": settings.USER_AGENT},
        http2=True,
    )


async def get_recipe(item_id: int) -> dict[str, Any] | None:
    """Fetch recipe for crafted item. Returns None if no recipe.

    Cached at key: x:recipe:{item_id}
    NOTE: This is a minimal implementation; nested ingredient resolution TBD.
    """
    key = ns("x", f"recipe:{item_id}")
    cached = await get_json(key)
    if cached is not None:
        return cast(dict[str, Any], cached)

    # XIVAPI recipe lookups (simplified): /search?indexes=recipe&filters=ItemResult.ID={item_id}
    async with _client() as client:
        async for attempt in _retryer():
            with attempt:
                resp = await client.get(
                    "/search",
                    params={
                        "indexes": "recipe",
                        "filters": f"ItemResult.ID={item_id}",
                        "columns": "Results.ID,Results.AmountResult,Results.Ingredients",
                    },
                )
                if resp.status_code == HTTP_NOT_FOUND:
                    return None
                resp.raise_for_status()
                data = cast(dict[str, Any], resp.json())
                results = data.get("Results", [])
                recipe = cast(dict[str, Any] | None, results[0] if results else None)
                await set_json(key, recipe, ttl=settings.CACHE_TTL_LONG)
                _log.info("xivapi_recipe_fetched", item_id=item_id, has_recipe=bool(recipe))
                return recipe

    # TODO: Garland fallback (static JSON) if XIVAPI incomplete
    return None


async def get_item_name(item_id: int) -> str | None:
    """Fetch item display name from XIVAPI, cached.

    Cache key: x:name:{item_id}
    Returns None if not found or on 404.
    """
    # 1) Check persistent catalog hash first (built by jobs)
    r = get_redis()
    name_hash = await r.hget("x:names", str(item_id))
    if name_hash is not None:
        return name_hash

    # 2) Check per-item cached value
    key = ns("x", f"name:{item_id}")
    cached = await get_json(key)
    if cached is not None:
        return cast(str | None, cached)

    try:
        async with _client() as client:
            async for attempt in _retryer():
                with attempt:
                    resp = await client.get(
                        f"/item/{item_id}", params={"columns": "ID,Name", "language": "en"}
                    )
                    if resp.status_code == HTTP_NOT_FOUND:
                        # Fallback: try search API for resilience
                        s = await client.get(
                            "/search",
                            params={
                                "indexes": "item",
                                "filters": f"ID={item_id}",
                                "columns": "Results.ID,Results.Name",
                                "language": "en",
                            },
                        )
                        if s.status_code == HTTP_NOT_FOUND:
                            return None
                        s.raise_for_status()
                        sd = cast(dict[str, Any], s.json())
                        results = sd.get("Results", []) or []
                        name = cast(str | None, (results[0] or {}).get("Name") if results else None)
                        if name:
                            # Store in both per-item cache and catalog hash
                            await set_json(key, name, ttl=settings.CACHE_TTL_LONG)
                            await r.hset("x:names", str(item_id), name)
                        _log.info("xivapi_item_name", item_id=item_id, name=name)
                        return name
                    resp.raise_for_status()
                    data = cast(dict[str, Any], resp.json())
                    name = cast(str | None, data.get("Name"))
                    if name is not None:
                        await set_json(key, name, ttl=settings.CACHE_TTL_LONG)
                        await r.hset("x:names", str(item_id), name)
                    _log.info("xivapi_item_name", item_id=item_id, name=name)
                    return name
    except httpx.HTTPError:
        # Continue to GarlandTools fallback below
        pass

    # Final fallback via Garland Tools API
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            rr = await c.get(
                "https://www.garlandtools.org/api/get.php",
                params={"type": "item", "id": str(item_id), "lang": "en"},
            )
            if rr.status_code == 200:
                data = cast(dict[str, Any], rr.json())
                d = cast(dict[str, Any] | None, data.get("item")) if isinstance(data, dict) else None
                name2 = cast(str | None, (d or {}).get("name") or (d or {}).get("en"))
                if name2:
                    await set_json(key, name2, ttl=settings.CACHE_TTL_LONG)
                    await r.hset("x:names", str(item_id), name2)
                    _log.info("garland_item_name", item_id=item_id, name=name2)
                    return name2
    except Exception:
        pass

    return None
