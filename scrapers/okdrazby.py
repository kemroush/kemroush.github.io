"""Scraper for OK Dražby (okdrazby.cz)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .common import fetch, make_record

PORTAL_SLUG = "okdrazby"
PORTAL_LABEL = "OK Dražby"
BASE = "https://okdrazby.cz"

CATEGORIES = [
    ("domy",       "/drazby/nemovity/domy"),
    ("byty",       "/drazby/nemovity/byty"),
    ("pozemky",    "/drazby/nemovity/pozemky"),
    ("automobily", "/drazby/movity/automobily"),
    ("ostatni",    "/drazby/ostatni"),
]
STATUSES = ["prepared", "ongoing"]

MAX_PAGES = 50  # safety cap; categories cap at ~48 pages


def _parse_listing_page(html: str, category: str, status: str) -> list[dict]:
    """Extract all auction cards from a listing page."""
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []
    seen_ids: set[str] = set()

    # Cards are wrapped in <div class="AuctionsList_auctionContentContainer__XXXX">
    containers = soup.find_all(
        "div",
        class_=lambda c: c and any(cls.startswith("AuctionsList_auctionContentContainer_") for cls in (c if isinstance(c, list) else c.split())),
    )

    for card in containers:
        # Detail link + native ID
        name_link = card.find(
            "a",
            class_=lambda c: c and any(cls.startswith("AuctionsList_auctionName_") for cls in (c if isinstance(c, list) else c.split())),
        )
        if not name_link:
            continue
        href = name_link.get("href", "")
        m = re.search(r"/drazba/(\d+)-", href)
        if not m:
            continue
        native_id = m.group(1)
        if native_id in seen_ids:
            continue
        seen_ids.add(native_id)

        title = name_link.get_text(strip=True)
        link = href if href.startswith("http") else f"{BASE}{href}"

        # Image
        img = card.find("img")
        image = img.get("src", "") if img else ""

        # Location: bare <div> sibling between name and date block
        location = ""
        sibling = name_link.find_next_sibling("div")
        if sibling and not sibling.get("class"):
            location = sibling.get_text(strip=True)

        # Status badges
        badges: list[str] = []
        badge_text_divs = card.find_all(
            "div",
            class_=lambda c: c and any(cls.startswith("AuctionsList_auctionStatusTextContainer_") for cls in (c if isinstance(c, list) else c.split())),
        )
        for b in badge_text_divs:
            txt = b.get_text(strip=True)
            if txt and txt not in badges:
                badges.append(txt)

        # Start date+time: "13. 5. 2026 8:00"
        date_span = card.find(
            "span",
            class_=lambda c: c and any(cls.startswith("AuctionsList_auctionExactDateTime_") for cls in (c if isinstance(c, list) else c.split())),
        )
        start_date, start_time = "", ""
        if date_span:
            from .common import parse_cz_date
            start_date, start_time = parse_cz_date(date_span.get_text(strip=True))

        # Minimum bid
        price_div = card.find(
            "div",
            class_=lambda c: c and any(cls.startswith("AuctionsList_auctionPrice_") and "Label" not in cls for cls in (c if isinstance(c, list) else c.split())),
        )
        min_bid_text = price_div.get_text(strip=True) if price_div else ""

        records.append(make_record(
            portal=PORTAL_SLUG,
            portal_label=PORTAL_LABEL,
            native_id=native_id,
            category=category,
            status=status,
            title=title,
            location=location,
            min_bid_text=min_bid_text,
            start_date=start_date,
            start_time=start_time,
            image=image,
            link=link,
            badges=badges,
        ))

    return records


def scrape() -> list[dict]:
    all_records: list[dict] = []
    seen_global_ids: set[str] = set()

    for cat_slug, cat_path in CATEGORIES:
        for status in STATUSES:
            cat_count = 0
            prev_page_ids: set[str] = set()
            for page in range(1, MAX_PAGES + 1):
                url = f"{BASE}{cat_path}?statuses={status}&page={page}"
                html = fetch(url)
                if not html:
                    break
                page_records = _parse_listing_page(html, cat_slug, status)
                if not page_records:
                    break
                page_ids = {r["id"] for r in page_records}
                if page_ids == prev_page_ids:
                    break  # same page repeating → end of pagination
                prev_page_ids = page_ids
                for r in page_records:
                    if r["id"] in seen_global_ids:
                        continue
                    seen_global_ids.add(r["id"])
                    all_records.append(r)
                    cat_count += 1
            print(f"  okdrazby/{cat_slug}/{status}: +{cat_count}")

    print(f"  okdrazby total: {len(all_records)}")
    return all_records
