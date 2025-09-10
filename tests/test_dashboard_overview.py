from __future__ import annotations

from typing import Any
import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_dashboard_overview_batched(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from broker.api.routes import dashboard as d

    # Stub advice to provide IDs and names hint
    async def _advice(**kwargs: Any) -> dict[str, Any]:
        return {
            "items": [
                {"item_id": 201, "name": "Foo"},
                {"item_id": 202, "name": "Bar"},
                {"item_id": 203, "name": "Baz"},
            ]
        }

    used = {"calls": 0}
    ts = int(time.time())

    async def _get_items_world(ids: list[int], world: str) -> list[dict[str, Any]]:
        used["calls"] += 1
        out: list[dict[str, Any]] = []
        for iid in ids:
            out.append(
                {
                    "listings": [{"pricePerUnit": iid * 10, "quantity": 1, "hq": False}],
                    "recentHistory": [
                        {
                            "pricePerUnit": iid * 12,
                            "quantity": 1,
                            "timestamp": ts,
                            "hq": False,
                        }
                    ],
                }
            )
        return out

    monkeypatch.setattr(d, "advice_endpoint", _advice)
    monkeypatch.setattr(d, "get_items_world", _get_items_world)

    r = client.get("/dashboard/data/overview", params={"world": "Phoenix", "limit": 3, "source": "advice"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert len(data["items"]) == 3
    # Ensure batching path used
    assert used["calls"] == 1
    # Check metrics shape
    one = data["items"][0]
    assert "lowest" in one and "avg_price_7d" in one and "sales_per_day_7d" in one

