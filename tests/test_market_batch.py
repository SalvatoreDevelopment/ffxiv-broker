from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
import pytest


@pytest.mark.asyncio
async def test_market_items_batch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from broker.api.routes import market as m

    async def _get_items_world(ids: list[int], world: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for iid in ids:
            out.append(
                {
                    "listings": [{"pricePerUnit": iid * 10, "quantity": 1, "hq": False}],
                    "recentHistory": [],
                }
            )
        return out

    monkeypatch.setattr(m, "get_items_world", _get_items_world)

    r = client.get("/market/items", params={"world": "Phoenix", "ids": "1,2,3"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    items = data["items"]
    assert [it["item_id"] for it in items] == [1, 2, 3]
    assert items[0]["listings"][0]["pricePerUnit"] == 10

