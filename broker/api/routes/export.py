from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ...exporters.excel import build_workbook
from .advice import advice as advice_endpoint


router = APIRouter(prefix="/export", tags=["export"])


@router.get("/excel/advice")
async def export_advice_excel(
    world: str = Query(...),
    roi_min: float = Query(0.0),
    limit: int = Query(50, ge=1, le=500),
    max_candidates: int = Query(150, ge=10, le=2000),
    min_spd: float = Query(0.0, ge=0.0),
    min_price: int = Query(0, ge=0),
    min_history: int = Query(0, ge=0),
    target: str = Query("avg"),
    q: float | None = Query(None, ge=0.0, le=1.0),
) -> StreamingResponse:
    """Generate an Excel workbook with current advice list.

    Uses the advice endpoint's output to populate the Advisor sheet. Items/Recipes
    sheets are left minimal for now and can be enriched later.
    """
    data = await advice_endpoint(
        world=world,
        roi_min=roi_min,
        limit=limit,
        max_candidates=max_candidates,
        min_spd=min_spd,
        min_price=min_price,
        min_history=min_history,
        target=target,
        q=q,
    )
    advice_items: list[dict[str, Any]] = [
        {
            "item_id": int(i.get("item_id")),
            "name": i.get("name"),
            "roi": float(i.get("roi", 0.0)),
            "sales_per_day": float(i.get("sales_per_day", 0.0)),
            "score": float(i.get("score", 0.0)),
            "flags": list(i.get("flags", [])),
            "risk": i.get("risk"),
        }
        for i in data.get("items", [])
    ]

    wb = build_workbook(items=[], recipes=[], advice=advice_items, world=world)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"ffxiv_advice_{world}.xlsx"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers=headers,
    )
