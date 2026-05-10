"""Auction scrapers — one module per portal.

Each scraper module exposes:
  PORTAL_SLUG  — short stable identifier (e.g. "okdrazby")
  PORTAL_LABEL — human-readable name (e.g. "OK Dražby")
  scrape() -> list[dict]  — returns standardized auction records

A standardized record has these fields (see scrapers.common.RECORD_FIELDS):
  id, portal, portal_label, category, status, title, location,
  min_bid_czk, min_bid_text, start_date, start_time, image, link, badges
"""

from . import okdrazby, portaldrazeb, exdrazby, drazby_exekutori

ALL = [okdrazby, portaldrazeb, exdrazby, drazby_exekutori]
