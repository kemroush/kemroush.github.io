# Auto Monitor

Hlídač nových ojetých SUV s automatem na sauto.cz. Výsledky jsou na `cars.html`.

## Jak to funguje

**GitHub Actions** spustí `auto_monitor.py` 4× denně (7:00, 11:00, 16:00, 20:00 CET). V létě (CEST = UTC+2) se časy posunou o hodinu dopředu — cron je v UTC. Skript scrapuje sauto.cz přes `curl`, uloží nové inzeráty do JSON a commitne je zpět do repa. GitHub Pages pak okamžitě publikuje výsledky.

Den se počítá od **6:00 do 6:00**. Více spuštění za den doplňuje stejný soubor.

## Soubory

```
auto_monitor.py          – skript (scraping, ukládání)
cars.html                – stránka s navigací mezi dny (statická, nemění se)
data/
  index.json             – seznam dní s počtem aut a časem aktualizace
  seen_cars.json         – globální seznam ID viděných inzerátů (dedupl. napříč dny)
  cars_YYYY-MM-DD.json   – inzeráty pro daný den
.github/workflows/
  auto-monitor.yml       – cron workflow (6:00, 10:00, 15:00, 19:00 UTC = 7:00, 11:00, 16:00, 20:00 CET)
```

## Filtr

V `auto_monitor.py` v sekci `CONFIG`:

```python
CONFIG = {
    "max_price_czk": 700_000,   # max cena
    ...
}
```

URL parametry filtru jsou v `scrape_sauto()`:
- `stav=ojete` – ojeté
- `typ=suv` – karoserie SUV
- `prevodovka=automaticka` – automat
- `razeni=datum-vlozeni-desc` – řazení od nejnovějšího

## Ruční spuštění

```bash
# GitHub Actions (bez čekání na cron)
gh workflow run auto-monitor.yml --repo kemroush/kemroush.github.io

# Lokálně
pip install beautifulsoup4 lxml
python3 auto_monitor.py

# Lokální preview stránky (fetch potřebuje HTTP, ne file://)
python3 -m http.server 8080
# → http://localhost:8080/cars.html
```

## Přidání dalšího zdroje

1. Přidej funkci `scrape_xxx() -> list[dict]` – vrací seznam dict s klíči `id, title, price, details, link`
2. V `main()` přidej `all_cars += scrape_xxx()`
