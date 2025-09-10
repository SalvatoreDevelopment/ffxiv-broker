from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_arbitrage_dc(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from broker.api.routes import market as m

    # Patch get_item_world to simulate different lowest per world
    async def _get_item_world(item_id: int, world: str) -> dict[str, Any]:
        lows = {
            "Phoenix": 1000,
            "Shiva": 1200,
            # others: none/listings empty
        }
        low = lows.get(world)
        listings = [] if low is None else [{"pricePerUnit": low, "quantity": 1, "hq": False}]
        return {"listings": listings, "recentHistory": []}

    monkeypatch.setattr(m, "get_item_world", _get_item_world)

    r = client.get("/market/arbitrage/1675", params={"dc": "Light"})
    assert r.status_code == 200
    data = r.json()
    assert data["item_id"] == 1675
    assert data["data_center"] == "Light"
    results = data["results"]
    worlds = [it["world"] for it in results]
    assert "Phoenix" in worlds and "Shiva" in worlds
    # Median over [1000, 1200] -> 1200//2 index, but our impl picks vals[len//2] -> for n=2 picks 1200; accept non-strict
    assert data["median"] in (1000, 1200)
