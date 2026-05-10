#!/usr/bin/env python3
"""
Auction Monitor — sběr dražeb z více portálů.

Generuje:
  data/auctions.json        – aktuální snapshot všech aktivních dražeb
  data/auctions_index.json  – meta info (last_updated, počty)
  data/auctions_seen.json   – mapa id → first_seen (pro detekci nových položek)

Požadavky:
  pip install beautifulsoup4 lxml
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from scrapers import ALL as SCRAPERS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CURRENT_FILE = os.path.join(DATA_DIR, "auctions.json")
INDEX_FILE   = os.path.join(DATA_DIR, "auctions_index.json")
SEEN_FILE    = os.path.join(DATA_DIR, "auctions_seen.json")


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    now_iso = datetime.now().isoformat(timespec="seconds")
    print(f"[{now_iso}] Auction monitor — start")

    seen: dict[str, str] = load_json(SEEN_FILE, {})  # id → first_seen date

    records: list[dict] = []
    per_portal: dict[str, int] = {}

    for module in SCRAPERS:
        slug = getattr(module, "PORTAL_SLUG", module.__name__)
        print(f"→ {slug}")
        try:
            portal_records = module.scrape()
        except Exception as e:
            print(f"  !! {slug} crashed: {e}")
            portal_records = []
        per_portal[slug] = len(portal_records)
        records.extend(portal_records)

    # Dedupe by id (in case of overlap)
    by_id: dict[str, dict] = {}
    for r in records:
        by_id[r["id"]] = r
    records = list(by_id.values())

    # Stamp first_seen / last_seen
    new_count = 0
    for r in records:
        if r["id"] not in seen:
            seen[r["id"]] = today
            new_count += 1
        r["first_seen"] = seen[r["id"]]
        r["last_seen"] = today

    # Sort: prepared first, then by start_date asc, then by min_bid_czk asc
    status_rank = {"ongoing": 0, "prepared": 1}
    records.sort(key=lambda r: (
        status_rank.get(r.get("status", ""), 9),
        r.get("start_date", "9999-99-99") or "9999-99-99",
        r.get("min_bid_czk", 0),
    ))

    # Per-category counts (across all portals)
    per_category: dict[str, int] = {}
    per_status: dict[str, int] = {}
    for r in records:
        per_category[r["category"]] = per_category.get(r["category"], 0) + 1
        per_status[r["status"]] = per_status.get(r["status"], 0) + 1

    save_json(CURRENT_FILE, records)
    save_json(SEEN_FILE, seen)
    save_json(INDEX_FILE, {
        "last_updated": now_iso,
        "today": today,
        "total": len(records),
        "new_today": new_count,
        "per_portal": per_portal,
        "per_category": per_category,
        "per_status": per_status,
    })

    print(f"✅ {len(records)} dražeb celkem ({new_count} nových dnes)")
    print(f"   portály: {per_portal}")
    print(f"   kategorie: {per_category}")
    print(f"   statusy: {per_status}")


if __name__ == "__main__":
    main()
