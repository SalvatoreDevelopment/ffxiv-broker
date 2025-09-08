from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from redis.asyncio import Redis

from ..config import settings


@lru_cache(maxsize=1)
def get_redis() -> Redis[str]:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def ns(namespace: str, key: str) -> str:
    return f"{namespace}:{key}"


async def get_json(key: str) -> Any | None:
    r = get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    r = get_redis()
    data = json.dumps(value)
    if ttl and ttl > 0:
        await r.set(key, data, ex=ttl)
    else:
        await r.set(key, data)


async def ping() -> bool:
    r = get_redis()
    try:
        res = await r.ping()
        return bool(res)
    except Exception:
        return False
