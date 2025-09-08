from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..logging import configure_logging, request_id_middleware
from .routes import advice, craft, health, market


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

    app.include_router(health.router)
    app.include_router(market.router)
    app.include_router(craft.router)
    app.include_router(advice.router)

    return app


app = create_app()
