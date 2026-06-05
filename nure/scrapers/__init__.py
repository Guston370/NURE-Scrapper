"""
NURE Scraper Registry
======================
Central registry mapping source names to scraper classes.
Add new scrapers here to integrate them into the pipeline.
"""

from __future__ import annotations

from typing import Dict, Type

from nure.scrapers.base import BaseScraper
from nure.scrapers.openfoodfacts import OpenFoodFactsScraper
from nure.scrapers.bigbasket import BigBasketScraper
from nure.scrapers.blinkit import BlinkitScraper
from nure.scrapers.jiomart import JioMartScraper


# Registry mapping source name → scraper class
SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {
    "openfoodfacts": OpenFoodFactsScraper,
    "bigbasket":     BigBasketScraper,
    "blinkit":       BlinkitScraper,
    "jiomart":       JioMartScraper,
    # Future scrapers can be added here:
    # "instamart":   InstamartScraper,
    # "amazon_india": AmazonIndiaScraper,
    # "flipkart":    FlipkartScraper,
}


def get_scraper(source: str) -> BaseScraper:
    """Instantiate and return a scraper for the given source name."""
    cls = SCRAPER_REGISTRY.get(source)
    if cls is None:
        raise ValueError(
            f"Unknown scraper source: '{source}'. "
            f"Available: {list(SCRAPER_REGISTRY.keys())}"
        )
    return cls()


def list_sources() -> list:
    """Return list of available source names."""
    return list(SCRAPER_REGISTRY.keys())
