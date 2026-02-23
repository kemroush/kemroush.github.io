#!/usr/bin/env python3
"""
Auto Monitor - sledování nových SUV s automatem na sauto.cz
Generuje cars.html ve stylu kemroush.github.io

Požadavky:
  pip install beautifulsoup4 lxml
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta

from bs4 import BeautifulSoup, NavigableString

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CONFIG = {
    "max_price_czk": 700_000,
    "seen_file":     os.path.join(DATA_DIR, "seen_cars.json"),
    "output_file":   os.path.join(BASE_DIR, "cars.html"),
}

HEXAGON_BG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='75' height='43.3' "
    "viewBox='0 0 75 43.3'%3E%3Cpath d='M25,0 L50,0 L62.5,21.65 L50,43.3 L25,43.3 L12.5,21.65 Z "
    "M0,21.65 L12.5,21.65 M62.5,21.65 L75,21.65' fill='none' stroke='%23ffffff' "
    "stroke-opacity='0.03' stroke-width='0.5'/%3E%3C/svg%3E"
)

# ─────────────────────────────────────────────
#  POMOCNÉ FUNKCE
# ─────────────────────────────────────────────

def get_day_key() -> str:
    now = datetime.now()
    if now.hour < 6:
        now -= timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def load_seen() -> set:
    if os.path.exists(CONFIG["seen_file"]):
        with open(CONFIG["seen_file"], "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG["seen_file"], "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)


def load_today_cars(path: str) -> list:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_today_cars(path: str, cars: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cars, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
#  SCRAPING SAUTO.CZ
# ─────────────────────────────────────────────

def scrape_sauto() -> list[dict]:
    url = (
        "https://www.sauto.cz/inzerce/osobni"
        f"?cena-do={CONFIG['max_price_czk']}"
        "&stav=ojete&typ=suv&prevodovka=automaticka&razeni=datum-vlozeni-desc"
    )
    cars = []
    try:
        result = subprocess.run(
            ["curl", "-sL",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
             "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
             "-H", "Accept-Language: cs-CZ,cs;q=0.9",
             url],
            capture_output=True, text=True, timeout=30,
        )
        soup = BeautifulSoup(result.stdout, "lxml")

        for item in soup.select("li.c-item.c-item--hor"):
            try:
                ad_id = None
                for cls in item.get("class", []):
                    m = re.match(r"^c-item-(\d+)$", cls)
                    if m:
                        ad_id = m.group(1)
                        break

                name_el   = item.select_one("span.c-item__name")
                suffix_el = item.select_one("span.c-item__name--suffix")
                direct = "".join(str(t).strip() for t in name_el.children
                                 if isinstance(t, NavigableString)).rstrip(",").strip() if name_el else ""
                suffix = suffix_el.get_text(strip=True) if suffix_el else ""
                title  = f"{direct} {suffix}".strip()

                price_el = item.select_one("div.c-item__price")
                price    = price_el.get_text(strip=True) if price_el else "Cena neuvedena"

                info_el   = item.select_one("div.c-item__info")
                info_text = info_el.get_text(" ", strip=True) if info_el else ""

                loc_el   = item.select_one("div.c-item__locality")
                location = loc_el.get_text(strip=True) if loc_el else ""

                details = f"{info_text}  ·  {location}".strip(" ·").strip()

                link_el = item.select_one("a[href]")
                href    = link_el["href"] if link_el else ""
                link    = href if href.startswith("http") else f"https://www.sauto.cz{href}"

                if not ad_id:
                    ad_id = link

                price_num = int(re.sub(r"[^\d]", "", price)) if re.search(r"\d", price) else 0
                if price_num > CONFIG["max_price_czk"]:
                    continue

                if title and link:
                    cars.append({
                        "id":      ad_id,
                        "title":   title,
                        "price":   price,
                        "details": details,
                        "link":    link,
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"  [sauto.cz] Chyba: {e}")

    print(f"  sauto.cz: {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  SESTAVENÍ HTML (styl kemroush)
# ─────────────────────────────────────────────

def build_html(cars: list[dict], day_key: str, updated_at: str) -> str:
    day_dt    = datetime.strptime(day_key, "%Y-%m-%d")
    day_label = f"{day_dt.day}. {day_dt.month}. {day_dt.year}"

    cards = ""
    for c in cars:
        found = c.get("found_at", "")
        cards += f"""
    <a href="{c['link']}" class="car-card" target="_blank" rel="noopener">
      <div class="car-top">
        <span class="car-title">{c['title']}</span>
        <span class="car-price">{c['price']}</span>
      </div>
      <div class="car-details">{c['details']}</div>
      {"<div class='car-time'>nalezeno " + found + "</div>" if found else ""}
    </a>"""

    empty = '<p class="empty">Žádná nová auta za dnešní den.</p>' if not cars else ""

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Auto monitor – {day_label}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'Inter', -apple-system, sans-serif;
      background-color: #0d1117;
      background-image: url("{HEXAGON_BG}");
      background-size: 75px 43.3px;
      color: #e6edf3;
      min-height: 100vh;
      padding: 2.5rem 1.5rem;
    }}
    .page {{
      max-width: 680px;
      margin: 0 auto;
      animation: fadeIn 0.6s ease-out;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    .back {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #8b949e;
      text-decoration: none;
      font-size: 0.82rem;
      margin-bottom: 2rem;
      transition: color 0.2s;
    }}
    .back:hover {{ color: #f0883e; }}
    h1 {{
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 0.5rem;
    }}
    .meta {{
      font-size: 0.8rem;
      color: #8b949e;
      margin-bottom: 0.2rem;
    }}
    .meta strong {{ color: #f0883e; font-weight: 600; }}
    .filter {{
      font-size: 0.78rem;
      color: #484f58;
      margin-bottom: 2rem;
    }}
    .car-card {{
      display: block;
      background: #161b22;
      border-radius: 12px;
      padding: 1rem 1.25rem;
      margin-bottom: 0.6rem;
      text-decoration: none;
      color: inherit;
      transition: background 0.2s, box-shadow 0.2s;
    }}
    .car-card:hover {{
      background: #1f2937;
      box-shadow: 0 0 20px rgba(240, 136, 62, 0.1);
    }}
    .car-top {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 1rem;
      margin-bottom: 0.35rem;
    }}
    .car-title {{
      font-weight: 600;
      color: #f0883e;
      font-size: 0.9rem;
      flex: 1;
    }}
    .car-price {{
      font-weight: 700;
      color: #e6edf3;
      white-space: nowrap;
      font-size: 0.9rem;
    }}
    .car-details {{
      font-size: 0.78rem;
      color: #8b949e;
    }}
    .car-time {{
      font-size: 0.7rem;
      color: #30363d;
      margin-top: 0.3rem;
    }}
    .empty {{
      color: #8b949e;
      font-size: 0.9rem;
      text-align: center;
      padding: 3rem 0;
    }}
  </style>
</head>
<body>
  <div class="page">
    <a href="index.html" class="back">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 12H5M12 5l-7 7 7 7"/>
      </svg>
      kemroush
    </a>

    <h1>Auto monitor</h1>
    <p class="meta">Období: <strong>{day_label}, 06:00</strong> – <strong>{updated_at}</strong> · <strong>{len(cars)}</strong> nových inzerátů</p>
    <p class="filter">SUV · Ojeté · Automat · do {CONFIG['max_price_czk']:,} Kč · sauto.cz</p>

    {cards}
    {empty}
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────
#  HLAVNÍ LOGIKA
# ─────────────────────────────────────────────

def main():
    now_str  = datetime.now().strftime("%d.%m.%Y %H:%M")
    day_key  = get_day_key()

    cars_file = os.path.join(DATA_DIR, f"cars_{day_key}.json")

    print(f"[{now_str}] Den: {day_key} | Spouštím kontrolu...")

    seen       = load_seen()
    today_cars = load_today_cars(cars_file)
    all_cars   = scrape_sauto()

    new_cars = [c for c in all_cars if c["id"] not in seen]
    print(f"  Nových: {len(new_cars)} | Dnes celkem: {len(today_cars)} | Nalezeno: {len(all_cars)}")

    if new_cars:
        for c in new_cars:
            c["found_at"] = now_str
        today_cars.extend(new_cars)
        save_today_cars(cars_file, today_cars)

        html = build_html(today_cars, day_key, now_str)
        with open(CONFIG["output_file"], "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ Uloženo → {CONFIG['output_file']}")

        seen.update(c["id"] for c in new_cars)
        save_seen(seen)
    else:
        print("  Žádná nová auta od posledního spuštění.")


if __name__ == "__main__":
    main()
