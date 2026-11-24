#!/usr/bin/env python3
"""Ceny pro sbírku (sbirka/index.html).

Přečte sbirka/collection.json, ke každé položce se zadaným ID dohledá cenu
a zapíše data/collection_prices.json, který čte stránka.

Zdroje:
  * Pokémon sealed – tcgcsv.com (veřejné denní zrcadlo cen TCGplayeru, USD,
    bez klíče). Položka se identifikuje číslem produktu z tcgplayer.com/product/<id>.
  * LEGO sady a minifigurky – BrickLink API (price guide, EUR). Potřebuje
    4 klíče v GitHub secrets: BRICKLINK_CONSUMER_KEY, BRICKLINK_CONSUMER_SECRET,
    BRICKLINK_TOKEN, BRICKLINK_TOKEN_SECRET (u tokenu IP i maska 0.0.0.0).
  * Kurzy – ČNB, denní kurz devizového trhu.

Ceny se ukládají pod klíčem "typ:id:stav" (např. "lego_set:75192-1:new"),
takže změna počtu kusů nic nepřepočítává. Ke každé ceně se vede denní
historie, ze které stránka počítá změnu za 30 dní.

Spuštění:  python3 collection_prices.py      (DRY_RUN=1 = nic nezapisovat)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
COLLECTION_FILE = os.path.join(ROOT, "sbirka", "collection.json")
PRICES_FILE = os.path.join(ROOT, "data", "collection_prices.json")
DRY_RUN = bool(os.environ.get("DRY_RUN"))
TZ = ZoneInfo("Europe/Prague")
HISTORY_POINTS = 400          # ~ rok a kus denních bodů na položku
USER_AGENT = "kemroush-sbirka/1.0 (+https://kemroush.github.io/sbirka/)"

CNB_URL = ("https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/"
           "kurzy-devizoveho-trhu/denni_kurz.txt")
TCGCSV = "https://tcgcsv.com/tcgplayer"
TCG_CATEGORIES = (3, 85)      # Pokémon (EN), Pokémon Japan
BRICKLINK_API = "https://api.bricklink.com/api/store/v1"

TYPES = {"lego_set", "lego_minifig", "pokemon_sealed"}


# ─────────────────────────────────────────────
#  HTTP
# ─────────────────────────────────────────────

class HttpError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.url = url


def http_get(url: str, headers: dict | None = None, retries: int = 3, timeout: int = 40) -> bytes:
    """GET s opakováním při výpadku sítě / 5xx / 429. 4xx vrací hned."""
    h = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    h.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = HttpError(e.code, url)
            if e.code != 429 and e.code < 500:
                raise last from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def get_json(url: str, headers: dict | None = None):
    return json.loads(http_get(url, headers).decode("utf-8"))


# ─────────────────────────────────────────────
#  KURZY ČNB
# ─────────────────────────────────────────────

def parse_cnb(text: str) -> dict:
    """Formát: '24.11.2026 #226' / hlavička / 'země|měna|množství|kód|kurz'."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rates: dict = {"date": lines[0].split()[0] if lines else None}
    for ln in lines[2:]:
        parts = ln.split("|")
        if len(parts) != 5:
            continue
        try:
            amount = int(parts[2])
            rate = float(parts[4].replace(",", "."))
        except ValueError:
            continue
        rates[parts[3]] = round(rate / amount, 4)
    return rates


def fetch_rates() -> dict:
    return parse_cnb(http_get(CNB_URL).decode("utf-8"))


# ─────────────────────────────────────────────
#  POKÉMON – tcgcsv.com
# ─────────────────────────────────────────────

