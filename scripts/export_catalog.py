from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
from typing import Any

from broker.db.cache import get_redis


async def fetch_all() -> dict[str, str]:
    r = get_redis()
    # Use HGETALL for a consistent snapshot instead of iterative HSCAN
    data = await r.hgetall("x:names")
    return {str(k): str(v) for k, v in data.items()}


async def main() -> None:
    ap = argparse.ArgumentParser(description="Export id->name catalog from Redis")
    ap.add_argument("--format", choices=["json", "csv"], default="json")
    ap.add_argument("--out", default="data/catalog_names_en.json")
    args = ap.parse_args()

    data = await fetch_all()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    if args.format == "json":
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Wrote JSON: {args.out} ({len(data)} entries)")
    else:
        p = args.out
        if not p.lower().endswith(".csv"):
            p += ".csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["item_id", "name"])
            for k, v in data.items():
                w.writerow([k, v])
        print(f"Wrote CSV: {p} ({len(data)} entries)")


if __name__ == "__main__":
    asyncio.run(main())
