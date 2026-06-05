"""
NURE Scraper - Blinkit (formerly Grofers)
==========================================
Scrapes product data from Blinkit using their internal API.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Dict, Any
from urllib.parse import quote

from bs4 import BeautifulSoup
from loguru import logger

from nure.models import (
    Product, ProductMetadata, ProductInfo, NutritionInfo,
    ImageRecord, generate_product_id, make_folder_name
)
from nure.scrapers.base import BaseScraper


BLINKIT_BASE    = "https://blinkit.com"
BLINKIT_SEARCH  = "https://blinkit.com/s/?q={query}"


class BlinkitScraper(BaseScraper):
    """Scraper for Blinkit (quick grocery delivery)."""

    source_name = "blinkit"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "Referer": "https://blinkit.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        })

    def _extract_next_data(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract __NEXT_DATA__ JSON from Next.js pages."""
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                return json.loads(script.string)
            except Exception:
                pass
        return {}

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(tag.string or "{}")
                if isinstance(d, list):
                    for item in d:
                        if item.get("@type") == "Product":
                            return item
                elif d.get("@type") == "Product":
                    return d
            except Exception:
                pass
        return {}

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> Optional[Product]:
        """Parse Blinkit product page using JSON-LD and Next.js data."""
        try:
            ld = self._extract_json_ld(soup)
            next_data = self._extract_next_data(soup)

            name = ""
            brand = ""
            weight = ""
            barcode = None
            images = []
            description = ""
            ingredients = []
            category = ""

            # Try Next.js page props
            try:
                page_props = next_data.get("props", {}).get("pageProps", {})
                product_data = page_props.get("product") or page_props.get("productData") or {}
                if product_data:
                    name = product_data.get("name", "")
                    brand = product_data.get("brand", "")
                    weight = product_data.get("quantity", "") or product_data.get("unit_quantity", "")
                    description = product_data.get("description", "")
                    barcode = product_data.get("ean") or product_data.get("barcode")
                    category = product_data.get("category", "")

                    for img_url in product_data.get("images", []):
                        product_id_temp = generate_product_id(brand, name, weight)
                        images.append(ImageRecord(
                            filename=f"{product_id_temp}_blinkit.jpg",
                            url=img_url if isinstance(img_url, str) else img_url.get("url", ""),
                        ))
            except Exception:
                pass

            # Fallback: JSON-LD
            if not name:
                name = ld.get("name", "")
            if not brand:
                b = ld.get("brand", {})
                brand = b.get("name", "") if isinstance(b, dict) else str(b)

            if not name:
                h1 = soup.find("h1")
                name = h1.get_text(strip=True) if h1 else ""

            if not name:
                return None

            product_id  = generate_product_id(brand, name, weight)
            folder_name = make_folder_name(name, brand, weight)

            # JSON-LD images fallback
            if not images:
                ld_imgs = ld.get("image", [])
                if isinstance(ld_imgs, str):
                    ld_imgs = [ld_imgs]
                for i, img_url in enumerate(ld_imgs):
                    if img_url:
                        images.append(ImageRecord(
                            filename=f"{product_id}_ld_{i:03d}.jpg",
                            url=img_url,
                        ))

            metadata = ProductMetadata(
                product_id=product_id,
                product_name=name,
                brand=brand,
                barcode=barcode,
                category=category,
                weight=weight,
                source=self.source_name,
                product_url=url,
                image_count=len(images),
                folder_name=folder_name,
                scraping_status="success",
            )

            rating_val = None
            review_count = None
            agg = ld.get("aggregateRating", {})
            if agg:
                rating_val = float(agg.get("ratingValue", 0) or 0)
                review_count = int(agg.get("reviewCount", 0) or 0)

            info = ProductInfo(
                ingredients=ingredients,
                description=description,
                rating=rating_val,
                review_count=review_count,
            )

            return Product(metadata=metadata, info=info, images=images)

        except Exception as e:
            logger.error(f"[Blinkit] Parse error for {url}: {e}")
            return None

    def search_products(
        self,
        query: str,
        category: str = "",
        max_results: int = 50,
    ) -> List[Product]:
        url = BLINKIT_SEARCH.format(query=quote(query))
        resp = self.get_with_retry(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        products = []

        # Find product links
        product_links = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/prn/" in href or "/pn/" in href:
                full = href if href.startswith("http") else BLINKIT_BASE + href
                product_links.add(full)

        logger.info(f"[Blinkit] Found {len(product_links)} product URLs for '{query}'")

        for link in list(product_links)[:max_results]:
            p = self.get_product_details(link)
            if p:
                products.append(p)

        return products

    def get_product_details(self, product_url: str) -> Optional[Product]:
        resp = self.get_with_retry(product_url)
        if not resp:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse_product_page(soup, product_url)