class Tcg:
    """Ceny produktů z TCGplayeru přes tcgcsv.com.

    tcgcsv vrací ceny po setech (groups), ale z odkazu na produkt známe jen
    productId. Set se proto jednou dohledá projitím setů (od nejnovějších)
    a uloží do cache v prices souboru ("tcg_groups"), další běhy už jen čtou.
    """

    def __init__(self, cache: dict, pause: float = 0.15):
        self.cache = cache                      # productId -> [categoryId, groupId]
        self.pause = pause
        self._groups: dict = {}
        self._products: dict = {}
        self._prices: dict = {}

    def groups(self, cat: int) -> list:
        if cat not in self._groups:
            res = get_json(f"{TCGCSV}/{cat}/groups").get("results") or []
            res.sort(key=lambda g: g.get("publishedOn") or "", reverse=True)
            self._groups[cat] = res
        return self._groups[cat]

    def products(self, cat: int, gid: int) -> list:
        k = (cat, gid)
        if k not in self._products:
            self._products[k] = get_json(f"{TCGCSV}/{cat}/{gid}/products").get("results") or []
            time.sleep(self.pause)
        return self._products[k]

    def prices(self, cat: int, gid: int) -> list:
        k = (cat, gid)
        if k not in self._prices:
            self._prices[k] = get_json(f"{TCGCSV}/{cat}/{gid}/prices").get("results") or []
            time.sleep(self.pause)
        return self._prices[k]

    def resolve(self, product_ids: set[str]) -> None:
        missing = {str(p) for p in product_ids if str(p) not in self.cache}
        if not missing:
            return
        print(f"  [tcg] dohledávám set pro {len(missing)} produkt(ů)…")
        for cat in TCG_CATEGORIES:
            for g in self.groups(cat):
                gid = g.get("groupId")
                if gid is None:
                    continue
                for p in self.products(cat, gid):
                    pid = str(p.get("productId"))
                    if pid in missing:
                        self.cache[pid] = [cat, gid]
                        missing.discard(pid)
                if not missing:
                    return
        if missing:
            print(f"  [tcg] nenalezeno: {', '.join(sorted(missing))}")

    @staticmethod
    def pick_price(rows: list, pid: str) -> float | None:
        mine = [r for r in rows if str(r.get("productId")) == pid]
        mine.sort(key=lambda r: 0 if r.get("subTypeName") in (None, "Normal") else 1)
        for r in mine:
            for f in ("marketPrice", "midPrice", "lowPrice"):
                v = r.get(f)
                if isinstance(v, (int, float)) and v > 0:
                    return float(v)
        return None

    def lookup(self, pid: str) -> tuple[float, str | None, str | None]:
        loc = self.cache.get(pid)
        if not loc:
            raise LookupError("produkt na TCGplayeru nenalezen – zkontroluj číslo z odkazu")
        cat, gid = loc
        usd = self.pick_price(self.prices(cat, gid), pid)
        info = next((p for p in self.products(cat, gid) if str(p.get("productId")) == pid), {})
        if usd is None:
            raise LookupError("TCGplayer k produktu zatím nemá cenu")
        return usd, info.get("name"), info.get("imageUrl")


# ─────────────────────────────────────────────
#  LEGO – BrickLink API (OAuth 1.0a, HMAC-SHA1)
# ─────────────────────────────────────────────

def _enc(s) -> str:
    return urllib.parse.quote(str(s), safe="~-._")


def oauth_header(method: str, url: str, params: dict, consumer_key: str, consumer_secret: str,
                 token: str, token_secret: str, nonce: str | None = None,
                 timestamp: str | None = None) -> str:
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(12),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    pairs = sorted((_enc(k), _enc(v)) for k, v in {**params, **oauth}.items())
    normalized = "&".join(f"{k}={v}" for k, v in pairs)
    base = "&".join([method.upper(), _enc(url), _enc(normalized)])
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return 'OAuth realm="", ' + ", ".join(f'{k}="{_enc(v)}"' for k, v in oauth.items())


class BrickLinkError(Exception):
    def __init__(self, code, message: str):
        super().__init__(message)
        self.code = code


