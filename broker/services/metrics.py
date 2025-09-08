from __future__ import annotations

import statistics
import time
from collections.abc import Iterable

from ..models.market import Sale


def _cutoff_ts(days: int) -> int:
    return int(time.time()) - days * 86400


def avg_price(history: Iterable[Sale | dict[str, object]], days: int = 7) -> float | None:
    cutoff = _cutoff_ts(days)
    prices: list[float] = []
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            prices.append(float(sale.price_per_unit))
    if not prices:
        return None
    return statistics.mean(prices)


def sales_per_day(history: Iterable[Sale | dict[str, object]], days: int = 7) -> float:
    cutoff = _cutoff_ts(days)
    qty = 0
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            qty += int(sale.quantity)
    return qty / float(days)


def roi(
    net_price: float,
    cost_total: float,
    buyer_tax: float = 0.05,
    seller_tax: float = 0.05,
) -> float:
    if cost_total <= 0:
        return 0.0
    revenue = net_price * (1.0 - max(0.0, min(seller_tax, 1.0)))
    effective_cost = cost_total * (1.0 + max(0.0, min(buyer_tax, 1.0)))
    return (revenue - effective_cost) / effective_cost


def saturation_flag(stock_count: int, spd: float) -> bool:
    return stock_count > 5.0 * spd


def flip_flag(lowest: float, avg7: float | None) -> bool:
    if avg7 is None:
        return False
    return lowest < 0.7 * avg7
