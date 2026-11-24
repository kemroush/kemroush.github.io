# Sbírka (`sbirka/`)

Evidence LEGO sad, LEGO minifigurek a Pokémon sealed s odhadem aktuální ceny.
Stránka: https://kemroush.github.io/sbirka/

## Jak to funguje

| Soubor | Kdo ho píše | Obsah |
|---|---|---|
| `sbirka/index.html` | ručně | stránka (jeden soubor, bez buildu) |
| `sbirka/collection.json` | **stránka** přes GitHub API | co ve sbírce mám: typ, ID, stav, počet, nákupní cena, vlastní odhad, poznámka |
| `data/collection_prices.json` | **bot** `collection_prices.py` | ceny podle klíče `typ:id:stav`, denní historie, kurzy ČNB, cache setů TCGplayeru |

- Úpravy na stránce (±kusy, přidání, smazání) se drží jako koncept v prohlížeči,
  dokud nedáš **Uložit**. Pak stránka commitne `sbirka/collection.json` přímo do
  `main` (je to datový soubor jako u botů, ne kód – proto bez PR).
- Commit `sbirka/collection.json` spustí workflow **Collection Prices**, takže
  ceny nových kusů jsou na stránce zhruba za pár minut. Jinak bot běží denně
  v 5:43 a jde spustit tlačítkem **Obnovit ceny**.
- Kus, který prodáš, stáhni na 0 – zůstane ve sbírce jako „prodáno“ (přepínač
  *zobrazit prodané*), bot pro něj ceny dál nestahuje.

## Zdroje cen

| Typ | ID na stránce | Zdroj (automaticky) | Měna |
|---|---|---|---|
| Pokémon sealed | číslo z `tcgplayer.com/product/<id>` (stačí vložit odkaz) | **Cardmarket** – cenový trend z oficiálního veřejného denního price guide (EU trh, prodává tam i většina Čechů); produkt se páruje podle názvu z TCGplayeru. Záloha a srovnání: **TCGplayer** přes tcgcsv.com (US trh) | EUR / USD |
| LEGO sada | číslo sady (`75192` → `75192-1`) | **BrickLink** price guide: prodeje v Evropě za 6 měsíců → celosvětově → aktuální nabídky (potřebuje klíče) | EUR |
| Minifigurka | BrickLink ID (`sw0001a`, nebo vložit odkaz s `M=`) | totéž | EUR |

Vše se přepočítá denním kurzem ČNB; ostatní zjištěné ceny se ukážou v detailu položky „pro srovnání“.

**České obchody (Heureka):** automaticky nejdou – Heureka automatické dotazy z GitHub Actions odmítá (HTTP 403) a obcházet to nebudeme. Českou cenu proto zadej do **Vlastní odhad** (přebije cenu od bota, nemá ale historii). V detailu každé položky je odkaz „Heureka (CZ obchody)“ s rovnou vyplněným hledáním. LEGO sady ve sbírce mají vlastní odhad podle Heureky z 24. 11. 2026 (poznámka u položky).

## Nastavení (jednou)

### 1. GitHub token pro stránku
https://github.com/settings/personal-access-tokens/new → *Only select repositories*:
`kemroush.github.io` → Permissions: **Contents: Read and write**
(volitelně **Actions: Read and write** pro tlačítko „Obnovit ceny“).
Token vlož na stránce přes „Připojit GitHub“; ukládá se jen v `localStorage`
daného prohlížeče (na každém zařízení zvlášť).

### 2. BrickLink klíče pro bota (jen kvůli LEGO cenám)
1. https://www.bricklink.com/v2/api/register_consumer.page → zaregistrovat consumer.
2. Access token pro IP **0.0.0.0** a masku **0.0.0.0** (GitHub Actions nemají pevnou IP).
3. V repu *Settings → Secrets and variables → Actions* přidat:
   `BRICKLINK_CONSUMER_KEY`, `BRICKLINK_CONSUMER_SECRET`, `BRICKLINK_TOKEN`, `BRICKLINK_TOKEN_SECRET`.

Bez klíčů bot LEGO přeskočí (u položky se ukáže „chybí BrickLink klíče“),
Pokémon ceny jdou i tak.

## Bot

```
python3 collection_prices.py          # stáhne a zapíše data/collection_prices.json
DRY_RUN=1 python3 collection_prices.py  # jen vypíše
```

Jen standardní knihovna Pythonu. Jedna chybná položka neshodí běh – u ní se do
`error` zapíše důvod a zůstane poslední známá cena. TCGplayer produkt se při
prvním výskytu dohledá projitím setů (od nejnovějších) a set se uloží do
`tcg_groups`, další běhy už jsou rychlé.
