from __future__ import annotations

import asyncio
from typing import Any

import pytest

from broker.clients import universalis as u


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:  # mimic httpx.Response
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, on_get: Any) -> None:
        self._on_get = on_get
        self.calls = 0

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        return None

    async def get(self, url: str) -> _FakeResponse:
        self.calls += 1
        return await self._on_get(url)


@pytest.mark.asyncio
async def test_get_items_world_alignment_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    # Capture cache set calls
    set_calls: list[tuple[str, Any, int | None]] = []

    async def _set_json(key: str, value: Any, ttl: int | None = None) -> None:  # type: ignore[override]
        set_calls.append((key, value, ttl))

    monkeypatch.setattr(u, "set_json", _set_json)

    # Fake multi endpoint handler
    async def _on_get(url: str) -> _FakeResponse:
        assert "/v2/" in url and "/Phoenix/" in url
        ids_csv = url.rsplit("/", 1)[-1]
        ids = [int(s) for s in ids_csv.split(",")]
        # Return in reverse order to verify alignment in client
        items = []
        for iid in reversed(ids):
            items.append(
                {
                    "itemID": iid,
                    "listings": [{"pricePerUnit": iid * 10, "quantity": 1, "hq": False}],
                    "recentHistory": [
                        {
                            "pricePerUnit": iid * 7,
                            "quantity": 1,
                            "timestamp": 1_700_000_000,
                            "hq": False,
                        }
                    ],
                }
            )
        return _FakeResponse({"items": items})

    fake = _FakeClient(_on_get)
    monkeypatch.setattr(u, "_client", lambda: fake)

    ids = [1, 2, 3, 4, 5]
    res = await u.get_items_world(ids, "Phoenix")

    assert len(res) == len(ids)
    for iid, data in zip(ids, res):
        assert isinstance(data, dict)
        assert data.get("listings") and data.get("recentHistory")
        # Alignment: first listing price follows input order (iid*10)
        assert data["listings"][0]["pricePerUnit"] == iid * 10

    # Cache set_json called twice per item (listings + history)
    assert len(set_calls) == len(ids) * 2
    keys = [k for k, _, _ in set_calls]
    assert u.ns("u", f"Phoenix:{ids[0]}:listings") in keys
    assert u.ns("u", f"Phoenix:{ids[0]}:history") in keys


@pytest.mark.asyncio
async def test_get_items_world_chunking(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _on_get(url: str) -> _FakeResponse:
        calls.append(url)
        ids_csv = url.rsplit("/", 1)[-1]
        ids = [int(s) for s in ids_csv.split(",")]
        # Minimal payload per request
        items = [
            {"itemID": iid, "listings": [], "recentHistory": []} for iid in ids
        ]
        return _FakeResponse({"items": items})

    fake = _FakeClient(_on_get)
    monkeypatch.setattr(u, "_client", lambda: fake)

    # Request more than 100 IDs to force multiple chunks
    ids = list(range(1, 205 + 1))  # 205 -> 3 requests (100,100,5)
    res = await u.get_items_world(ids, "Phoenix")

    assert len(res) == len(ids)
    # Expect 3 batched GETs
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_get_items_world_parses_items_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate Universalis response shape with items as a mapping {"id": {...}}
    calls: list[str] = []

    async def _on_get(url: str) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(
            {
                "itemIDs": [10, 20],
                "items": {
                    "10": {"listings": [{"pricePerUnit": 100, "quantity": 1, "hq": False}], "recentHistory": []},
                    "20": {"listings": [{"pricePerUnit": 200, "quantity": 1, "hq": False}], "recentHistory": []},
                },
            }
        )

    fake = _FakeClient(_on_get)
    monkeypatch.setattr(u, "_client", lambda: fake)

    res = await u.get_items_world([10, 20], "Phoenix")
    assert len(res) == 2
    assert res[0]["listings"][0]["pricePerUnit"] == 100
    assert res[1]["listings"][0]["pricePerUnit"] == 200
