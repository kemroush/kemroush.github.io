#!/usr/bin/env python3
"""
Auto Monitor - sledování nových BMW a Mercedes na sauto.cz,
renocar.cz, mercedesnasklade.cz, future.drivalia.cz a nabidky.bmw.cz

Generuje:
  data/index.json            – seznam dostupných dní (čte JS v cars.html)
  data/cars_YYYY-MM-DD.json  – inzeráty per den (nová + zlevněná auta)
  data/tracked.json          – id → {price, last_seen} (hlídání zlevnění, úklid, stav "v nabídce")

Druhý, oddělený feed – dodávky (užitková na sauto.cz, VAN_CONFIG):
  data/vans_index.json, data/vans_YYYY-MM-DD.json, data/vans_seen.json, data/vans_tracked.json

Třetí, oddělený feed – Ari car store (malá auta s automatem na sauto.cz, ARI_CONFIG):
  data/ari_index.json, data/ari_YYYY-MM-DD.json, data/ari_seen.json, data/ari_tracked.json

Požadavky:
  pip install beautifulsoup4 lxml
"""

import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timedelta

from bs4 import BeautifulSoup, NavigableString

RENOCAR_BASE = "https://www.renocar.cz"
MNS_BASE = "https://www.mercedesnasklade.cz"
DRIVALIA_BASE = "https://future.drivalia.cz"
BMWOJETE_BASE = "https://nabidky.bmw.cz"
# Podepsaný (šířka/hash) prefix pro náhledové obrázky – konstanta ze šablony webu.
BMWOJETE_IMG_PREFIX = f"{BMWOJETE_BASE}/ojete/api/v1/ems/bmw-used-cs_CZ/vehicle/704/3badee93bb5066d1f934a160e74bf8ec"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CONFIG = {
    "min_price_czk": 300_000,
    "max_price_czk": 750_000,
    "max_km":        100_000,
    "min_year":      2020,
    "min_year_overrides": {"bmw": 2022},
    "brands":        ["bmw", "mercedes-benz", "mini"],
    "blocked_sellers": ["davo car", "aaa auto", "auta super"],
    "max_pages":       5,
    "seen_file":     os.path.join(DATA_DIR, "seen_cars.json"),
    "index_file":    os.path.join(DATA_DIR, "index.json"),
    "tracked_file":  os.path.join(DATA_DIR, "tracked.json"),
    "keep_days":     60,   # denní soubory cars_*.json starší než tohle se mažou
    "forget_days":   30,   # auto nevidané tak dlouho se zapomene (seen + tracked)
}

# Dodávky – samostatný feed se samostatnými soubory (nemíchá se s auty).
VAN_CONFIG = {
    "min_price_czk": 40_000,    # pod tím bývají vraky / na díly
    "max_price_czk": 150_000,
    "max_km":        300_000,
    "min_km":        1_000,     # nesmyslné / nevyplněné tachometry
    "min_year":      2008,
    "max_pages":     20,        # × 100 inzerátů z API
    # Jen střední a velké dodávky (manufacturer_seo/model_seo ze sauto API).
    # Malé (Caddy, Kangoo, Berlingo, Praktik…) a pick-upy se přeskakují.
    "models": {
        "ford/transit", "ford/transit-custom", "ford/tourneo-custom",
        "volkswagen/transporter", "volkswagen/multivan", "volkswagen/caravelle",
        "volkswagen/crafter", "volkswagen/lt",
        "mercedes-benz/vito", "mercedes-benz/viano", "mercedes-benz/sprinter",
        "renault/master", "renault/trafic",
        "opel/movano", "opel/vivaro",
        "fiat/ducato", "fiat/scudo", "fiat/talento",
        "peugeot/boxer", "peugeot/expert",
        "citroen/jumper", "citroen/jumpy",
        "toyota/proace",
        "iveco/daily",
        "nissan/primastar", "nissan/interstar", "nissan/nv300", "nissan/nv400",
        "hyundai/h-1",
    },
    "seen_file":     os.path.join(DATA_DIR, "vans_seen.json"),
    "index_file":    os.path.join(DATA_DIR, "vans_index.json"),
    "tracked_file":  os.path.join(DATA_DIR, "vans_tracked.json"),
    "file_prefix":   "vans_",
}

