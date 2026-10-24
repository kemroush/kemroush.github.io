# Auto Monitor

Hlídač nových ojetých BMW / Mercedes / MINI na sauto.cz + skladových BMW na renocar.cz + skladových Mercedes na mercedesnasklade.cz + ojetých BMW / MINI z Future Drivalia (future.drivalia.cz) + oficiálních ojetých BMW / MINI z nabidky.bmw.cz. Výsledky jsou na `cars.html`.

## Jak to funguje

**GitHub Actions** spustí `auto_monitor.py` 4× denně (7:17, 11:17, 16:17, 20:17 CET). V létě (CEST = UTC+2) se časy posunou o hodinu dopředu — cron je v UTC. Minuta :17 je schválně: v celou hodinu GitHub plánované běhy často o hodiny zpožďuje nebo zahazuje. Dva běhy nikdy nejedou naráz (`concurrency`), a když mezitím přibude commit na `main`, bot se před pushem přeskládá (`git pull --rebase`).

Skript stahuje všechny zdroje přes `curl` (funkce `fetch()` – každý požadavek zkouší až 3×), uloží nové a zlevněné inzeráty do JSON a commitne je zpět do repa. GitHub Pages pak výsledky hned publikuje. Shrnutí běhu (kolik aut z kterého zdroje, kolik nových / zlevněných) je vidět jako anotace v přehledu runu na GitHub Actions.

Den se počítá od **6:00 do 6:00**. Více spuštění za den doplňuje stejný soubor.

## Soubory

```
auto_monitor.py          – skript (scraping, ukládání)
cars.html                – stránka s navigací mezi dny (statická, nemění se)
data/
  index.json             – seznam dní s počtem aut a časem aktualizace
  seen_cars.json         – globální seznam ID viděných inzerátů (dedupl. napříč dny)
  tracked.json           – id → {price, last_seen} (hlídání zlevnění, „už není v nabídce“, úklid)
  cars_YYYY-MM-DD.json   – inzeráty pro daný den
.github/workflows/
  auto-monitor.yml       – cron workflow (6:17, 10:17, 15:17, 19:17 UTC = 7:17, 11:17, 16:17, 20:17 CET)
```

## Filtr

V `auto_monitor.py` v sekci `CONFIG`:

```python
CONFIG = {
    "min_price_czk": 300_000,
    "max_price_czk": 750_000,
    "max_km":        100_000,
    "min_year":      2020,
    "min_year_overrides": {"bmw": 2022},
    "brands":        ["bmw", "mercedes-benz", "mini"],
    ...
}
```

`scrape_sauto()` volá interní JSON API sauto.cz (stejné jako dodávky a Ari) – `https://www.sauto.cz/api/v1/items/search` s `category_id=838` (osobní), `condition_seo=ojete`, `gearbox_seo=automaticka`, `price_from/price_to`, `tachometer_to` a `manufacturer_model_seo=bmw|mercedes-benz|mini`; stránkuje po 100 (limit `sauto_max_pages`). Rok jde jen klientsky (`manufacturing_date_from` API nepodporuje). Dřív se četl HTML výpis s limitem 5 stránek, který u Mercedesů uřízl zhruba polovinu nabídky. ID jsou čistě číselná (sauto ID, stejná jako dřív).

Všechny tři sauto feedy sdílí `_scrape_sauto_feed()`; liší se jen konfigurací, kategorií a whitelistem modelů. Výsledky se deduplikují podle ID.

