#!/usr/bin/env python3
"""
Script per raccogliere dataset completo degli item tradeable di FFXIV
Raccoglie: ID, Nome, Prezzo piu basso, Prezzo medio, Vendite giornaliere, Flags
"""

import asyncio
import csv
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx
from tqdm import tqdm

# Configurazione
UNIVERSALIS_BASE = "https://universalis.app/api"
XIVAPI_BASE = "https://xivapi.com"
import os
WORLD = os.environ.get("FFXIV_WORLD", "Phoenix")  # Cambia questo per altri server
OUTPUT_FILE = "data/ffxiv_market_dataset.csv"
BATCH_SIZE = 50  # Processa item in batch per evitare rate limiting


async def get_marketable_items() -> List[int]:
    """Ottiene la lista completa degli item tradeable da Universalis"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{UNIVERSALIS_BASE}/marketable")
        response.raise_for_status()
        return response.json()


async def get_item_name(item_id: int) -> str:
    """Ottiene il nome dell'item da XIVAPI"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{XIVAPI_BASE}/item/{item_id}")
            response.raise_for_status()
            data = response.json()
            return data.get("Name", f"Item_{item_id}")
    except Exception:
        return f"Item_{item_id}"


async def get_market_data(item_id: int, world: str) -> Dict[str, Any]:
    """Ottiene i dati di mercato per un item specifico"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{UNIVERSALIS_BASE}/v2/{world}/{item_id}")
            response.raise_for_status()
            data = response.json()

            listings = data.get("listings", [])
            history = data.get("recentHistory", [])

            # Calcola metriche
            lowest_price = min((listing["pricePerUnit"] for listing in listings), default=None)

            # Prezzo medio degli ultimi 7 giorni (filtra per timestamp)
            seven_days_ago = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
            recent_sales = [
                sale for sale in history if int(sale.get("timestamp", 0)) >= seven_days_ago
            ]
            avg_price = (
                sum(sale["pricePerUnit"] for sale in recent_sales) / len(recent_sales)
                if recent_sales
                else None
            )

            # Vendite giornaliere (ultimi 7 giorni)
            sales_per_day = len(recent_sales) / 7.0 if recent_sales else 0.0

            # Calcola %diff (variazione percentuale rispetto alla media)
            price_diff_percent = None
            if lowest_price is not None and avg_price is not None and avg_price > 0:
                price_diff_percent = round(((lowest_price - avg_price) / avg_price) * 100, 2)

            # Flags
            flags = []
            if len(listings) > 10 and sales_per_day < 2:
                flags.append("saturo")
            if (
                lowest_price is not None
                and avg_price is not None
                and lowest_price < avg_price * 0.8
            ):
                flags.append("flip")
            if price_diff_percent is not None and price_diff_percent < -20:
                flags.append("sottovalutato")
            if price_diff_percent is not None and price_diff_percent > 20:
                flags.append("sopravvalutato")

            return {
                "item_id": item_id,
                "lowest_price": lowest_price,
                "avg_price_7d": round(avg_price, 2) if avg_price is not None else None,
                "price_diff_percent": price_diff_percent,
                "sales_per_day_7d": round(sales_per_day, 2),
                "flags": ",".join(flags) if flags else "",
                "listings_count": len(listings),
                "history_count": len(history),
            }
    except Exception as e:
        print(f"Errore per item {item_id}: {e}")
        return {
            "item_id": item_id,
            "lowest_price": None,
            "avg_price_7d": None,
            "sales_per_day_7d": 0.0,
            "flags": "error",
            "listings_count": 0,
            "history_count": 0,
        }


async def process_batch(item_ids: List[int], world: str) -> List[Dict[str, Any]]:
    """Processa un batch di item in parallelo"""
    tasks = []
    for item_id in item_ids:
        task = get_market_data(item_id, world)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filtra risultati validi
    valid_results = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            result["item_id"] = item_ids[i]
            valid_results.append(result)

    return valid_results


async def main():
    """Funzione principale"""
    print("?? Inizio raccolta dataset FFXIV Market...")

    # 1. Ottieni lista item tradeable
    print("?? Ottenendo lista item tradeable...")
    marketable_items = await get_marketable_items()
    print(f"? Trovati {len(marketable_items)} item tradeable")

    # 2. Processa in batch per evitare rate limiting
    all_results = []

    for i in tqdm(range(0, len(marketable_items), BATCH_SIZE), desc="Processando item"):
        batch = marketable_items[i : i + BATCH_SIZE]
        batch_results = await process_batch(batch, WORLD)
        all_results.extend(batch_results)

        # Pausa tra batch per rispettare rate limits
        await asyncio.sleep(1)

    # 3. Ottieni nomi degli item
    print("??? Ottenendo nomi degli item...")
    for result in tqdm(all_results, desc="Aggiungendo nomi"):
        item_name = await get_item_name(result["item_id"])
        result["item_name"] = item_name
        await asyncio.sleep(0.1)  # Rate limiting per XIVAPI

    # 4. Salva dataset con formato Excel-compatibile
    print("?? Salvando dataset...")
    fieldnames = [
        "ID_Item",
        "Nome_Item",
        "Prezzo_Piu_Basso",
        "Prezzo_Medio_7g",
        "Diff_Percentuale",
        "Vendite_Giornaliere",
        "Flags",
        "Numero_Annunci",
        "Numero_Vendite",
    ]

    # Mappa i dati per Excel
    excel_data = []
    for result in all_results:
        excel_data.append(
            {
                "ID_Item": result["item_id"],
                "Nome_Item": result["item_name"],
                "Prezzo_Piu_Basso": result["lowest_price"]
                if result["lowest_price"] is not None
                else "",
                "Prezzo_Medio_7g": result["avg_price_7d"]
                if result["avg_price_7d"] is not None
                else "",
                "Diff_Percentuale": result["price_diff_percent"]
                if result["price_diff_percent"] is not None
                else "",
                "Vendite_Giornaliere": result["sales_per_day_7d"],
                "Flags": result["flags"],
                "Numero_Annunci": result["listings_count"],
                "Numero_Vendite": result["history_count"],
            }
        )

    # Salva con encoding UTF-8 BOM per Excel
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(excel_data)

    print(f"? Dataset salvato in {OUTPUT_FILE}")
    print(f"?? Totale item processati: {len(all_results)}")

    # Statistiche rapide
    with_data = [r for r in all_results if r["lowest_price"] is not None]
    print(f"?? Item con dati di mercato: {len(with_data)}")
    print(
        f"?? Item con opportunita flip: {len([r for r in with_data if 'flip' in r['flags']])}"
    )
    print(
        f"?? Item con mercato saturo: {len([r for r in with_data if 'saturo' in r['flags']])}"
    )


if __name__ == "__main__":
    asyncio.run(main())
