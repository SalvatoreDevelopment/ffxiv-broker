from __future__ import annotations

from typing import Any
import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_advice_uses_batched_market(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch candidates source to a small stable set
    from broker.api.routes import advice as adv

    async def _marketable() -> list[int]:
        return [101, 102, 103]
    monkeypatch.setattr(adv, "get_marketable_items", _marketable)

    used: dict[str, int] = {"calls": 0}

    async def _get_items_world(ids: list[int], world: str) -> list[dict[str, Any]]:
        used["calls"] += 1
        # Return aligned data: first empty (skip), next two with values
        out: list[dict[str, Any]] = []
        ts = int(time.time())
        for iid in ids:
            if iid == 101:
                out.append({"listings": [], "recentHistory": []})
            else:
                out.append(
                    {
                        "listings": [
                            {"pricePerUnit": iid * 10, "quantity": 1, "hq": False}
                        ],
                        "recentHistory": [
                            {
                                "pricePerUnit": iid * 12,  # target above lowest -> positive ROI
                                "quantity": 1,
                                "timestamp": ts,
                                "hq": False,
                            }
                        ],
                    }
                )
        return out

    async def _get_name(iid: int) -> str:
        return f"Item {iid}"

    monkeypatch.setattr(adv, "get_items_world", _get_items_world)
    monkeypatch.setattr(adv, "get_item_name", _get_name)

    r = client.get("/advice", params={"world": "Phoenix", "limit": 2, "max_candidates": 10})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert len(data["items"]) == 2
    # Ensure batched path used
    assert used["calls"] >= 1
