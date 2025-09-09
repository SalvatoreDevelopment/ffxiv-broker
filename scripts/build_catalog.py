from __future__ import annotations

import argparse
import asyncio
from typing import Any

from broker.clients.universalis import get_marketable_items
from broker.clients.xivapi import get_item_name
from broker.db.cache import get_redis
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
                            d.get("name")
                            or d.get("n")
                            or d.get("en")
                            or d.get("Name")
                        )
                    else:
                        name = (
                            data.get("name")
                            or data.get("n")
                            or data.get("en")
                            or data.get("Name")
                        )
                if isinstance(name, str) and name.strip():
                    return name
            except Exception:
                continue
    return None


async def build(limit: int, concurrency: int, batch_size: int, use_garland: bool) -> int:
    ids = await get_marketable_items()
    if not ids:
        print("No marketable IDs fetched")
        return 0
    ids = ids[: limit if limit > 0 else len(ids)]
    r = get_redis()
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(iid: int) -> tuple[int, str | None]:
        async with sem:
            try:
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
                return iid, name
            except Exception:
                return iid, None

    processed = 0
    mapping: dict[str, str] = {}
    tasks = [asyncio.create_task(one(i)) for i in ids]
    for fut in asyncio.as_completed(tasks):
        iid, name = await fut
        if name:
            mapping[str(iid)] = name
        if len(mapping) >= batch_size:
            await r.hset("x:names", mapping=mapping)  # type: ignore[arg-type]
            processed += len(mapping)
            mapping.clear()

    if mapping:
        await r.hset("x:names", mapping=mapping)  # type: ignore[arg-type]
        processed += len(mapping)
    return processed


def main() -> None:
    ap = argparse.ArgumentParser(description="Build id->name catalog in Redis")
    ap.add_argument("--limit", type=int, default=500, help="Max items to process (0=all)")
    ap.add_argument("--concurrency", type=int, default=10, help="Concurrent requests to XIVAPI")
    ap.add_argument("--batch-size", type=int, default=200, help="Batch size for Redis HSET")
    ap.add_argument("--use-garland", action="store_true", help="Fallback to GarlandTools for missing names")
    args = ap.parse_args()

    total = asyncio.run(build(args.limit, args.concurrency, args.batch_size, args.use_garland))
    print(f"Inserted names: {total}")


if __name__ == "__main__":
    main()
