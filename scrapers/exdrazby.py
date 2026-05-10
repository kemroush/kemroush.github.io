"""Scraper for ExDražby (exdrazby.cz).

The site is a heavy SPA: the static HTML is just a 1KB shell, and listings are
fetched via authenticated XHR after the JS bundle hydrates. The Symfony API at
https://exdrazby.cz/api/auction returns 500 without a route — there is no
obvious public listing endpoint.

TODO: either capture the actual XHR with browser dev tools (inspect Network
tab on the homepage to find the listing call), or add a Playwright/headless
fallback to render the SPA and scrape the rendered DOM.
"""
from __future__ import annotations

PORTAL_SLUG = "exdrazby"
PORTAL_LABEL = "ExDražby"


def scrape() -> list[dict]:
    return []
