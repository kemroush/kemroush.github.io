"""Scraper for Portál Dražeb (portaldrazeb.cz).

Uses the public JSON API at /drazby/search.json — the same endpoint the Vue
frontend hits. One request returns up to ~10 000 records; we filter to
upcoming + ongoing client-side.
"""
from __future__ import annotations

import json
import subprocess

from .common import USER_AGENT, make_record

PORTAL_SLUG = "portaldrazeb"
PORTAL_LABEL = "Portál Dražeb"
BASE = "https://www.portaldrazeb.cz"
LIST_URL = f"{BASE}/drazby/search.json?limit=2000"

# Map portaldrazeb category slug → our standardized bucket.
CATEGORY_MAP = {
    "rodinny-dum":   "domy",
    "byt":           "byty",
    "pozemek":       "pozemky",
    "stavebni-pozemek": "pozemky",
    "auto-moto":     "automobily",
}

# Map their status → ours. Anything else (finished/deferred/cancelled) is dropped.
STATUS_MAP = {
    "upcoming": "prepared",
    "current":  "ongoing",
}


def _fetch_json(url: str) -> dict:
    try:
        result = subprocess.run(
            [
                "curl", "-sL", "--compressed",
                "-H", f"User-Agent: {USER_AGENT}",
                "-H", "Accept: application/json",
                url,
            ],
            capture_output=True, text=True, timeout=60,
        )
        return json.loads(result.stdout) if result.stdout else {}
    except Exception as e:
        print(f"    portaldrazeb fetch failed: {e}")
        return {}


def _map_category(item_cat: dict) -> str:
    slug = (item_cat or {}).get("slug", "")
    return CATEGORY_MAP.get(slug, "ostatni")


def _start_date_time(start_at: str) -> tuple[str, str]:
    if not start_at:
        return "", ""
    # ISO 8601: "2026-05-11T07:00:00.000+00:00"
    try:
        date_part, _, rest = start_at.partition("T")
        time_part = rest[:5] if rest else ""
        return date_part, time_part
    except Exception:
        return "", ""


def _record_from_api(r: dict) -> dict | None:
    status_raw = r.get("status", "")
    status = STATUS_MAP.get(status_raw)
    if not status:
        return None  # finished/deferred/cancelled — skip

    item = r.get("item") or {}
    title = (item.get("title") or "").strip()
    if not title:
        return None

    # Location: prefer city, fallback to district, then county
    loc = item.get("location_district") or {}
    city = (loc.get("city") or {}).get("city_name") or ""
    district = loc.get("district_name") or ""
    county = (loc.get("county") or {}).get("county_name") or ""
    location = city or district or county

    # Min bid: portaldrazeb's "minimal_bid" is often null at start; fallback to
    # item_price (= starting bid, typically 2/3 of estimated_price).
    min_bid_czk = r.get("minimal_bid") or r.get("item_price") or 0
    min_bid_text = f"{int(min_bid_czk):,} Kč".replace(",", " ") if min_bid_czk else ""

    start_date, start_time = _start_date_time(r.get("start_at", ""))

    # Image URL: first image by priority. Pattern: /upload/auction-image/{image_hash}
    images = r.get("images") or {}
    image = ""
    if images:
        # Sort by priority asc, take first
        first = sorted(images.items(), key=lambda kv: kv[1].get("priority", 999))[0]
        image_hash = first[0]
        image = f"{BASE}/upload/auction-image/{image_hash}"

    badges: list[str] = []
    if r.get("electronic"):
        badges.append("Elektronická")
    if r.get("voluntary"):
        badges.append("Dobrovolná")
    if r.get("repeated"):
        badges.append("Opakovaná")

    link = r.get("link") or f"{BASE}/drazba/{r.get('slug', '')}"
    native_id = r.get("hash") or r.get("slug")
    if not native_id:
        return None

    return make_record(
        portal=PORTAL_SLUG,
        portal_label=PORTAL_LABEL,
        native_id=native_id,
        category=_map_category(item.get("category")),
        status=status,
        title=title,
        location=location,
        min_bid_text=min_bid_text,
        start_date=start_date,
        start_time=start_time,
        image=image,
        link=link,
        badges=badges,
    )


def scrape() -> list[dict]:
    data = _fetch_json(LIST_URL)
    if not data:
        return []

    records: list[dict] = []
    skipped_status: dict[str, int] = {}
    for k, r in data.items():
        if not k.isdigit() or not isinstance(r, dict):
            continue
        rec = _record_from_api(r)
        if rec is None:
            skipped_status[r.get("status", "?")] = skipped_status.get(r.get("status", "?"), 0) + 1
            continue
        records.append(rec)

    print(f"  portaldrazeb total: {len(records)} (skipped {skipped_status})")
    return records
