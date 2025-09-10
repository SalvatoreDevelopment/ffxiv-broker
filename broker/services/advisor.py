from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..services.metrics import roi
from ..config import settings

RISK_LOW = settings.ADVICE_RISK_LOW
RISK_MED = settings.ADVICE_RISK_MED


@dataclass
class AdviceItem:
    item_id: int
    name: str | None
    roi: float
    sales_per_day: float
    profit_per_day: float
    profit_unit: float
    score: float
    flags: list[str]
    risk: str


def compute_score(
    roi_value: float,
    sales_per_day: float,
    flags: list[str],
    profit_per_day: float,
    competition_count: int = 0,
) -> tuple[float, str]:
    # Normalize ROI to 0..1 over a rough range (-0.5..1.0)
    norm_roi = max(0.0, min(1.0, (roi_value + 0.5) / 1.5))
    vend = max(0.0, min(1.0, sales_per_day / settings.ADVICE_SPD_NORM))
    ppd = max(0.0, min(1.0, profit_per_day / settings.ADVICE_PPD_NORM))
    penalty = 0.0
    if "saturo" in flags:
        penalty += settings.ADVICE_PENALTY_SATURO
    if "instabile" in flags:
        penalty += settings.ADVICE_PENALTY_INSTABILE
    # Competition penalty scaled by number of listings below target
    comp_pen = min(1.0, max(0, competition_count) / 10.0) * settings.ADVICE_PENALTY_COMP
    penalty += comp_pen
    score = max(
        0.0,
        norm_roi * settings.ADVICE_W_ROI + vend * settings.ADVICE_W_SPD + ppd * settings.ADVICE_W_PPD - penalty,
    )

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
        ppd = float(c.get("profit_per_day", 0.0))
        comp = int(c.get("competition", 0))
        score, risk = compute_score(r, spd, flags, ppd, comp)
        results.append(
            AdviceItem(
                item_id=int(c["item_id"]),
                name=c.get("name"),
                roi=r,
                sales_per_day=spd,
                profit_per_day=ppd,
                profit_unit=float(c.get("profit_unit", 0.0)),
                score=score,
                flags=flags,
                risk=risk,
            )
        )
    results.sort(key=lambda x: x.score, reverse=True)
    return results
