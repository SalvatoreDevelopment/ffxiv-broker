from __future__ import annotations

from fastapi.testclient import TestClient

STATUS_OK = 200


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == STATUS_OK
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
