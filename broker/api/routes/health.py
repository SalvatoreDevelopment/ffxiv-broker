from __future__ import annotations

from fastapi import APIRouter

from ... import __version__
from ...db.cache import ping

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, object]:
    redis_ok = await ping()
    return {"status": "ok", "version": __version__, "redis": redis_ok}
