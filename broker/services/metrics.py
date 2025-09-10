from __future__ import annotations

import statistics
import time
from collections.abc import Iterable

from ..models.market import Sale
from ..config import settings


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


def trimmed_mean_price(
    history: Iterable[Sale | dict[str, object]],
    days: int = 7,
    trim: float = 0.2,
) -> float | None:
    """Robust average using a symmetric trimmed mean over the price series.

    Discards `trim` fraction on each tail (e.g., 0.2 keeps the central 60%).
    """
    cutoff = _cutoff_ts(days)
    prices: list[float] = []
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            prices.append(float(sale.price_per_unit))
    if not prices:
        return None
    prices.sort()
    n = len(prices)
    k = int(n * max(0.0, min(0.45, trim)))
    core = prices[k : n - k] if n - k > k else prices
    if not core:
        core = prices
    return float(statistics.mean(core))


def prices_in_window(
    history: Iterable[Sale | dict[str, object]], days: int = 7
) -> list[float]:
    cutoff = _cutoff_ts(days)
    prices: list[float] = []
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            prices.append(float(sale.price_per_unit))
    return prices


def price_cv(history: Iterable[Sale | dict[str, object]], days: int = 7) -> float | None:
    """Coefficient of variation of per-sale prices in window: stdev/mean.

    Returns None if insufficient data (n < 2) or mean is zero.
    """
    ps = prices_in_window(history, days=days)
    if len(ps) < 2:
        return None
    mean = statistics.mean(ps)
    if mean == 0:
        return None
    try:
        stdev = statistics.stdev(ps)
    except statistics.StatisticsError:
        return None
    return stdev / mean


def quantile_price(
    history: Iterable[Sale | dict[str, object]],
    q: float = 0.5,
    days: int = 7,
) -> float | None:
    """Return the price quantile (e.g., median for q=0.5) over the window.

    Uses per-sale prices (unweighted). For robustness and speed we avoid weighting by
    quantities; adjust if needed.
    """
    cutoff = _cutoff_ts(days)
    prices: list[float] = []
    q = max(0.0, min(1.0, q))
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            prices.append(float(sale.price_per_unit))
    if not prices:
        return None
    prices.sort()
    idx = int(round((len(prices) - 1) * q))
    return prices[idx]


def median_price(history: Iterable[Sale | dict[str, object]], days: int = 7) -> float | None:
    return quantile_price(history, q=0.5, days=days)


def sales_per_day(history: Iterable[Sale | dict[str, object]], days: int = 7) -> float:
    cutoff = _cutoff_ts(days)
    qty = 0
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            qty += int(sale.quantity)
    return qty / float(days)


def units_sold(history: Iterable[Sale | dict[str, object]], days: int = 7) -> int:
    cutoff = _cutoff_ts(days)
    qty = 0
    for rec in history:
        sale = Sale.model_validate(rec) if isinstance(rec, dict) else rec
        if sale.timestamp >= cutoff:
            qty += int(sale.quantity)
    return qty


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


def net_profit_unit(
    target_price: float,
    lowest_cost: float,
    buyer_tax: float = 0.05,
    seller_tax: float = 0.05,
) -> float:
    """Absolute profit per unit after fees (gil)."""
    revenue = target_price * (1.0 - max(0.0, min(seller_tax, 1.0)))
    effective_cost = lowest_cost * (1.0 + max(0.0, min(buyer_tax, 1.0)))
    return revenue - effective_cost


def saturation_flag(stock_count: int, spd: float) -> bool:
    return stock_count > settings.ADVICE_SATURATION_MULT * spd


def flip_flag(lowest: float, avg7: float | None) -> bool:
    if avg7 is None:
        return False
    return lowest < settings.FLIP_THRESHOLD * avg7
