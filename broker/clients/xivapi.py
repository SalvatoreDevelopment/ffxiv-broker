from __future__ import annotations

from typing import Any, cast

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings
from ..db.cache import get_json, ns, set_json
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
