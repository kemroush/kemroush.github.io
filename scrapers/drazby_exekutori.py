"""Scraper for Dražby Exekutorů (drazby-exekutori.cz).

The site is ASP.NET WebForms with __doPostBack pagination — full pagination
would require sending POST requests with __VIEWSTATE and __EVENTVALIDATION
tokens. For now we just parse the homepage, which lists the 10 most recently
added auctions. The "seen" deduplication in auction_monitor.py means rotated
listings still accumulate over time.

TODO: implement VIEWSTATE-aware pagination to backfill all ~80 active auctions.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .common import fetch, make_record, parse_cz_date

PORTAL_SLUG = "drazby-exekutori"
PORTAL_LABEL = "Dražby Exekutorů"
BASE = "http://www.drazby-exekutori.cz"
HOMEPAGE = f"{BASE}/"

# Map keywords in the title → our standardized category bucket.
# Order matters: first match wins.
CATEGORY_KEYWORDS = [
    ("byty",       ["byt ", "bytu", "bytov", "bytové jednot"]),
    ("domy",       ["dům", "domu", "domku", "domku", "domek", "rodin"]),
    ("pozemky",    ["pozem"]),
    ("automobily", ["automobil", "vozidl", "osobní auto", "motocykl"]),
]


def _classify(title: str) -> str:
    t = title.lower()
    for cat, keywords in CATEGORY_KEYWORDS:
        if any(k in t for k in keywords):
            return cat
    return "ostatni"


def _parse_homepage(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []
    seen_ids: set[str] = set()

    for table in soup.select("table.tblDrazbaMala"):
        link = table.find("a", class_="linkDrazbaMala")
        if not link:
            continue
        href = link.get("href", "")
        m = re.match(r"/(DR\d+)/", href)
        if not m:
            continue
        native_id = m.group(1)
        if native_id in seen_ids:
            continue
        seen_ids.add(native_id)

        h3 = table.find("h3")
        title = h3.get_text(strip=True) if h3 else ""
        if not title:
            continue

        # "UHRAZENO" prefix means already paid — treat as finished, skip
        if title.upper().startswith("UHRAZENO"):
            continue

        img = table.find("img")
        image = ""
        if img and img.get("src"):
            src = img["src"]
            image = src if src.startswith("http") else f"{BASE}/{src.lstrip('/')}"

        # Start date+time
        start_span = table.find(id="zacatekDrazby")
        start_date, start_time = "", ""
        if start_span:
            start_date, start_time = parse_cz_date(start_span.get_text(strip=True))

        # Min bid: <strong> after "nejnižší podání"
        min_bid_text = ""
        for p in table.find_all("p", class_="pDrazbaMalaDetailPrava"):
            strong = p.find("strong")
            if strong and "Kč" in strong.get_text():
                min_bid_text = strong.get_text(strip=True)
                break

        link_url = f"{BASE}{href}"

        records.append(make_record(
            portal=PORTAL_SLUG,
            portal_label=PORTAL_LABEL,
            native_id=native_id,
            category=_classify(title),
            status="prepared",  # homepage only lists upcoming items
            title=title,
            location="",  # not on homepage card; would need detail page
            min_bid_text=min_bid_text,
            start_date=start_date,
            start_time=start_time,
            image=image,
            link=link_url,
            badges=[],
        ))

    return records


def scrape() -> list[dict]:
    html = fetch(HOMEPAGE)
    if not html:
        return []
    records = _parse_homepage(html)
    print(f"  drazby-exekutori total: {len(records)} (homepage only — pagination TODO)")
    return records
