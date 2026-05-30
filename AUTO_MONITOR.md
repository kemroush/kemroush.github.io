# Auto Monitor

Hlídač nových ojetých BMW / Mercedes / MINI na sauto.cz + skladových BMW na renocar.cz + skladových Mercedes na mercedesnasklade.cz. Výsledky jsou na `cars.html`.

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

`scrape_renocar()` volá JSON endpoint `?ajax=newFilterQuery-cars&brand=bmw&limit=500` a aplikuje stejné cenové / kilometrové / rokové filtry (BMW od 2022). API vrací cenu **bez DPH** v poli `price` — ve scraperu se násobí `(1 + vat/100)` (typicky ×1.21) aby zobrazená cena odpovídala té na renocar.cz. ID jsou prefixované `renocar:` aby nekolidovaly se sauto.cz.

`scrape_mercedesnasklade()` scrapuje stránkovaný listing `mercedesnasklade.cz/?sp-min=…&sp-max=…&km-max=…&cy-min=…&p=N` (server-side filtry), iteruje stránky dokud nejsou prázdné. Cena se čte z `.price.dph b` (s DPH). ID prefix `mns:`.

## Frontend filtry (cars.html)

- Řádek značek: Vše / BMW / Mercedes / Mini / Besties
- Řádek paliva: Vše / Spalovací / Hybrid / Elektro
- Řádek modelů: Vše / X1 / X2 / X3 / GLA / GLB (regex `\b<model>\b` proti `title`)
- Cenový posuvník 300k–750k

Filtry se průnikují (AND mezi řádky, OR uvnitř řádku).

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

## Známá omezení

- **Datum přidání inzerátu na sauto.cz** není dostupné v HTML listingu — zobrazuje se jen na detailu každého auta. Získat ho by vyžadovalo extra request na každý inzerát zvlášť (pomalé, riziko bloku). Proto se zobrazuje jen čas kdy inzerát zachytil skript (`found_at`).
- **Mezera přes noc** — auta přidaná na sauto.cz po posledním runu dne se objeví v reportu následujícího dne, ne včerejšího.
- **GitHub cron** občas skipne nebo zpozdí scheduled run. Řešení: ruční spuštění přes `gh workflow run`.

## Přidání dalšího zdroje

1. Přidej funkci `scrape_xxx() -> list[dict]` – vrací seznam dict s klíči `id, title, price, details, link, image`
   - `id` prefixuj jménem zdroje (např. `xxx:12345`) aby nekolidovalo s ostatními zdroji v `seen_cars.json`
   - `price` musí obsahovat číslo a "Kč" — frontend parsuje regexem `[\d\s ]+`
   - `details` musí obsahovat rok (`\b(20\d{2})\b`) a "<číslo> km" — frontend z toho vyčte hodnoty pro řazení
   - aplikuj stejné filtry (`min_price_czk`, `max_price_czk`, `max_km`, `min_year` + `min_year_overrides`) jako u ostatních
2. V `main()` přidej `all_cars += scrape_xxx()`
3. `found_at` doplní `main()` automaticky, scraper ho nenastavuje
