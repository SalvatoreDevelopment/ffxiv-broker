from __future__ import annotations

import argparse
import asyncio
from typing import Any

from broker.db.cache import get_redis, ns, get_json
from broker.clients.xivapi import get_item_name
import httpx


async def garland_item_name(item_id: int) -> str | None:
    endpoints = [
        f"https://www.garlandtools.org/api/get.php?type=item&id={item_id}&lang=en",
        f"https://www.garlandtools.org/db/doc/item/en/3/{item_id}.json",
        f"https://www.garlandtools.org/db/doc/item/en/2/{item_id}.json",
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        for url in endpoints:
            try:
                r = await client.get(url)
                if r.status_code != 200:
                    continue
                data = r.json()
                name = None
                if isinstance(data, dict):
                    if isinstance(data.get("item"), dict):
                        d = data["item"]
                        name = (
                            d.get("name") or d.get("n") or d.get("en") or d.get("Name")
                        )
                    else:
                        name = (
                            data.get("name") or data.get("n") or data.get("en") or data.get("Name")
                        )
                if isinstance(name, str) and name.strip():
                    return name
            except Exception:
                continue
    return None


async def list_missing(limit: int, try_fill: bool, use_garland: bool) -> list[int]:
    # Load universe of marketable IDs
    ids_any: Any = await get_json(ns("u", "marketable"))
    ids = [int(x) for x in (ids_any or [])]
    ids_set = set(ids)
    # Load keys already named
    r = get_redis()
    named_keys = await r.hkeys("x:names")
    named = {int(k) for k in named_keys}
    missing = sorted(ids_set - named)

    if try_fill and missing:
        # Try to fill a small batch to heal gaps
        tgt = missing[: min(limit, 200)]
        for iid in tgt:
            name = None
            try:
                name = await get_item_name(iid)
            except Exception:
                name = None
            if name is None and use_garland:
                try:
                    name = await garland_item_name(iid)
                except Exception:
                    name = None
            if name:
                await r.hset("x:names", str(iid), name)
        # Recompute
        named_keys = await r.hkeys("x:names")
        named = {int(k) for k in named_keys}
        missing = sorted(ids_set - named)

    return missing


def main() -> None:
    ap = argparse.ArgumentParser(description="List marketable IDs without names in catalog")
    ap.add_argument("--limit", type=int, default=50, help="Print first N missing IDs")
    ap.add_argument("--fill", action="store_true", help="Attempt to fill a small batch via XIVAPI/Garland (if enabled)")
    ap.add_argument("--use-garland", action="store_true", help="Use GarlandTools fallback for missing names")
    args = ap.parse_args()

    missing = asyncio.run(list_missing(args.limit, args.fill, args.use_garland))
    print(f"Missing count: {len(missing)}")
    print("Sample:", missing[: args.limit])


if __name__ == "__main__":
    main()
