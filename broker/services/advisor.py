from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..services.metrics import roi

RISK_LOW = 0.3
RISK_MED = 0.6


@dataclass
class AdviceItem:
    item_id: int
    name: str | None
    roi: float
    sales_per_day: float
    score: float
    flags: list[str]
    risk: str


def compute_score(roi_value: float, sales_per_day: float, flags: list[str]) -> tuple[float, str]:
    # Normalize ROI to 0..1 over a rough range (-0.5..1.0)
    norm_roi = max(0.0, min(1.0, (roi_value + 0.5) / 1.5))
    vend = max(0.0, min(1.0, sales_per_day / 10.0))
    penalty = 0.0
    if "saturo" in flags:
        penalty += 0.2
    if "instabile" in flags:
        penalty += 0.2
    score = max(0.0, norm_roi * 0.7 + vend * 0.5 - penalty)

    risk = "basso"
    if score < RISK_LOW:
        risk = "alto"
    elif score < RISK_MED:
        risk = "medio"
    return score, risk


def rank_items(
    candidates: list[dict[str, Any]],
    min_roi: float = 0.0,
    min_spd: float = 0.0,
) -> list[AdviceItem]:
    results: list[AdviceItem] = []
    for c in candidates:
        r = roi(c.get("price", 0.0), c.get("cost", 1.0))
        spd = float(c.get("sales_per_day", 0.0))
        if r < min_roi or spd < min_spd:
            continue
        flags = list(c.get("flags", []))
        score, risk = compute_score(r, spd, flags)
        results.append(
            AdviceItem(
                item_id=int(c["item_id"]),
                name=c.get("name"),
                roi=r,
                sales_per_day=spd,
                score=score,
                flags=flags,
                risk=risk,
            )
        )
    results.sort(key=lambda x: x.score, reverse=True)
    return results