class BrickLink:
    KEYS = ("BRICKLINK_CONSUMER_KEY", "BRICKLINK_CONSUMER_SECRET",
            "BRICKLINK_TOKEN", "BRICKLINK_TOKEN_SECRET")

    # Pořadí, ve kterém se zkouší price guide: nejdřív skutečné prodeje
    # v Evropě, pak celosvětově, nakonec aktuální nabídky.
    ATTEMPTS = (
        ("sold", "europe", "prodeje v Evropě za 6 měsíců"),
        ("sold", None, "prodeje celosvětově za 6 měsíců"),
        ("stock", "europe", "aktuální nabídky v Evropě"),
        ("stock", None, "aktuální nabídky celosvětově"),
    )

    def __init__(self, env=os.environ, pause: float = 0.3):
        self.creds = [env.get(k, "").strip() for k in self.KEYS]
        self.ok = all(self.creds)
        self.pause = pause

    def get(self, path: str, params: dict | None = None):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        url = BRICKLINK_API + path
        auth = oauth_header("GET", url, params, *self.creds)
        full = url + ("?" + urllib.parse.urlencode(params) if params else "")
        try:
            body = get_json(full, {"Authorization": auth})
        except HttpError as e:
            raise BrickLinkError(e.status, f"BrickLink HTTP {e.status}") from None
        finally:
            time.sleep(self.pause)
        meta = body.get("meta") or {}
        if meta.get("code") != 200:
            desc = meta.get("description") or meta.get("message") or "neznámá chyba"
            raise BrickLinkError(meta.get("code"), f"BrickLink {meta.get('code')}: {desc}")
        return body.get("data") or {}

    def item(self, bl_type: str, no: str) -> tuple[str | None, str | None]:
        d = self.get(f"/items/{bl_type}/{urllib.parse.quote(no)}")
        name = html.unescape(d.get("name") or "") or None
        img = d.get("image_url") or d.get("thumbnail_url")
        if img and img.startswith("//"):
            img = "https:" + img
        return name, img

    def price(self, bl_type: str, no: str, condition: str) -> tuple[float, str]:
        new_or_used = "U" if condition == "used" else "N"
        last_err: Exception | None = None
        for guide, region, label in self.ATTEMPTS:
            try:
                d = self.get(f"/items/{bl_type}/{urllib.parse.quote(no)}/price", {
                    "guide_type": guide,
                    "new_or_used": new_or_used,
                    "currency_code": "EUR",
                    "region": region,
                })
            except BrickLinkError as e:
                # špatné klíče (401/403) nebo neznámé ID (404) nemá smysl zkoušet dál;
                # jiná chyba (např. nepodporovaný region) → další varianta
                if e.code in (401, 403, 404):
                    raise
                last_err = e
                continue
            qty = int(d.get("unit_quantity") or 0)
            val = float(d.get("qty_avg_price") or 0) or float(d.get("avg_price") or 0)
            if qty > 0 and val > 0:
                return val, f"BrickLink – {label}, průměr z {qty} ks"
        if last_err:
            raise last_err
        raise LookupError("na BrickLinku zatím nejsou prodeje ani nabídky")


# ─────────────────────────────────────────────
#  HLAVNÍ BĚH
# ─────────────────────────────────────────────

