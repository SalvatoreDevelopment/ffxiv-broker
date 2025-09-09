from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..logging import configure_logging, request_id_middleware
from .routes import advice, catalog, craft, health, market
from .routes import export
from .routes.dashboard import router as dashboard_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="FFXIV Broker", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_id_middleware)

    # Static files and templates
    app.mount("/static", StaticFiles(directory="broker/api/static"), name="static")

    app.include_router(health.router)
    app.include_router(market.router)
    app.include_router(craft.router)
    app.include_router(advice.router)
    app.include_router(catalog.router)
    app.include_router(export.router)
    app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])

    # Startup task: bootstrap local catalog file into Redis if empty
    @app.on_event("startup")
    async def _bootstrap_catalog() -> None:  # pragma: no cover - side-effectful
        try:
            from ..config import settings as _settings
            from ..db.cache import get_redis
            import json, os

            path = _settings.CATALOG_BOOTSTRAP_PATH
            if not path:
                return
            if not os.path.exists(path):
                return
            r = get_redis()
            count = await r.hlen("x:names")
            if count and int(count) > 0:
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                await r.hset("x:names", mapping={str(k): str(v) for k, v in data.items()})  # type: ignore[arg-type]
        except Exception:
            # Best-effort: ignore bootstrap errors to not block the app
            pass

    return app


app = create_app()
