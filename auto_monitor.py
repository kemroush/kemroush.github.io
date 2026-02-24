#!/usr/bin/env python3
"""
Auto Monitor - sledování nových BMW a Mercedes na sauto.cz

Generuje:
  data/index.json            – seznam dostupných dní (čte JS v cars.html)
  data/cars_YYYY-MM-DD.json  – inzeráty per den

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
    "min_price_czk": 300_000,
    "max_price_czk": 700_000,
    "max_km":        100_000,
    "min_year":      2022,
    "brands":        ["bmw", "mercedes-benz"],
    "seen_file":     os.path.join(DATA_DIR, "seen_cars.json"),
    "index_file":    os.path.join(DATA_DIR, "index.json"),
}

# ─────────────────────────────────────────────
#  POMOCNÉ FUNKCE
# ─────────────────────────────────────────────

def get_day_key() -> str:
    """Aktuální den, reset v 6:00."""
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


def update_index(day_key: str, count: int, updated_at: str):
    """Udržuje data/index.json – seznam dní s metadaty pro JS navigaci."""
    index_file = CONFIG["index_file"]
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"latest": day_key, "days": []}

    # Najdi nebo vytvoř záznam pro dnešek
    day_entry = next((d for d in index["days"] if d["key"] == day_key), None)
    if day_entry:
        day_entry["count"]   = count
        day_entry["updated"] = updated_at
    else:
        index["days"].insert(0, {"key": day_key, "count": count, "updated": updated_at})
        index["days"].sort(key=lambda d: d["key"], reverse=True)

    index["latest"] = index["days"][0]["key"]

    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
#  SCRAPING SAUTO.CZ
# ─────────────────────────────────────────────

def scrape_sauto(brand: str) -> list[dict]:
    url = (
        f"https://www.sauto.cz/inzerce/osobni/{brand}"
        f"?cena-od={CONFIG['min_price_czk']}"
        f"&cena-do={CONFIG['max_price_czk']}"
        f"&vyrobeno-od={CONFIG['min_year']}"
        f"&km-do={CONFIG['max_km']}"
        f"&prevodovka=automaticka&razeni=datum-vlozeni-desc"
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

                seller_el   = item.select_one("div.c-item__seller")
                seller_text = seller_el.get_text(strip=True) if seller_el else ""
                seller_type = "Soukromý" if seller_text == "Soukromý prodejce" else seller_text

                details = f"{info_text}  ·  {location}  ·  {seller_type}".strip(" ·").strip()

                link_el = item.select_one("a[href]")
                href    = link_el["href"] if link_el else ""
                link    = href if href.startswith("http") else f"https://www.sauto.cz{href}"

                if not ad_id:
                    ad_id = link

                # Záložní filtr: značka (pro případ sponzorovaných výsledků jiných značek)
                title_lower = title.lower()
                brand_prefixes = ["bmw", "mercedes"]
                if not any(title_lower.startswith(b) for b in brand_prefixes):
                    continue

                # Filtr: rok
                year_m = re.search(r'\b(20\d{2})\b', info_text)
                if year_m and int(year_m.group(1)) < CONFIG["min_year"]:
                    continue

                # Filtr: km
                km_m = re.search(r'([\d\s\u00a0]+)\s*km', info_text)
                if km_m:
                    km = int(re.sub(r'\D', '', km_m.group(1)))
                    if km > CONFIG["max_km"]:
                        continue

                # Filtr: cena
                price_num = int(re.sub(r"[^\d]", "", price)) if re.search(r"\d", price) else 0
                if price_num > CONFIG["max_price_czk"] or (price_num > 0 and price_num < CONFIG["min_price_czk"]):
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
        print(f"  [sauto.cz/{brand}] Chyba: {e}")

    print(f"  sauto.cz/{brand}: {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  HLAVNÍ LOGIKA
# ─────────────────────────────────────────────

def main():
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    day_key = get_day_key()

    cars_file = os.path.join(DATA_DIR, f"cars_{day_key}.json")

    print(f"[{now_str}] Den: {day_key} | Spouštím kontrolu...")

    seen       = load_seen()
    today_cars = load_today_cars(cars_file)
    all_cars = []
    for brand in CONFIG["brands"]:
        all_cars += scrape_sauto(brand)

    new_cars = [c for c in all_cars if c["id"] not in seen]
    print(f"  Nových: {len(new_cars)} | Dnes celkem: {len(today_cars)} | Nalezeno: {len(all_cars)}")

    if new_cars:
        for c in new_cars:
            c["found_at"] = now_str
        today_cars.extend(new_cars)
        save_today_cars(cars_file, today_cars)
        update_index(day_key, len(today_cars), now_str)

        seen.update(c["id"] for c in new_cars)
        save_seen(seen)

        print(f"✅ Uloženo → data/cars_{day_key}.json ({len(today_cars)} aut dnes)")
    else:
        print("  Žádná nová auta od posledního spuštění.")


if __name__ == "__main__":
    main()
