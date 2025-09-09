from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query

from ...clients.xivapi import get_item_name
from ...db.cache import get_redis, get_json, ns


router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/item/{item_id}")
async def item_name(
    item_id: int = Path(..., ge=1),
) -> dict[str, Any]:
    """Return item name by ID, reading from Redis hash and lazily populating if missing.

    If the name cannot be resolved, returns name = null and found = false.
    """
    r = get_redis()
    name = await r.hget("x:names", str(item_id))
    if name is None:
        # lazy fill via XIVAPI
        name = await get_item_name(item_id)
        if name:
            await r.hset("x:names", str(item_id), name)
    return {"item_id": item_id, "name": name, "found": name is not None}


@router.get("/search")
async def search(
    q: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Case-insensitive substring search over the id->name catalog.

    Implemented via HSCAN on Redis hash `x:names`, client-side filter.
    """
    q_raw = q.strip()
    q_norm = q_raw.casefold()
    r = get_redis()
    cursor: int = 0
    results: list[dict[str, Any]] = []
    # Iterate until we collect `limit` or we've scanned all
    while True:
        cursor, chunk = await r.hscan("x:names", cursor=cursor, count=1000)
        for k, v in chunk.items():
            if not q_norm or q_norm in v.casefold() or q_norm in k:
                results.append({"item_id": int(k), "name": v})
                if len(results) >= limit:
                    return {"count": len(results), "items": results}
        if cursor == 0:
            break

    # Numeric fallback: allow searching by ID even if name is missing
    digits = q_raw.lstrip("#")
    if digits.isdigit():
        ids_any = await get_json(ns("u", "marketable"))
        ids = [int(x) for x in (ids_any or [])]
        existing = {int(r["item_id"]) for r in results}
        for iid in ids:
            s = str(iid)
            if s.startswith(digits) and iid not in existing:
                results.append({"item_id": iid, "name": None})
                if len(results) >= limit:
                    break

    return {"count": len(results), "items": results}


@router.get("/stats")
async def stats(sample_missing: int = Query(0, ge=0, le=200)) -> dict[str, Any]:
    """Return catalog stats: counts and optional sample of missing IDs.

    - names_count: entries in Redis hash x:names
    - marketable_count: number of IDs in Universalis marketable list (if cached)
    - missing_count: marketable_count - names_count (approx)
    - missing_sample: up to N missing IDs
    """
    r = get_redis()
    names_count = int(await r.hlen("x:names"))
    ids_any = await get_json(ns("u", "marketable"))
    ids = [int(x) for x in (ids_any or [])]
    marketable_count = len(ids)
    result: dict[str, Any] = {
        "names_count": names_count,
        "marketable_count": marketable_count,
        "missing_count": max(0, marketable_count - names_count),
    }
    if sample_missing and marketable_count:
        named = {int(k) for k in await r.hkeys("x:names")}
        missing = [i for i in ids if i not in named]
        result["missing_sample"] = missing[:sample_missing]
    return result


@router.post("/refresh", include_in_schema=False)
async def refresh_catalog() -> dict[str, Any]:
    """No-op placeholder: recommend running the job via code or scheduler.

    Exposed for convenience; in production protect this route or disable it.
    """
    # Intentionally not building here to avoid long-running request.
    return {"status": "ok"}