# Ari car store – malá auta s automatem pro Ari, samostatný feed (ari_*).
ARI_CONFIG = {
    "min_price_czk": 100_000,   # pod tím bývají vraky / na díly
    "max_price_czk": 400_000,
    "max_km":        250_000,   # nájezd moc nevadí, jen pojistka proti extrémům
    "min_km":        1_000,     # nesmyslné / nevyplněné tachometry
    "min_year":      2014,
    "max_pages":     30,        # × 100 inzerátů z API (~12 stránek v 10/2026)
    # manufacturer_seo → model_seo ze sauto API. Pozor: neznámé model_seo API
    # tiše ignoruje a vrátí celou značku → whitelist se proto kontroluje i klientsky.
    "models": {
        "toyota":        ["yaris", "yaris-cross", "aygo", "auris", "corolla", "c-hr"],
        "audi":          ["a1", "a3"],
        "mercedes-benz": ["tridy-a", "cla"],
        "bmw":           ["rada-1", "rada-2"],
        "volkswagen":    ["polo", "golf"],
        "skoda":         ["fabia", "scala"],
        "seat":          ["ibiza", "leon"],
        "cupra":         ["leon", "born"],
        "peugeot":       ["208", "2008"],
        "mazda":         ["2", "2-hybrid", "3"],
        "lexus":         ["ct-200h", "ux-200", "ux-250h", "ux-300e"],
        "ds":            ["3", "3-crossback"],
        "hyundai":       ["i20"],
        "kia":           ["rio", "stonic"],
    },
    "blocked_manufacturers": {"mini"},   # Mini Ari nechce
    "seen_file":     os.path.join(DATA_DIR, "ari_seen.json"),
    "index_file":    os.path.join(DATA_DIR, "ari_index.json"),
    "tracked_file":  os.path.join(DATA_DIR, "ari_tracked.json"),
    "file_prefix":   "ari_",
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


def load_seen(path: str = CONFIG["seen_file"]) -> set:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set, path: str = CONFIG["seen_file"]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)


def load_tracked(path: str = CONFIG["tracked_file"]) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tracked(tracked: dict, path: str = CONFIG["tracked_file"]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tracked, f, ensure_ascii=False, indent=1, sort_keys=True)


def forget_stale(seen: set, tracked: dict, day_key: str) -> int:
    """Zapomene auta nevidaná déle než forget_days (ze seen i tracked).
    ID ze seen bez záznamu v tracked (starší než tracked.json) dostanou
    last_seen = dnes, takže se mažou až po celé lhůtě – kdyby scraper
    zrovna selhal, auto se nevrátí jako „nové“."""
    for car_id in seen:
        tracked.setdefault(car_id, {"price": 0, "last_seen": day_key})
    cutoff = (datetime.strptime(day_key, "%Y-%m-%d")
              - timedelta(days=CONFIG["forget_days"])).strftime("%Y-%m-%d")
    stale = [i for i, t in tracked.items() if t["last_seen"] < cutoff]
    for car_id in stale:
        del tracked[car_id]
        seen.discard(car_id)
    return len(stale)


def prune_old_days(day_key: str, prefix: str = "cars_",
                   index_file: str = CONFIG["index_file"]) -> int:
    """Smaže <prefix>YYYY-MM-DD.json starší než keep_days a vyřadí je z indexu."""
    cutoff = (datetime.strptime(day_key, "%Y-%m-%d")
              - timedelta(days=CONFIG["keep_days"])).strftime("%Y-%m-%d")
    removed = 0
    for name in os.listdir(DATA_DIR):
        m = re.fullmatch(re.escape(prefix) + r"(\d{4}-\d{2}-\d{2})\.json", name)
        if m and m.group(1) < cutoff:
            os.remove(os.path.join(DATA_DIR, name))
            removed += 1

    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)
        kept = [d for d in index["days"] if d["key"] >= cutoff]
        if len(kept) != len(index["days"]):
            index["days"] = kept
            if kept:
                index["latest"] = kept[0]["key"]
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
    return removed


def parse_price(price: str) -> int:
    digits = re.sub(r"\D", "", price or "")
    return int(digits) if digits else 0


def load_today_cars(path: str) -> list:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_today_cars(path: str, cars: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cars, f, ensure_ascii=False, indent=2)


