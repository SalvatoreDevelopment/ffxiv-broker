from __future__ import annotations

import time

from broker.services.metrics import avg_price, sales_per_day

AVG_LOW = 149.0
AVG_HIGH = 151.0
SPD_LOW = 0.42
SPD_HIGH = 0.44


def _mk_sale(price: int, qty: int, days_ago: int = 0) -> dict[str, object]:
    ts = int(time.time()) - days_ago * 86400 + 60
    return {"pricePerUnit": price, "quantity": qty, "timestamp": ts, "hq": False}


def test_avg_price_7d() -> None:
    history = [
        _mk_sale(100, 1, days_ago=1),
        _mk_sale(200, 2, days_ago=2),
        _mk_sale(300, 1, days_ago=8),  # outside window
    ]
    avg = avg_price(history, days=7)
    assert avg is not None
    # Average of 100 and 200 (pricePerUnit), not counting the 300
    assert AVG_LOW < avg < AVG_HIGH


def test_sales_per_day_7d() -> None:
    history = [
        _mk_sale(100, 1, days_ago=1),
        _mk_sale(200, 2, days_ago=2),
        _mk_sale(300, 1, days_ago=8),  # outside window
    ]
    spd = sales_per_day(history, days=7)
    # (1 + 2) / 7
    assert SPD_LOW < spd < SPD_HIGH
