from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, cast

import structlog
from fastapi import Request
from starlette.responses import Response

from .config import settings

request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_ctx_var.get()


def set_request_id(request_id: str | None) -> None:
    request_id_ctx_var.set(request_id)


def configure_logging() -> None:
    processors: list[Callable[..., Any]] = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(_level_to_numeric(settings.LOG_LEVEL)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _level_to_numeric(level: str) -> int:
    mapping = {
        "CRITICAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "INFO": 20,
        "DEBUG": 10,
        "NOTSET": 0,
    }
    return mapping.get(level.upper(), 20)


def _add_request_id(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


async def request_id_middleware(request: Request, call_next: Callable[[Request], Any]) -> Response:
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(rid)
    start = time.perf_counter()
    response = cast(Response, await call_next(request))
    duration_ms = (time.perf_counter() - start) * 1000
    structlog.get_logger().info(
        "request",
        method=request.method,
        path=request.url.path,
        status_code=getattr(response, "status_code", 0),
        duration_ms=round(duration_ms, 2),
    )
    # Clear after request
    set_request_id(None)
    response.headers["X-Request-ID"] = rid
    return response


def get_logger() -> Any:
    return structlog.get_logger()