def update_index(day_key: str, count: int, updated_at: str,
                 index_file: str = CONFIG["index_file"]):
    """Udržuje data/index.json – seznam dní s metadaty pro JS navigaci."""
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
    min_year = CONFIG["min_year_overrides"].get(brand, CONFIG["min_year"])
    base_url = (
        f"https://www.sauto.cz/inzerce/osobni/{brand}"
        f"?cena-od={CONFIG['min_price_czk']}"
        f"&cena-do={CONFIG['max_price_czk']}"
        f"&vyrobeno-od={min_year}"
        f"&km-do={CONFIG['max_km']}"
        f"&prevodovka=automaticka&razeni=datum-vlozeni-desc"
    )
    cars = []
    try:
        for page in range(1, CONFIG["max_pages"] + 1):
            url = base_url if page == 1 else f"{base_url}&strana={page}"
            result = subprocess.run(
                ["curl", "-sL",
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                 "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                 "-H", "Accept-Language: cs-CZ,cs;q=0.9",
                 url],
                capture_output=True, text=True, timeout=30,
            )
            soup = BeautifulSoup(result.stdout, "lxml")
            items = soup.select("li.c-item.c-item--hor")
            if not items:
                break  # žádné další výsledky

            for item in items:
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

                    img_el = item.select_one("img.c-item__image")
                    img_src = img_el["src"] if img_el else ""
                    if img_src.startswith("//"):
                        img_src = "https:" + img_src

                    if not ad_id:
                        ad_id = link

                    # Filtr: blokovaní prodejci
                    seller_lower = seller_text.lower()
                    if any(b in seller_lower for b in CONFIG["blocked_sellers"]):
                        continue

                    # Záložní filtr: značka (pro případ sponzorovaných výsledků jiných značek)
                    title_lower = title.lower()
                    brand_prefixes = ["bmw", "mercedes", "mini"]
                    if not any(title_lower.startswith(b) for b in brand_prefixes):
                        continue

                    # Filtr: rok (BMW má vyšší min_year přes min_year_overrides)
                    year_m = re.search(r'\b(20\d{2})\b', info_text)
                    if year_m and int(year_m.group(1)) < min_year:
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
                            "image":   img_src,
                        })
                except Exception:
                    continue

    except Exception as e:
        print(f"  [sauto.cz/{brand}] Chyba: {e}")

    print(f"  sauto.cz/{brand}: {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  SCRAPING RENOCAR.CZ (BMW skladové vozy)
# ─────────────────────────────────────────────

def _format_czk(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " Kč"


def scrape_renocar() -> list[dict]:
    brand = "bmw"
    min_year = CONFIG["min_year_overrides"].get(brand, CONFIG["min_year"])
    url = f"{RENOCAR_BASE}/?ajax=newFilterQuery-cars&brand={brand}&limit=500&offset=0"
    cars = []
    try:
        result = subprocess.run(
            ["curl", "-sL",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
             "-H", "Accept: application/json, text/plain, */*",
             "-H", "X-Requested-With: XMLHttpRequest",
             "-H", "Accept-Language: cs-CZ,cs;q=0.9",
             url],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        for c in data.get("cars", []):
            try:
                ad_id = f"renocar:{c['id']}"

                title = c.get("name", "").strip()
                if not title.lower().startswith("bmw"):
                    continue

                price_net = float(c.get("price") or 0)
                vat_rate = float(c.get("vat") or 21)
                price_num = round(price_net * (1 + vat_rate / 100))
                if price_num <= 0:
                    continue
                if price_num > CONFIG["max_price_czk"] or price_num < CONFIG["min_price_czk"]:
                    continue

                km = int(c.get("tachometer_state") or 0)
                if km > CONFIG["max_km"]:
                    continue

                year = 0
                reg = c.get("date_of_first_registration") or ""
                year_m = re.match(r"(\d{4})", reg)
                if year_m:
                    year = int(year_m.group(1))
                if year and year < min_year:
                    continue

                body = (c.get("body_name") or "").strip()
                displacement = (c.get("displacement") or "").strip()
                parts = []
                if body:
                    parts.append(body)
                if year:
                    parts.append(str(year))
                parts.append(f"{km:,}".replace(",", " ") + " km")
                if displacement:
                    parts.append(displacement)
                parts.append("Renocar")
                details = "  ·  ".join(parts)

                slug = c.get("url") or ""
                link = f"{RENOCAR_BASE}/vuz/{slug}-{c['id']}"

                image = ""
                raw_img = c.get("image")
                if raw_img:
                    try:
                        img_obj = json.loads(raw_img) if isinstance(raw_img, str) else raw_img
                        img_src = (img_obj or {}).get("src", "")
                        if img_src:
                            image = f"{RENOCAR_BASE}/{img_src.lstrip('/')}"
                    except Exception:
                        pass

                cars.append({
                    "id":      ad_id,
                    "title":   title,
                    "price":   _format_czk(price_num),
                    "details": details,
                    "link":    link,
                    "image":   image,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"  [renocar.cz] Chyba: {e}")

    print(f"  renocar.cz/{brand}: {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  SCRAPING NABIDKY.BMW.CZ (oficiální ojeté BMW + MINI)
# ─────────────────────────────────────────────

def scrape_bmwojete() -> list[dict]:
    """Oficiální burza ojetých vozů BMW/MINI. JSON API řadí podle ceny
    vzestupně, takže po překročení max_price se dá skončit. Parametr
    ``$offset`` API ignoruje, proto se stránkuje jedním velkým ``$limit``."""
    url = f"{BMWOJETE_BASE}/ojete/api/v1/ems/bmw-used-cs_CZ/search"
    cars = []
    try:
        body = json.dumps({
            "$offset": 0,
            "$limit":  500,
            "$sort":   [{"$field": "transactionalPrice", "$order": "asc"}],
        })
        result = subprocess.run(
            ["curl", "-sL", "-X", "POST", url,
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
             "-H", "Content-Type: application/json;charset=UTF-8",
             "-H", "Accept: application/json",
             "-H", "Accept-Language: cs-CZ,cs;q=0.9",
             "--data", body],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        items = data.get("$list", [])

        for v in items:
            try:
                price_num = int(v.get("transactionalPrice") or 0)
                # Řazeno vzestupně: jakmile cena přeteče max, končíme úplně.
                if price_num > CONFIG["max_price_czk"]:
                    break
                if price_num < CONFIG["min_price_czk"]:
                    continue

                title = (v.get("title") or "").strip()
                title_lower = title.lower()
                # Web míchá BMW i MINI; jinou značku (kdyby přišla) přeskoč.
                if title_lower.startswith("bmw"):
                    brand = "bmw"
                elif title_lower.startswith("mini"):
                    brand = "mini"
                else:
                    continue
                min_year = CONFIG["min_year_overrides"].get(brand, CONFIG["min_year"])

                km = int(v.get("mileage") or 0)
                if km > CONFIG["max_km"]:
                    continue

                year = int(v.get("productionYear") or 0)
                if year and year < min_year:
                    continue

                dealer = ((v.get("dealer") or {}).get("name") or "").strip()
                if any(b in dealer.lower() for b in CONFIG["blocked_sellers"]):
                    continue

                fuel = ((v.get("fuel") or {}).get("label") or "").strip()

                parts = []
                if year:
                    parts.append(str(year))
                parts.append(f"{km:,}".replace(",", " ") + " km")
                if fuel:
                    parts.append(fuel)
                if dealer:
                    parts.append(dealer)
                details = "  ·  ".join(parts)

                vid = v.get("id")
                link = f"{BMWOJETE_BASE}/ojete/hledat/detaily/{vid}/"

                image = ""
                if (v.get("images") or 0) > 0:
                    stamp = v.get("imagesLastChanged") or ""
                    image = f"{BMWOJETE_IMG_PREFIX}/{vid}?{stamp}"

                cars.append({
                    "id":      f"bmwojete:{vid}",
                    "title":   title,
                    "price":   _format_czk(price_num),
                    "details": details,
                    "link":    link,
                    "image":   image,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"  [nabidky.bmw.cz] Chyba: {e}")

    print(f"  nabidky.bmw.cz: {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  SCRAPING MERCEDESNASKLADE.CZ
# ─────────────────────────────────────────────

def scrape_mercedesnasklade() -> list[dict]:
    base = (
        f"{MNS_BASE}/?sp-min={CONFIG['min_price_czk']}"
        f"&sp-max={CONFIG['max_price_czk']}"
        f"&km-max={CONFIG['max_km']}"
        f"&cy-min={CONFIG['min_year']}"
    )
    cars = []
    try:
        for page in range(1, 21):
            url = base if page == 1 else f"{base}&p={page}"
            result = subprocess.run(
                ["curl", "-sL",
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                 "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                 "-H", "Accept-Language: cs-CZ,cs;q=0.9",
                 url],
                capture_output=True, text=True, timeout=30,
            )
            soup = BeautifulSoup(result.stdout, "lxml")
            items = soup.select(".car-item")
            if not items:
                break

            for item in items:
                try:
                    link_el = item.select_one("a[href^='/detail/']")
                    if not link_el:
                        continue
                    href = link_el.get("href", "")
                    m = re.match(r"^/detail/(\d+)", href)
                    if not m:
                        continue
                    detail_id = m.group(1)
                    ad_id = f"mns:{detail_id}"
                    link = f"{MNS_BASE}{href}"

                    type_el = item.select_one(".car-type h3")
                    car_type = type_el.get_text(strip=True) if type_el else ""
                    title = f"Mercedes-Benz {car_type}".strip()

                    price_el = item.select_one(".price.dph b") or item.select_one(".price.dph")
                    price = price_el.get_text(strip=True) if price_el else ""
                    if not price:
                        continue
                    price_num = int(re.sub(r"\D", "", price)) if re.search(r"\d", price) else 0
                    if price_num <= 0:
                        continue
                    if price_num > CONFIG["max_price_czk"] or price_num < CONFIG["min_price_czk"]:
                        continue

                    km = 0
                    km_m = re.search(r"([\d\s ]+)\s*km", item.get_text(" ", strip=True))
                    if km_m:
                        km = int(re.sub(r"\D", "", km_m.group(1)))
                        if km > CONFIG["max_km"]:
                            continue

                    year = 0
                    reg_year_m = re.search(r"\b(20\d{2})\b", item.get_text(" ", strip=True))
                    if reg_year_m:
                        year = int(reg_year_m.group(1))
                        if year < CONFIG["min_year"]:
                            continue

                    fuel = ""
                    for col in item.select(".car-info .column"):
                        desc = col.select_one(".desc")
                        if desc and desc.get_text(strip=True) == "Palivo":
                            val = col.select_one("span:not(.desc)")
                            if val:
                                fuel = val.get_text(strip=True)
                            break

                    seller_el = item.select_one(".prodejce strong")
                    seller = seller_el.get_text(strip=True) if seller_el else ""

                    parts = []
                    if car_type:
                        parts.append(car_type)
                    if year:
                        parts.append(str(year))
                    if km:
                        parts.append(f"{km:,}".replace(",", " ") + " km")
                    if fuel:
                        parts.append(fuel)
                    if seller:
                        parts.append(seller)
                    details = "  ·  ".join(parts)

                    img_el = item.select_one(".car-img img")
                    image = img_el.get("src", "") if img_el else ""
                    if image.startswith("/"):
                        image = f"{MNS_BASE}{image}"

                    if title and link:
                        cars.append({
                            "id":      ad_id,
                            "title":   title,
                            "price":   price,
                            "details": details,
                            "link":    link,
                            "image":   image,
                        })
                except Exception:
                    continue
    except Exception as e:
        print(f"  [mercedesnasklade.cz] Chyba: {e}")

    print(f"  mercedesnasklade.cz: {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  SCRAPING FUTURE.DRIVALIA.CZ
# ─────────────────────────────────────────────

# Mapování interních značek CONFIG na slugy v Drivalia API.
# Mercedes-Benz v Drivalia nemají, takže ho přeskočíme.
DRIVALIA_BRAND_SLUGS = {
    "bmw":           "bmw",
    "mini":          "mini",
}


def _drivalia_nonce() -> str:
    result = subprocess.run(
        ["curl", "-sL",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
         f"{DRIVALIA_BASE}/vozidla/"],
        capture_output=True, text=True, timeout=30,
    )
    m = re.search(r'"action":"ddf_query","nonce":"([a-f0-9]+)"', result.stdout)
    return m.group(1) if m else ""


def _drivalia_fetch_page(brand_slug: str, page: int, nonce: str, min_year: int) -> dict:
    args = [
        "curl", "-sL", "-X", "POST",
        f"{DRIVALIA_BASE}/wp-admin/admin-ajax.php",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "-H", "X-Requested-With: XMLHttpRequest",
        "-H", "Accept: application/json, text/javascript, */*; q=0.01",
        "--data-urlencode", "action=ddf_query",
        "--data-urlencode", f"nonce={nonce}",
        "--data-urlencode", f"page={page}",
        "--data-urlencode", "sort=date-desc",
        "--data-urlencode", f"price_min={CONFIG['min_price_czk']}",
        "--data-urlencode", f"price_max={CONFIG['max_price_czk']}",
        "--data-urlencode", f"km_max={CONFIG['max_km']}",
        "--data-urlencode", f"year_min={min_year}",
        "--data-urlencode", f"brand[]={brand_slug}",
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout)


def scrape_drivalia() -> list[dict]:
    nonce = _drivalia_nonce()
    if not nonce:
        print("  [future.drivalia.cz] Nepodařilo se získat nonce")
        return []

    cars = []
    for brand, brand_slug in DRIVALIA_BRAND_SLUGS.items():
        min_year = CONFIG["min_year_overrides"].get(brand, CONFIG["min_year"])
        brand_count = 0
        try:
            for page in range(1, CONFIG["max_pages"] + 1):
                resp = _drivalia_fetch_page(brand_slug, page, nonce, min_year)
                if not resp.get("success"):
                    break
                data = resp.get("data", {})
                products = data.get("product_data") or []
                if not products:
                    break

                # Z HTML karet vytáhneme obrázky a spárujeme se slug ID
                images = {}
                cards_html = data.get("cards") or ""
                if cards_html:
                    soup = BeautifulSoup(cards_html, "lxml")
                    for card in soup.select("div.car"):
                        link_el = card.select_one("a[href*='/vozidla/']")
                        img_el = card.select_one("img")
                        if link_el and img_el:
                            href = link_el.get("href", "")
                            slug_m = re.search(r"/vozidla/([^/]+)/", href)
                            if slug_m:
                                images[slug_m.group(1)] = img_el.get("src", "")

                for p in products:
                    try:
                        slug = p.get("id") or ""
                        if not slug:
                            continue
                        pid_m = re.match(r"(\d+)", slug)
                        ad_id = f"drivalia:{pid_m.group(1)}" if pid_m else f"drivalia:{slug}"

                        brand_name = (p.get("brand") or "").strip()
                        name = (p.get("name") or "").strip()
                        title = name if name.lower().startswith(brand_name.lower()) else f"{brand_name} {name}".strip()

                        price_num = int(round(float(p.get("price") or 0)))
                        if price_num <= 0:
                            continue
                        if price_num > CONFIG["max_price_czk"] or price_num < CONFIG["min_price_czk"]:
                            continue

                        km_raw = p.get("dimension5") or 0
                        km = int(float(km_raw)) if km_raw else 0
                        if km > CONFIG["max_km"]:
                            continue

                        reg = p.get("dimension56") or ""
                        year_m = re.match(r"(\d{4})", reg)
                        year = int(year_m.group(1)) if year_m else 0
                        if year and year < min_year:
                            continue

                        body = (p.get("dimension1") or "").strip()
                        fuel = (p.get("dimension2") or "").strip()
                        variant = (p.get("variant") or "").strip()

                        parts = []
                        if variant:
                            parts.append(variant)
                        if body:
                            parts.append(body)
                        if year:
                            parts.append(str(year))
                        if km:
                            parts.append(f"{km:,}".replace(",", " ") + " km")
                        if fuel:
                            parts.append(fuel)
                        parts.append("Future Drivalia")
                        details = "  ·  ".join(parts)

                        link = f"{DRIVALIA_BASE}/vozidla/{slug}/"
                        image = images.get(slug, "")

                        cars.append({
                            "id":      ad_id,
                            "title":   title,
                            "price":   _format_czk(price_num),
                            "details": details,
                            "link":    link,
                            "image":   image,
                        })
                        brand_count += 1
                    except Exception:
                        continue

                if not data.get("hasMore"):
                    break
        except Exception as e:
            print(f"  [future.drivalia.cz/{brand_slug}] Chyba: {e}")

        print(f"  future.drivalia.cz/{brand_slug}: {brand_count} inzerátů")

    return cars


# ─────────────────────────────────────────────
#  SCRAPING SAUTO.CZ – DODÁVKY (užitková, JSON API)
# ─────────────────────────────────────────────

SAUTO_IMG_SUFFIX = "?fl=exf|res,360,270,3|jpg,80,,1"


def scrape_sauto_vans() -> list[dict]:
    """Užitková vozidla ze sauto.cz přes interní JSON API (category_id=839).
    Cenový filtr jde server-side, zbytek (model, rok, km) klientsky."""
    vc = VAN_CONFIG
    base = (
        "https://www.sauto.cz/api/v1/items/search"
        f"?price_from={vc['min_price_czk']}&price_to={vc['max_price_czk']}"
        "&condition_seo=ojete&category_id=839&operating_lease=false&limit=100"
    )
    vans = []
    try:
        for page in range(vc["max_pages"]):
            result = subprocess.run(
                ["curl", "-sL",
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                 "-H", "Accept: application/json, text/plain, */*",
                 "-H", "Accept-Language: cs-CZ,cs;q=0.9",
                 "-H", "Referer: https://www.sauto.cz/inzerce/uzitkova",
                 f"{base}&offset={page * 100}"],
                capture_output=True, text=True, timeout=30,
            )
            items = json.loads(result.stdout).get("results") or []

            for v in items:
                try:
                    man = v.get("manufacturer_cb") or {}
                    model = v.get("model_cb") or {}
                    key = f"{man.get('seo_name', '')}/{model.get('seo_name', '')}"
                    if key not in vc["models"]:
                        continue

                    price_num = int(v.get("price") or 0)
                    if v.get("price_by_agreement") or price_num <= 0:
                        continue
                    if price_num < vc["min_price_czk"] or price_num > vc["max_price_czk"]:
                        continue

                    km = int(v.get("tachometer") or 0)
                    if km < vc["min_km"] or km > vc["max_km"]:
                        continue

                    year_m = re.match(r"(\d{4})", v.get("manufacturing_date")
                                      or v.get("in_operation_date") or "")
                    year = int(year_m.group(1)) if year_m else 0
                    if not year or year < vc["min_year"]:
                        continue

                    premise = (v.get("premise") or {}).get("name") or ""
                    if any(b in premise.lower() for b in CONFIG["blocked_sellers"]):
                        continue
                    seller = premise.strip() or "Soukromý"

                    # „Opel Vivaro, 1,9 CDTI“ → „Opel Vivaro 1,9 CDTI“ (jen první čárka)
                    title = re.sub(r"\s*,\s*", " ", (v.get("name") or "").strip(), count=1).strip()
                    if not title:
                        title = f"{man.get('name', '')} {model.get('name', '')}".strip()

                    fuel = ((v.get("fuel_cb") or {}).get("name") or "").strip()
                    gearbox = ((v.get("gearbox_cb") or {}).get("name") or "").strip()
                    loc = v.get("locality") or {}
                    place = (loc.get("district") or loc.get("municipality") or "").strip()

                    parts = [str(year), f"{km:,}".replace(",", " ") + " km"]
                    parts += [x for x in (fuel, gearbox, place, seller) if x]
                    details = "  ·  ".join(parts)

                    vid = v.get("id")
                    link = (f"https://www.sauto.cz/uzitkova/detail/"
                            f"{man.get('seo_name', '')}/{model.get('seo_name', '')}/{vid}")

                    image = ""
                    imgs = v.get("images") or []
                    if imgs and imgs[0].get("url"):
                        image = imgs[0]["url"]
                        if image.startswith("//"):
                            image = "https:" + image
                        image += SAUTO_IMG_SUFFIX

                    vans.append({
                        "id":      str(vid),
                        "title":   title,
                        "price":   _format_czk(price_num),
                        "details": details,
                        "link":    link,
                        "image":   image,
                    })
                except Exception:
                    continue

            if len(items) < 100:
                break
    except Exception as e:
        print(f"  [sauto.cz/uzitkova] Chyba: {e}")

    print(f"  sauto.cz/uzitkova (dodávky): {len(vans)} inzerátů")
    return vans


# ─────────────────────────────────────────────
#  SCRAPING SAUTO.CZ – ARI CAR STORE (malá auta s automatem, JSON API)
# ─────────────────────────────────────────────

def scrape_sauto_ari() -> list[dict]:
    """Malá ojetá auta s automatem ze sauto.cz přes interní JSON API
    (category_id=838 = osobní). Cena, převodovka, km a whitelist modelů
    jdou server-side (manufacturer_model_seo=znacka:m1,m2|znacka2:m3),
    rok + kontrola whitelistu klientsky."""
    ac = ARI_CONFIG
    mm = "|".join(f"{man}:{','.join(models)}" for man, models in ac["models"].items())
    base = (
        "https://www.sauto.cz/api/v1/items/search"
        f"?price_from={ac['min_price_czk']}&price_to={ac['max_price_czk']}"
        f"&tachometer_to={ac['max_km']}"
        "&condition_seo=ojete&category_id=838&gearbox_seo=automaticka"
        "&operating_lease=false&limit=100"
        f"&manufacturer_model_seo={urllib.parse.quote(mm, safe='')}"
    )
    cars = []
    try:
        for page in range(ac["max_pages"]):
            result = subprocess.run(
                ["curl", "-sL",
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                 "-H", "Accept: application/json, text/plain, */*",
                 "-H", "Accept-Language: cs-CZ,cs;q=0.9",
                 "-H", "Referer: https://www.sauto.cz/inzerce/osobni",
                 f"{base}&offset={page * 100}"],
                capture_output=True, text=True, timeout=30,
            )
            items = json.loads(result.stdout).get("results") or []

            for v in items:
                try:
                    man = v.get("manufacturer_cb") or {}
                    model = v.get("model_cb") or {}
                    man_seo = man.get("seo_name", "")
                    model_seo = model.get("seo_name", "")
                    if man_seo in ac["blocked_manufacturers"]:
                        continue
                    if model_seo not in ac["models"].get(man_seo, []):
                        continue

                    gearbox_cb = v.get("gearbox_cb") or {}
                    if gearbox_cb.get("seo_name") != "automaticka":
                        continue

                    price_num = int(v.get("price") or 0)
                    if v.get("price_by_agreement") or price_num <= 0:
                        continue
                    if price_num < ac["min_price_czk"] or price_num > ac["max_price_czk"]:
                        continue

                    km = int(v.get("tachometer") or 0)
                    if km < ac["min_km"] or km > ac["max_km"]:
                        continue

                    year_m = re.match(r"(\d{4})", v.get("manufacturing_date")
                                      or v.get("in_operation_date") or "")
                    year = int(year_m.group(1)) if year_m else 0
                    if not year or year < ac["min_year"]:
                        continue

                    premise = (v.get("premise") or {}).get("name") or ""
                    if any(b in premise.lower() for b in CONFIG["blocked_sellers"]):
                        continue
                    seller = premise.strip() or "Soukromý"

                    # „Toyota Yaris, 1.5 Hybrid“ → „Toyota Yaris 1.5 Hybrid“ (jen první čárka)
                    title = re.sub(r"\s*,\s*", " ", (v.get("name") or "").strip(), count=1).strip()
                    if not title:
                        title = f"{man.get('name', '')} {model.get('name', '')}".strip()

                    fuel = ((v.get("fuel_cb") or {}).get("name") or "").strip()
                    gearbox = (gearbox_cb.get("name") or "").strip()
                    loc = v.get("locality") or {}
                    place = (loc.get("district") or loc.get("municipality") or "").strip()

                    parts = [str(year), f"{km:,}".replace(",", " ") + " km"]
                    parts += [x for x in (fuel, gearbox, place, seller) if x]
                    details = "  ·  ".join(parts)

                    vid = v.get("id")
                    link = f"https://www.sauto.cz/osobni/detail/{man_seo}/{model_seo}/{vid}"

                    image = ""
                    imgs = v.get("images") or []
                    if imgs and imgs[0].get("url"):
                        image = imgs[0]["url"]
                        if image.startswith("//"):
                            image = "https:" + image
                        image += SAUTO_IMG_SUFFIX

                    cars.append({
                        "id":      str(vid),
                        "title":   title,
                        "price":   _format_czk(price_num),
                        "details": details,
                        "link":    link,
                        "image":   image,
                    })
                except Exception:
                    continue

            if len(items) < 100:
                break
    except Exception as e:
        print(f"  [sauto.cz/ari] Chyba: {e}")

    print(f"  sauto.cz/osobni (Ari): {len(cars)} inzerátů")
    return cars


# ─────────────────────────────────────────────
#  HLAVNÍ LOGIKA
# ─────────────────────────────────────────────

def process_feed(label: str, all_cars: list, prefix: str, seen_file: str,
                 tracked_file: str, index_file: str, day_key: str, now_str: str):
    """Společná logika pro jeden feed (auta / dodávky): nové + zlevněné
    inzeráty do denního souboru, index, seen, tracked a úklid."""
    cars_file = os.path.join(DATA_DIR, f"{prefix}{day_key}.json")

    seen       = load_seen(seen_file)
    today_cars = load_today_cars(cars_file)

    new_cars = [c for c in all_cars if c["id"] not in seen]

    # Zlevnění: už viděné auto s nižší cenou než při minulém běhu.
    # Auta viděná před zavedením tracked.json se při prvním běhu jen zaznamenají.
    tracked = load_tracked(tracked_file)
    drops = []
    for c in all_cars:
        price_num = parse_price(c["price"])
        old_num = tracked.get(c["id"], {}).get("price", 0)
        if c["id"] in seen and price_num and old_num and price_num < old_num:
            c["old_price"] = _format_czk(old_num)
            drops.append(c)
        tracked[c["id"]] = {"price": price_num or old_num, "last_seen": day_key}

    print(f"  [{label}] Nových: {len(new_cars)} | Zlevněných: {len(drops)} | Dnes celkem: {len(today_cars)} | Nalezeno: {len(all_cars)}")

    if new_cars or drops:
        for c in new_cars:
            c["found_at"] = now_str
        today_cars.extend(new_cars)

        today_by_id = {c["id"]: c for c in today_cars}
        for c in drops:
            existing = today_by_id.get(c["id"])
            if existing:
                # Auto už dnes v seznamu je – jen aktualizuj cenu,
                # původní "old_price" (ze začátku dne) zachovej.
                existing.setdefault("old_price", c["old_price"])
                existing["price"] = c["price"]
                existing["price_drop_at"] = now_str
            else:
                c["found_at"] = now_str
                c["price_drop_at"] = now_str
                today_cars.append(c)

        save_today_cars(cars_file, today_cars)
        update_index(day_key, len(today_cars), now_str, index_file)

        seen.update(c["id"] for c in new_cars)

        print(f"✅ [{label}] Uloženo → data/{prefix}{day_key}.json ({len(today_cars)} dnes)")
    else:
        print(f"  [{label}] Žádné nové ani zlevněné inzeráty od posledního spuštění.")

    # Úklid: zapomenout dlouho nevidané inzeráty, smazat staré denní soubory.
    forgotten = forget_stale(seen, tracked, day_key)
    save_seen(seen, seen_file)
    save_tracked(tracked, tracked_file)
    removed = prune_old_days(day_key, prefix, index_file)
    if forgotten or removed:
        print(f"🧹 [{label}] Zapomenuto: {forgotten} | Smazáno denních souborů: {removed}")


def main():
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    day_key = get_day_key()

    print(f"[{now_str}] Den: {day_key} | Spouštím kontrolu...")

    all_cars = []
    for brand in CONFIG["brands"]:
        all_cars += scrape_sauto(brand)
    all_cars += scrape_renocar()
    all_cars += scrape_bmwojete()
    all_cars += scrape_mercedesnasklade()
    all_cars += scrape_drivalia()

    process_feed("auta", all_cars, "cars_", CONFIG["seen_file"],
                 CONFIG["tracked_file"], CONFIG["index_file"], day_key, now_str)

    # Dodávky – samostatně, aby případná chyba nerozbila feed aut.
    try:
        vans = scrape_sauto_vans()
        # Prázdný výsledek = nejspíš selhal request; nic neukládej, ať se
        # dodávky zítra neobjeví znovu jako „nové“ a neodečte se last_seen.
        if vans:
            process_feed("dodávky", vans, VAN_CONFIG["file_prefix"],
                         VAN_CONFIG["seen_file"], VAN_CONFIG["tracked_file"],
                         VAN_CONFIG["index_file"], day_key, now_str)
    except Exception as e:
        print(f"  [dodávky] Chyba: {e}")

    # Ari car store – samostatně, stejná logika jako u dodávek.
    try:
        ari = scrape_sauto_ari()
        if ari:
            process_feed("ari", ari, ARI_CONFIG["file_prefix"],
                         ARI_CONFIG["seen_file"], ARI_CONFIG["tracked_file"],
                         ARI_CONFIG["index_file"], day_key, now_str)
    except Exception as e:
        print(f"  [ari] Chyba: {e}")


if __name__ == "__main__":
    main()
