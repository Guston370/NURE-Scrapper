"""
NURE Scraper - Base Class
==========================
All source scrapers inherit from BaseScraper.
Provides retry logic, rate limiting, session management,
and a common interface.
"""

from __future__ import annotations

import abc
import time
import random
from typing import List, Optional

import requests
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from nure.config import (
    DEFAULT_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, REQUEST_DELAY
)
from nure.models import Product, ScrapingTask


class BaseScraper(abc.ABC):
    """Abstract base class for all source scrapers."""

    source_name: str = "base"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._last_request_time: float = 0.0

    # ──────────────────────────────────────────────
    # Rate Limiting
    # ──────────────────────────────────────────────

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        delay = REQUEST_DELAY + random.uniform(0.5, 1.5)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    # ──────────────────────────────────────────────
    # HTTP Helpers
    # ──────────────────────────────────────────────

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET with rate limiting and error handling."""
        self._rate_limit()
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"[{self.source_name}] GET failed for {url}: {e}")
            return None

    def get_with_retry(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET with exponential backoff retry."""
        for attempt in range(MAX_RETRIES):
            self._rate_limit()
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                wait = 2 ** attempt
                logger.warning(
                    f"[{self.source_name}] Attempt {attempt + 1}/{MAX_RETRIES} failed for {url}: {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
        logger.error(f"[{self.source_name}] All retries exhausted for: {url}")
        return None

    # ──────────────────────────────────────────────
    # Abstract Interface
    # ──────────────────────────────────────────────

    @abc.abstractmethod
    def search_products(self, query: str, category: str = "", max_results: int = 50) -> List[Product]:
        """Search for products by query string."""
        ...

    @abc.abstractmethod
    def get_product_details(self, product_url: str) -> Optional[Product]:
        """Scrape full product details from a product page URL."""
        ...

    def get_products_by_barcode(self, barcode: str) -> Optional[Product]:
        """Look up product by barcode. Override in subclasses that support it."""
        return None

    def scrape_category(self, category_url: str, max_pages: int = 5) -> List[Product]:
        """Scrape all products in a category. Override in subclasses."""
        return []

    # ──────────────────────────────────────────────
    # Source Name
    # ──────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source={self.source_name}>"
