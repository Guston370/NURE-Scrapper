"""
NURE Scraper - BigBasket
==========================
Scrapes product metadata and images from BigBasket.
Uses requests + BeautifulSoup with structured JSON-LD extraction.
"""

from __future__ import annotations

import json
import re
import time
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlencode, quote

from bs4 import BeautifulSoup
from loguru import logger

from nure.models import (
    Product, ProductMetadata, ProductInfo, NutritionInfo,
    ImageRecord, generate_product_id, make_folder_name
)
from nure.scrapers.base import BaseScraper


BB_BASE_URL     = "https://www.bigbasket.com"
BB_SEARCH_URL   = "https://www.bigbasket.com/ps/?q={query}"
BB_PRODUCT_URL  = "https://www.bigbasket.com/pd/{slug}/"


class BigBasketScraper(BaseScraper):
    """Scraper for BigBasket grocery platform."""

    source_name = "bigbasket"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "Referer": "https://www.bigbasket.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    # ──────────────────────────────────────────────
    # JSON-LD Extraction
    # ──────────────────────────────────────────────

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract structured data from JSON-LD script tags."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            return item
                elif data.get("@type") == "Product":
                    return data
            except Exception:
                continue
        return {}

    # ──────────────────────────────────────────────
    # Product Page Parser
    # ──────────────────────────────────────────────

    def _parse_product_page(self, soup: BeautifulSoup, url: str) -> Optional[Product]:
        """Parse a BigBasket product detail page."""
        try:
            ld = self._extract_json_ld(soup)

            # Product Name
            name = (
                ld.get("name")
                or (soup.find("h1", {"class": re.compile(r"product.*name|name.*product", re.I)}) or {}).get_text(strip=True)
                or (soup.find("h1") or {}).get_text(strip=True)
                or ""
            )

            # Brand
            brand = (
                (ld.get("brand") or {}).get("name", "")
                if isinstance(ld.get("brand"), dict)
                else ld.get("brand", "")
            )
            if not brand:
                brand_tag = soup.find("a", {"class": re.compile(r"brand", re.I)})
                brand = brand_tag.get_text(strip=True) if brand_tag else ""

            if not name:
                return None

            # Weight/Quantity
            weight = ""
            weight_tag = soup.find(attrs={"class": re.compile(r"weight|quantity|size", re.I)})
            if weight_tag:
                weight = weight_tag.get_text(strip=True)

            # Barcode/SKU
            barcode = ld.get("sku") or ld.get("productID") or None
            if barcode and not re.match(r"^\d{8,14}$", str(barcode)):
                barcode = None

            # Category
            category = ""
            breadcrumb = soup.find("ol", {"class": re.compile(r"breadcrumb", re.I)})
            if breadcrumb:
                crumbs = [li.get_text(strip=True) for li in breadcrumb.find_all("li")]
                if len(crumbs) > 1:
                    category = crumbs[1]
                if len(crumbs) > 2:
                    subcategory = crumbs[2]
                else:
                    subcategory = ""
            else:
                subcategory = ""

            # Images
            images = []
            product_id = generate_product_id(brand, name, weight)

            # From JSON-LD
            ld_images = ld.get("image", [])
            if isinstance(ld_images, str):
                ld_images = [ld_images]
            for i, img_url in enumerate(ld_images):
                if img_url:
                    images.append(ImageRecord(
                        filename=f"{product_id}_ld_{i:03d}.jpg",
                        url=img_url,
                    ))

            # From img tags in product gallery
            gallery = soup.find("div", {"class": re.compile(r"image.*slider|product.*image|gallery", re.I)})
            if gallery:
                for i, img_tag in enumerate(gallery.find_all("img")):
                    src = img_tag.get("src") or img_tag.get("data-src") or ""
                    if src and src.startswith("http") and not any(im.url == src for im in images):
                        images.append(ImageRecord(
                            filename=f"{product_id}_gallery_{i:03d}.jpg",
                            url=src,
                        ))

            # Description
            desc_tag = soup.find("div", {"class": re.compile(r"product.*desc|description", re.I)})
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Ingredients
            ingredients = []
            ingr_section = soup.find(
                lambda tag: tag.name in ["div", "section"] and
                "ingredient" in tag.get_text(strip=True).lower()[:50]
            )
            if ingr_section:
                ingr_text = ingr_section.get_text(separator=",")
                parts = re.split(r"[,;]", ingr_text)
                ingredients = [p.strip() for p in parts if p.strip() and len(p.strip()) < 60]

            # Price
            price = (ld.get("offers") or {}).get("price") if isinstance(ld.get("offers"), dict) else None

            # Rating
            rating_val = None
            review_count = None
            agg_rating = ld.get("aggregateRating")
            if agg_rating:
                rating_val = float(agg_rating.get("ratingValue", 0) or 0)
                review_count = int(agg_rating.get("reviewCount", 0) or 0)

            folder_name = make_folder_name(name, brand, weight)

            metadata = ProductMetadata(
                product_id=product_id,
                product_name=name,
                brand=brand,
                barcode=barcode,
                category=category,
                subcategory=subcategory,
                weight=weight,
                source=self.source_name,
                product_url=url,
                image_count=len(images),
                folder_name=folder_name,
                scraping_status="success",
            )

            info = ProductInfo(
                ingredients=ingredients,
                description=description,
                rating=rating_val,
                review_count=review_count,
            )

            return Product(metadata=metadata, info=info, images=images)

        except Exception as e:
            logger.error(f"[BigBasket] Parse error for {url}: {e}")
            return None

    # ──────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────

    def search_products(
        self,
        query: str,
        category: str = "",
        max_results: int = 50,
    ) -> List[Product]:
        """Search BigBasket for products."""
        url = BB_SEARCH_URL.format(query=quote(query))
        resp = self.get_with_retry(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        products = []

        # Try to find product cards
        # BigBasket has several layouts - try multiple selectors
        product_cards = (
            soup.find_all("a", {"class": re.compile(r"product.*link|item.*link", re.I)})
            or soup.find_all("div", {"class": re.compile(r"product.*item|item.*product", re.I)})
        )

        product_urls = set()
        for card in product_cards:
            href = card.get("href", "")
            if "/pd/" in href:
                full_url = urljoin(BB_BASE_URL, href)
                product_urls.add(full_url)

        logger.info(f"[BigBasket] Found {len(product_urls)} product URLs for '{query}'")

        for purl in list(product_urls)[:max_results]:
            product = self.get_product_details(purl)
            if product:
                products.append(product)

        return products

    def get_product_details(self, product_url: str) -> Optional[Product]:
        """Scrape a single BigBasket product page."""
        resp = self.get_with_retry(product_url)
        if not resp:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        return self._parse_product_page(soup, product_url)
