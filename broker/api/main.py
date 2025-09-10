from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager

from .. import __version__
from ..logging import configure_logging, request_id_middleware
from .routes import advice, catalog, craft, health, market
from .routes import export
from .routes.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - integration lifecycle
    # Startup task: bootstrap local catalog file into Redis if empty
    try:
        from ..config import settings as _settings
        from ..db.cache import get_redis
        import json, os

        path = _settings.CATALOG_BOOTSTRAP_PATH
        if path and os.path.exists(path):
            r = get_redis()
            count = await r.hlen("x:names")
            if not count or int(count) <= 0:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    await r.hset(
                        "x:names",
                        mapping={str(k): str(v) for k, v in data.items()},  # type: ignore[arg-type]
                    )
    except Exception:
        # Best-effort: ignore bootstrap errors to not block the app
        pass
    try:
        yield
    finally:
        # No shutdown hooks at the moment
        pass


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="FFXIV Broker", version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_id_middleware)

    # Static files and templates (use absolute path within package)
    base_dir = Path(__file__).resolve().parent
    static_dir = base_dir / "static"
    # Starlette requires the directory to exist at mount time
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(health.router)
    app.include_router(market.router)
    app.include_router(craft.router)
    app.include_router(advice.router)
    app.include_router(catalog.router)
    app.include_router(export.router)
    app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])

    return app


app = create_app()
