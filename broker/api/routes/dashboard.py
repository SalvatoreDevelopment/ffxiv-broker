from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ...config import settings
from ...clients.universalis import get_item_world
from ...clients.xivapi import get_item_name
from ...services.metrics import (
    avg_price, sales_per_day, saturation_flag, flip_flag
)
from .advice import advice as advice_endpoint


router = APIRouter()
templates = Jinja2Templates(directory="broker/api/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "page_title": "Dashboard FFXIV Market Advisor",
        },
    )


# Support both "/dashboard" and "/dashboard/"
@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_home_no_slash(request: Request):
    return await dashboard_home(request)


# FFXIV Data Centers and Worlds mapping
FFXIV_DATA_CENTERS = {
    "Light": ["Phoenix", "Shiva", "Zodiark", "Twintania", "Alpha", "Raiden"],
    "Chaos": ["Cerberus", "Louisoix", "Moogle", "Omega", "Ragnarok",
              "Sagittarius"],
    "Elemental": ["Aegis", "Atomos", "Carbuncle", "Garuda", "Gungnir",
                  "Kujata", "Ramuh", "Tonberry", "Typhon", "Unicorn"],
    "Gaia": ["Alexander", "Bahamut", "Durandal", "Fenrir", "Ifrit",
             "Ridill", "Tiamat", "Ultima", "Valefor", "Yojimbo", "Zeromus"],
    "Mana": ["Anima", "Asura", "Belias", "Chocobo", "Hades", "Ixion",
             "Mandragora", "Masamune", "Pandaemonium", "Shinryu", "Titan"],
    "Meteor": ["Balmung", "Brynhildr", "Coeurl", "Diabolos", "Goblin",
               "Malboro", "Mateus", "Seraph", "Ultros"],
    "Dynamis": ["Halicarnassus", "Maduin", "Marilith", "Seraph"],
    "Crystal": ["Balmung", "Brynhildr", "Coeurl", "Diabolos", "Goblin",
                "Malboro", "Mateus", "Seraph", "Ultros"],
    "Aether": ["Adamantoise", "Cactuar", "Faerie", "Gilgamesh", "Jenova",
               "Midgardsormr", "Sargatanas", "Siren"],
    "Primal": ["Behemoth", "Excalibur", "Exodus", "Famfrit", "Hyperion",
               "Lamia", "Leviathan", "Ultros"],
    "Materia": ["Bismarck", "Ravana", "Sephirot", "Sophia", "Zurvan"]
}

@router.get("/data/data-centers")
async def data_centers() -> dict[str, Any]:
    """Restituisce la lista dei Data Centers disponibili"""
    return {"data_centers": list(FFXIV_DATA_CENTERS.keys())}


@router.get("/data/worlds")
async def worlds(data_center: str | None = None) -> dict[str, Any]:
    """Restituisce la lista dei Worlds, opzionalmente filtrati per Data Center"""
    if data_center and data_center in FFXIV_DATA_CENTERS:
        return {"worlds": FFXIV_DATA_CENTERS[data_center]}

    # Se non specificato, restituisce tutti i worlds
    all_worlds = []
    for world_list in FFXIV_DATA_CENTERS.values():
        all_worlds.extend(world_list)

    # Controlla se ci sono mondi limitati nelle impostazioni
    allowed = settings.allowed_worlds()
    if allowed is not None and len(allowed) > 0:
        all_worlds = [w for w in all_worlds if w in allowed]

    return {"worlds": sorted(set(all_worlds))}


@router.get("/data/overview")
async def overview(
    world: str,
    limit: int = 8,
    source: str = "advice",
    roi_min: float = 0.0,
) -> dict[str, Any]:
    # 1) Ottieni lista ID item: da advice o fallback seed
    ids: list[int] = []
    names_hint: dict[int, str] = {}
    if source == "advice":
        try:
            # Call with explicit defaults to avoid FastAPI Query default objects
            data = await advice_endpoint(
                world=world,
                roi_min=roi_min,
                limit=limit,
                max_candidates=150,
                offset=0,
                ids=None,
                min_spd=0.0,
                min_price=0,
                min_history=0,
                target="avg",
                q=None,
            )
            for item in data.get("items", []):
                iid = int(item.get("item_id"))
                ids.append(iid)
                if item.get("name"):
                    names_hint[iid] = str(item["name"])
        except Exception:
            ids = []
    if not ids:
        seed_ids = [1675, 5, 19, 3976, 12538, 8166, 5330, 28064, 35946, 36064]
        ids = seed_ids[: max(1, min(limit, len(seed_ids)))]

    # 2) Fetch in parallelo: market data + nomi XIVAPI
    async def _one(iid: int) -> dict[str, Any]:
        data = await get_item_world(iid, world)
        listings = data.get("listings", [])
        history = data.get("recentHistory", [])
        lowest = min((listing["pricePerUnit"] for listing in listings),
                     default=None)
        a7 = avg_price(history, days=7)
        spd = sales_per_day(history, days=7)
        flags: list[str] = []
        if (lowest is not None and
                saturation_flag(stock_count=len(listings), spd=spd)):
            flags.append("saturo")
        if (lowest is not None and a7 is not None and
                flip_flag(float(lowest), float(a7))):
            flags.append("flip")
        name = (names_hint.get(iid) or
                await get_item_name(iid) or f"Item {iid}")
        return {
            "item_id": iid,
            "name": name,
            "lowest": lowest,
            "avg_price_7d": a7,
            "sales_per_day_7d": spd,
            "flags": flags,
        }

    items = await asyncio.gather(*[_one(i) for i in ids])
    return {"world": world, "count": len(items), "items": items}


@router.get("/market", response_class=HTMLResponse)
async def dashboard_market(request: Request):
    return templates.TemplateResponse(
        "market.html",
        {
            "request": request,
            "page_title": "Analisi Mercato",
        },
    )


@router.get("/portfolio", response_class=HTMLResponse)
async def dashboard_portfolio(request: Request):
    return templates.TemplateResponse(
        "portfolio.html",
        {
            "request": request,
            "page_title": "Portfolio Tracking",
        },
    )
