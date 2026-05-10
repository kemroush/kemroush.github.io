"""Shared helpers for auction portal scrapers."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

RECORD_FIELDS = [
    "id", "portal", "portal_label", "category", "status",
    "title", "location", "min_bid_czk", "min_bid_text",
    "start_date", "start_time", "image", "link", "badges",
]

CZ_MONTHS = {
    "ledna": 1, "února": 2, "března": 3, "dubna": 4,
    "května": 5, "června": 6, "července": 7, "srpna": 8,
    "září": 9, "října": 10, "listopadu": 11, "prosince": 12,
    "leden": 1, "únor": 2, "březen": 3, "duben": 4,
    "květen": 5, "červen": 6, "červenec": 7, "srpen": 8,
    "říjen": 10, "listopad": 11, "prosinec": 12,
}


def fetch(url: str, timeout: int = 30) -> str:
    """Fetch URL via curl with gzip support. Returns body text or empty string on failure."""
    try:
        result = subprocess.run(
            [
                "curl", "-sL", "--compressed",
                "-H", f"User-Agent: {USER_AGENT}",
                "-H", "Accept: text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "-H", "Accept-Language: cs-CZ,cs;q=0.9,en;q=0.8",
                url,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout or ""
    except Exception as e:
        print(f"    curl failed for {url}: {e}")
        return ""


def parse_czk(text: str) -> int:
    """Extract a Kč amount from a string. Returns 0 if not found."""
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def parse_cz_date(text: str) -> tuple[str, str]:
    """Parse Czech-formatted date+time. Returns (YYYY-MM-DD, HH:MM) or ("", "")."""
    if not text:
        return "", ""
    text = text.strip()

    # "13. 5. 2026 8:00" or "13.5.2026 08:00"
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m:
        d, mo, y, hh, mm = m.groups()
        date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        time = f"{int(hh):02d}:{int(mm):02d}" if hh else ""
        return date, time

    # "13. května 2026 8:00"
    m = re.search(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m:
        d, month_name, y, hh, mm = m.groups()
        mo = CZ_MONTHS.get(month_name.lower())
        if mo:
            date = f"{int(y):04d}-{mo:02d}-{int(d):02d}"
            time = f"{int(hh):02d}:{int(mm):02d}" if hh else ""
            return date, time

    return "", ""


def make_record(
    *,
    portal: str,
    portal_label: str,
    native_id: str,
    category: str,
    status: str,
    title: str,
    location: str = "",
    min_bid_text: str = "",
    start_date: str = "",
    start_time: str = "",
    image: str = "",
    link: str = "",
    badges: list[str] | None = None,
) -> dict:
    """Build a standardized auction record."""
    return {
        "id": f"{portal}:{native_id}",
        "portal": portal,
        "portal_label": portal_label,
        "category": category,
        "status": status,
        "title": title.strip(),
        "location": location.strip(),
        "min_bid_czk": parse_czk(min_bid_text),
        "min_bid_text": min_bid_text.strip(),
        "start_date": start_date,
        "start_time": start_time,
        "image": image,
        "link": link,
        "badges": badges or [],
    }


def class_starts_with(prefix: str):
    """BeautifulSoup CSS-like matcher for hashed Next.js classes (prefix match)."""
    return {"class": lambda v: bool(v) and any(c.startswith(prefix) for c in (v if isinstance(v, list) else v.split()))}
