# CLAUDE.md — kemroush.github.io

Personal website + auto/auction monitoring tools. Hosted on **GitHub Pages** at kemroush.cz (auto-deploys from `main`).

## Layout
- **`index.html`** — landing page (single file)
- **`cars.html`** — car monitoring dashboard (sauto.cz, renocar.cz, future.drivalia.cz, mercedesnasklade)
- **`hokynarstvi.html`** — auctions dashboard
- **`auto_monitor.py`** + **`scrapers/`** — car scraper bot (runs via GitHub Actions, commits to `data/`)
- **`auction_monitor.py`** — auctions scraper
- **`data/`** — JSON output from the bots (auto-committed; do not hand-edit)
- **`cce-c1.*`**, **`test1.html`**, **`test2.html`** — legacy/experimental, leave alone
- **`AUTO_MONITOR.md`** — bot documentation

## Editing workflow (incl. from iPhone)
- Make changes on a **branch** and open a **PR** — don't push directly to `main`. The site is live, so a bad commit goes live in ~1 minute.
- The auto-monitor bot pushes to `main` on its own schedule. **Always rebase on `origin/main` before pushing** to avoid conflicts with bot commits.
- Never touch files under `data/` manually — they're owned by the bots.

## Safe-to-edit vs hands-off
**Safe to edit freely:** `index.html`, `cars.html`, `hokynarstvi.html`, `AUTO_MONITOR.md`, CSS/styling on the HTML files.

**Hands-off unless explicitly asked:** `auto_monitor.py`, `auction_monitor.py`, `scrapers/`, `.github/workflows/`, anything in `data/`.

## Deploy
GitHub Pages serves `main` directly — no build step. Merge a PR → live within ~1 minute at kemroush.cz.
