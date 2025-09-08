from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from broker.api.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _env() -> Iterator[None]:
    # Ensure test env uses local redis default unless provided
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    yield


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as c:
        yield c