**Výbava (štítky):** sauto výbavu v listingu neposílá, ale vyhledávání umí filtr `equipment_cb=<id>`. Pro každou položku z `SAUTO_EQUIPMENT` (Apple CarPlay #278, ambientní osvětlení #276, vyhřívaná sedadla #42) se pustí jeden dotaz navíc a nalezená auta dostanou pole `eq` (`["carplay", "ambient", "heated"]`). Ukládá se do denního souboru i do `*tracked.json`, takže stránka kreslí štítky i u starších inzerátů. Další položku stačí přidat do `SAUTO_EQUIPMENT` (ID je vidět v `equipment_cb` v detailu `GET /api/v1/items/<id>`) a popisek do `EQ_LABELS` v `cars.html`. Jen sauto – dealerské zdroje výbavu nemají. **Pozor:** neznámou hodnotu filtru (např. položku, kterou kategorie nemá – u užitkových chybí ambientní osvětlení) API tiše ignoruje a vrátí všechno; bot to pozná (filtr vrátil celou nabídku) a takový filtr pro daný feed přeskočí. Stejná pojistka platí pro 4×4.

**Pohon 4×4:** sauto ho v listingu neposílá, takže se stejný dotaz pustí ještě jednou s `drive_seo=4x4` a nalezená ID dostanou do `details` štítek `4×4` (hned za palivem). U ostatních zdrojů se 4×4 pozná z názvu (`xDrive`, `4MATIC`, `ALL4`, `quattro`, `4x4`). Stránka štítek u starších inzerátů bez něj doplní podle názvu.

`scrape_renocar()` volá JSON endpoint `?ajax=newFilterQuery-cars&brand=bmw&limit=500` a aplikuje stejné cenové / kilometrové / rokové filtry (BMW od 2022). API vrací cenu **bez DPH** v poli `price` — ve scraperu se násobí `(1 + vat/100)` (typicky ×1.21) aby zobrazená cena odpovídala té na renocar.cz. ID jsou prefixované `renocar:` aby nekolidovaly se sauto.cz.

`scrape_mercedesnasklade()` scrapuje stránkovaný listing `mercedesnasklade.cz/?sp-min=…&sp-max=…&km-max=…&cy-min=…&p=N` (server-side filtry), iteruje stránky dokud nejsou prázdné. Cena se čte z `.price.dph b` (s DPH). ID prefix `mns:`.

`scrape_drivalia()` volá WP AJAX endpoint `future.drivalia.cz/wp-admin/admin-ajax.php` s `action=ddf_query`. Nonce se vytahuje fresh z `/vozidla/` při každém běhu (anonymní WP nonce je stabilní napříč requesty bez cookies). Filtry (`price_min/max`, `km_max`, `year_min`, `brand[]=…`) jdou server-side. Iteruje brandy `bmw` a `mini` (Mercedes-Benz Drivalia nemají), pro každý prochází stránky dokud `hasMore=true`. Data čte z `product_data` v JSON odpovědi, obrázky z přiloženého HTML `cards` (joinuje přes URL slug). ID prefix `drivalia:` + leading numeric WP product ID.

`scrape_bmwojete()` volá JSON API oficiální burzy ojetých vozů `nabidky.bmw.cz` — `POST /ojete/api/v1/ems/bmw-used-cs_CZ/search` s tělem `{"$offset":0,"$limit":500,"$sort":[{"$field":"transactionalPrice","$order":"asc"}]}`. **Pozor:** API ignoruje `$offset` (stránkování nefunguje) a ignoruje i field-level filtry — funguje jen `$sort`. Proto se stáhne jeden velký `$limit` seřazený podle ceny vzestupně a filtruje se klientsky; jakmile cena přeteče `max_price_czk`, cyklus končí. Cena `transactionalPrice` je **s DPH** (gross). Web míchá BMW i MINI, značka se pozná z prefixu `title` (per-brand `min_year`: BMW 2022, MINI 2020). Obrázek se skládá z podepsaného prefixu `.../vehicle/704/<hash>/<id>?<imagesLastChanged>` (hash je konstanta ze šablony webu). Odkaz na detail `.../ojete/hledat/detaily/<id>/`. ID prefix `bmwojete:`.

## Dodávky (samostatný feed)

Stejný běh `auto_monitor.py` sbírá i ojeté dodávky ze sauto.cz (kategorie užitková) a ukládá je **odděleně** od aut:

```
data/vans_index.json         – seznam dní (jako index.json)
data/vans_YYYY-MM-DD.json    – nové + zlevněné dodávky daného dne
data/vans_seen.json          – viděná ID
data/vans_tracked.json       – id → {price, last_seen}
```

`scrape_sauto_vans()` volá stejné JSON API jako auta, jen s `category_id=839` (užitková), stránkuje po 100, dokud stránka není kratší. Filtry jsou v `VAN_CONFIG`: 40–150k Kč, rok 2008+, 1 000–300 000 km a whitelist `manufacturer_seo/model_seo` jen středních a velkých dodávek (Transit, Transporter, Proace, Vito, Master, Trafic, Vivaro, Boxer, Jumper, Ducato, Sprinter, Crafter…). Malé dodávky (Caddy, Kangoo, Berlingo, Praktik…) a pick-upy se přeskakují. `blocked_sellers` platí i tady. ID jsou čistě číselná (sauto ID). Když scraper vrátí 0 dodávek (nejspíš selhal request), feed dodávek se ten běh vůbec neukládá.

Na `cars.html` se mezi feedy přepíná přepínačem **Auta / Dodávky / Ari**; přímý odkaz na dodávky je `cars.html#dodavky`.

## Ari car store (samostatný feed)

Třetí feed ve stejném běhu `auto_monitor.py` – malá ojetá auta s automatem pro Ari ze sauto.cz (osobní). Ukládá se **odděleně**:

```
data/ari_index.json          – seznam dní
data/ari_YYYY-MM-DD.json     – nová + zlevněná auta daného dne
data/ari_seen.json           – viděná ID
data/ari_tracked.json        – id → {price, last_seen}
```

`scrape_sauto_ari()` volá stejné JSON API jako dodávky, jen `category_id=838` (osobní) a navíc server-side `gearbox_seo=automaticka`, `tachometer_to=…` a `manufacturer_model_seo=toyota:yaris,c-hr|audi:a1,a3|…` (formát: značka`:`modely oddělené čárkou, značky oddělené `|`). Stránkuje po 100. Filtry jsou v `ARI_CONFIG`: 100–400k Kč, rok 2014+ (rok jde jen klientsky – `manufacturing_date_from` API nepodporuje), 1 000–250 000 km, whitelist malých modelů (Toyota Yaris/Aygo/Auris/Corolla/C-HR, Audi A1/A3, Mercedes třída A/CLA, BMW řada 1/2, VW Polo/Golf, Škoda Fabia/Scala, Seat Ibiza/Leon, Cupra, Peugeot 208/2008, Mazda 2/3, Lexus CT/UX, DS 3, Hyundai i20, Kia Rio/Stonic). **Mini je explicitně blokované** (`blocked_manufacturers`). `blocked_sellers` platí i tady. Odkaz na detail `https://www.sauto.cz/osobni/detail/<značka>/<model>/<id>`.

**Vyřazené pohony (`ari_exclusion_reason()`):** po scrapu se z Ari feedu ještě vyhazují inzeráty podle titulku + detailu (sauto API motor nevrací): Toyota Aygo a Peugeot 1.2 VTi (ultra nízký výkon), Peugeot/DS benzín (1.2 PureTech, rozvod v oleji), Audi A1/A3 benzín + S tronic, VAG benzín s 1.0/1.2/1.4/1.8 TSI a DSG (Fabia/Scala/Polo/Ibiza/Golf/Leon; 1.5 TSI zůstává; u malých modelů bez uvedeného motoru se vyřadí také), sporťáky VAG (GTI, GTD, Golf R, Cupra) a elektro / plug-in hybridy (e-Golf, GTE, e-208, 225xe – sauto má u e-Golfů palivo „Benzín“, proto se hledá i v titulku). Diesely VAG, BMW, Mercedes, Toyota/Mazda hybridy a Kia/Hyundai zůstávají. Počty vyřazených se vypisují do logu (`[ari] vyřazeno rizikových pohonů: …`). Při každém běhu se před scrapem volá `purge_ari_excluded()`, která stejný filtr uplatní i na už uložené `data/ari_YYYY-MM-DD.json` (vyřazená auta smaže, přepočítá `ari_index.json` a odstraní jejich ID ze `ari_seen.json` a `ari_tracked.json`); prázdný denní soubor se smaže i z indexu. Po prvním úklidu je idempotentní.

**Pozor:** neznámé `model_seo` API tiše ignoruje a vrátí celou značku – proto se whitelist kontroluje i klientsky. Nový model přidej do `ARI_CONFIG["models"]` jen se správným `seo_name` ze sauto (vidět v URL detailu inzerátu). Když scraper vrátí 0 aut, feed se ten běh neukládá.

## Hlídání zlevnění

`data/tracked.json` (u dodávek `vans_tracked.json`, u Ari `ari_tracked.json`) drží pro každé `id` poslední známou cenu (číslo v Kč) a den, kdy bylo auto naposledy vidět (`last_seen`). Při každém běhu se u aut, která už jsou v `seen_cars.json`, porovná aktuální cena s uloženou; je-li nižší, auto se přidá do dnešního `cars_YYYY-MM-DD.json` s poli `old_price` (předchozí cena, formátovaný string) a `price_drop_at`. Pokud už auto v dnešním souboru je (nové dnes nebo zlevněné dřív během dne), jen se mu aktualizuje `price` a `old_price` zůstane ta původní. Auta, u kterých ještě není uložená cena, se při prvním běhu jen zaznamenají (bez alertu). Zdražení se neoznamuje, jen se přepíše uložená cena. Auto, které vypadne z filtrů (např. zdraží nad `max_price_czk`), se nesleduje, dokud se znovu neobjeví.

## Frontend filtry (cars.html)

Ve všech třech feedech (Auta / Dodávky / Ari) stejně:

- **Řádek značek** s počty – staví se z dat zobrazeného dne / historie, ukazují se jen značky, které v datech jsou. Pořadí tlačítek je v `BRAND_ORDER` (zbytek podle počtu). U Aut navíc **Besties** (BMW X1 + Mercedes GLA) a všude **Zlevněné** (jen auta s `old_price`).
- **Řádek modelů** s počty – ukáže se po výběru značky. Výběr modelu omezuje jen svou značku (např. Toyota Yaris + celá Škoda).
- Počty = kolik aut se ukáže po kliknutí (ostatní filtry se započítávají, v historii se nepočítají prodaná auta).
- Značka a model jsou sauto seo názvy: u sauto z odkazu (`/<sekce>/detail/<značka>/<model>/<id>`), u dealerských zdrojů z názvu (`titleKey()`: BMW 218i → `bmw/rada-2`, Mercedes-Benz Třída A 200 → `mercedes-benz/tridy-a`, MINI Cooper SE ALL4 → `mini/countryman`…), takže dealer i bazar spadnou pod stejný model. Popisky dělá `modelLabel()`, výjimky jsou v `MODEL_LABELS`.
- Řádek prodejců: Všichni / Soukromí / Bazary (podle „Soukromý“ na konci `details`)
- Řádek paliva: Vše / Spalovací / Hybrid / Elektro (ne u Dodávek)
- Cenový posuvník 300k–750k (Dodávky 40k–150k, Ari 100k–400k)

Filtry se průnikují (AND mezi řádky, OR uvnitř řádku).

## Ruční spuštění

```bash
# GitHub Actions (bez čekání na cron)
gh workflow run auto-monitor.yml --repo kemroush/kemroush.github.io

# Nanečisto – stáhne a vypíše shrnutí, nic neuloží ani necommitne
# (v GitHubu: Actions → Auto Monitor → Run workflow → zaškrtnout „Jen nanečisto“)
gh workflow run auto-monitor.yml --repo kemroush/kemroush.github.io -f dry_run=true
DRY_RUN=1 python3 auto_monitor.py   # lokálně

# Lokálně
pip install beautifulsoup4 lxml
python3 auto_monitor.py

# Lokální preview stránky (fetch potřebuje HTTP, ne file://)
python3 -m http.server 8080
# → http://localhost:8080/cars.html
```

## Známá omezení

- **Zobrazuje se čas, kdy inzerát zachytil bot** (`found_at`), ne kdy ho prodejce vložil.
- **Mezera přes noc** — auta přidaná na sauto.cz po posledním runu dne se objeví v reportu následujícího dne, ne včerejšího.
- **GitHub cron** občas skipne nebo zpozdí scheduled run (proto běhy v :17, ne v :00). Řešení: ruční spuštění přes `gh workflow run`.

## Přidání dalšího zdroje

1. Přidej funkci `scrape_xxx() -> list[dict]` – vrací seznam dict s klíči `id, title, price, details, link, image`
   - stahuj přes `fetch(url, headers=…, as_json=…)` (User-Agent + 3 pokusy jsou v ní)
   - `id` prefixuj jménem zdroje (např. `xxx:12345`) aby nekolidovalo s ostatními zdroji v `seen_cars.json`
   - `price` musí obsahovat číslo a "Kč" — frontend parsuje regexem `[\d\s ]+`
   - `details` musí obsahovat rok (`\b(20\d{2})\b`) a "<číslo> km" — frontend z toho vyčte hodnoty pro řazení
   - aplikuj stejné filtry (`min_price_czk`, `max_price_czk`, `max_km`, `min_year` + `min_year_overrides`) jako u ostatních
   - když web pozná 4×4, přidej do `details` štítek `AWD_TAG` (jinak stačí `AWD_RE.search(title)`)
2. V `main()` přidej `scrape_xxx` do seznamu scraperů feedu `auta`
3. `found_at` doplní `process_feed()` automaticky, scraper ho nenastavuje