def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def wanted_keys(collection: dict) -> dict[str, tuple[str, str, str]]:
    """Unikátní (typ, id, stav) pro položky, které ještě mám (count > 0)."""
    out: dict[str, tuple[str, str, str]] = {}
    for it in collection.get("items") or []:
        t, ref = it.get("type"), str(it.get("ref") or "").strip()
        if t not in TYPES or not ref:
            continue
        try:
            if int(it.get("count") or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        cond = "new" if t == "pokemon_sealed" else ("used" if it.get("condition") == "used" else "new")
        out[f"{t}:{ref}:{cond}"] = (t, ref, cond)
    return out


def add_history(entry: dict, day: str, value: int) -> None:
    hist = [h for h in entry.get("history") or [] if h and h[0] != day]
    hist.append([day, value])
    hist.sort(key=lambda h: h[0])
    entry["history"] = hist[-HISTORY_POINTS:]


def update_prices(collection: dict, prices: dict, rates: dict | None, tcg: Tcg,
                  bricklink: BrickLink, now: datetime) -> tuple[int, int]:
    keys = wanted_keys(collection)
    day = now.date().isoformat()
    stamp = now.isoformat(timespec="minutes")
    items = prices.setdefault("items", {})

    poke = {ref for (t, ref, _c) in keys.values() if t == "pokemon_sealed"}
    if poke:
        try:
            tcg.resolve(poke)
        except Exception as e:   # síť / tcgcsv mimo provoz – ceny se jen nepřepočítají
            print(f"  [tcg] chyba při hledání setů: {e}")

    ok = failed = 0
    for key, (t, ref, cond) in sorted(keys.items()):
        entry = dict(items.get(key) or {})
        try:
            if t == "pokemon_sealed":
                orig, name, image = tcg.lookup(ref)
                currency, source = "USD", "tcgplayer"
                basis = "TCGplayer – tržní cena (US trh), přepočteno kurzem ČNB"
            else:
                if not bricklink.ok:
                    raise LookupError("chybí BrickLink klíče v GitHub secrets")
                bl_type = "SET" if t == "lego_set" else "MINIFIG"
                name, image = entry.get("name"), entry.get("image")
                if not name:
                    try:
                        name, image = bricklink.item(bl_type, ref)
                    except BrickLinkError as e:
                        print(f"  [bl] {key}: katalog – {e}")
                orig, basis = bricklink.price(bl_type, ref, cond)
                currency, source = "EUR", "bricklink"
            rate = (rates or {}).get(currency)
            if not rate:
                raise LookupError(f"chybí kurz ČNB pro {currency}")
            value = int(round(orig * rate))
            entry.update({
                "czk": value, "orig": round(orig, 2), "currency": currency,
                "source": source, "basis": basis, "checked": stamp, "error": None,
            })
            if name:
                entry["name"] = name
            if image:
                entry["image"] = image
            add_history(entry, day, value)
            ok += 1
            print(f"  ✓ {key}: {value} Kč ({orig:.2f} {currency})")
        except Exception as e:  # jedna položka nesmí shodit celý běh
            entry["error"] = str(e) or e.__class__.__name__
            entry["error_at"] = stamp
            failed += 1
            print(f"  ✗ {key}: {entry['error']}")
        items[key] = entry
    return ok, failed


def main() -> int:
    try:
        collection = load_json(COLLECTION_FILE, {"items": []})
    except json.JSONDecodeError as e:
        print(f"❌ sbirka/collection.json není platný JSON: {e}")
        return 1
    prices = load_json(PRICES_FILE, {})
    prices.setdefault("items", {})
    prices.setdefault("tcg_groups", {})

    try:
        rates = fetch_rates()
        print(f"Kurz ČNB {rates.get('date')}: USD {rates.get('USD')}, EUR {rates.get('EUR')}")
    except Exception as e:
        rates = prices.get("rates")
        print(f"⚠️  Kurz ČNB nestažen ({e}) – použiju poslední známý: {rates}")

    bricklink = BrickLink()
    if not bricklink.ok:
        print("⚠️  BrickLink klíče nejsou nastavené – LEGO ceny se přeskočí")

    now = datetime.now(TZ)
    ok, failed = update_prices(collection, prices, rates, Tcg(prices["tcg_groups"]), bricklink, now)
    prices["updated"] = now.isoformat(timespec="minutes")
    if rates:
        prices["rates"] = rates

    print(f"Hotovo: {ok} cen, {failed} chyb")
    if DRY_RUN:
        print("DRY_RUN – nic neukládám")
        return 0
    os.makedirs(os.path.dirname(PRICES_FILE), exist_ok=True)
    tmp = PRICES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PRICES_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
