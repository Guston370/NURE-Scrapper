"""
NURE Scraper - JioMart
========================
Scrapes Indian grocery products from JioMart.
Uses requests + BeautifulSoup + JSON-LD extraction.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

from bs4 import BeautifulSoup
from loguru import logger

from nure.models import (
    Product, ProductMetadata, ProductInfo, NutritionInfo,
    ImageRecord, generate_product_id, make_folder_name
)
from nure.scrapers.base import BaseScraper


JIOMART_BASE   = "https://www.jiomart.com"
JIOMART_SEARCH = "https://www.jiomart.com/search/{query}"


class JioMartScraper(BaseScraper):
    """Scraper for JioMart."""

    source_name = "jiomart"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "Referer": "https://www.jiomart.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        })

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
        try:
            ld = self._extract_json_ld(soup)

            name = ld.get("name", "").strip()
            if not name:
                h1 = soup.find("h1")
                name = h1.get_text(strip=True) if h1 else ""

            brand_raw = ld.get("brand", {})
            brand = brand_raw.get("name", "") if isinstance(brand_raw, dict) else str(brand_raw)
            if not brand:
                b_tag = soup.find("span", {"class": re.compile(r"brand", re.I)})
                brand = b_tag.get_text(strip=True) if b_tag else ""

            if not name:
                return None

            # Weight
            weight = ld.get("weight", "") or ""
            qty_tag = soup.find(attrs={"class": re.compile(r"qty|quantity|weight|size", re.I)})
            if not weight and qty_tag:
                weight = qty_tag.get_text(strip=True)

            # Barcode/SKU
            barcode = ld.get("sku") or ld.get("gtin13") or ld.get("gtin") or None

            # Category from breadcrumbs
            category = ""
            subcategory = ""
            breadcrumb = soup.find(attrs={"class": re.compile(r"breadcrumb", re.I)})
            if breadcrumb:
                crumbs = [li.get_text(strip=True) for li in breadcrumb.find_all("li")]
                if len(crumbs) > 1:
                    category = crumbs[1]
                if len(crumbs) > 2:
                    subcategory = crumbs[2]

            product_id  = generate_product_id(brand, name, weight)
            folder_name = make_folder_name(name, brand, weight)

            # Images
            images = []
            ld_imgs = ld.get("image", [])
            if isinstance(ld_imgs, str):
                ld_imgs = [ld_imgs]
            for i, img_url in enumerate(ld_imgs):
                images.append(ImageRecord(
                    filename=f"{product_id}_ld_{i:03d}.jpg",
                    url=img_url,
                ))

            # Gallery images
            for i, img in enumerate(soup.find_all("img", {"class": re.compile(r"product.*img|img.*product", re.I)})):
                src = img.get("src") or img.get("data-src") or ""
                if src.startswith("http") and src not in [im.url for im in images]:
                    images.append(ImageRecord(
                        filename=f"{product_id}_gallery_{i:03d}.jpg",
                        url=src,
                    ))

            # Description
            desc_tag = soup.find(attrs={"class": re.compile(r"desc|description|about", re.I)})
            description = desc_tag.get_text(strip=True)[:1000] if desc_tag else ""

            # Rating
            rating_val = None
            review_count = None
            agg = ld.get("aggregateRating", {})
            if agg:
                rating_val = float(agg.get("ratingValue", 0) or 0)
                review_count = int(agg.get("reviewCount", 0) or 0)

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
                description=description,
                rating=rating_val,
                review_count=review_count,
            )

            return Product(metadata=metadata, info=info, images=images)

        except Exception as e:
            logger.error(f"[JioMart] Parse error for {url}: {e}")
            return None

    def search_products(
        self,
        query: str,
        category: str = "",
        max_results: int = 50,
    ) -> List[Product]:
        url = JIOMART_SEARCH.format(query=quote(query))
        resp = self.get_with_retry(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        products = []

        product_links = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/p/" in href and JIOMART_BASE in href:
                product_links.add(href)
            elif "/p/" in href and href.startswith("/"):
                product_links.add(JIOMART_BASE + href)

        logger.info(f"[JioMart] Found {len(product_links)} product URLs for '{query}'")

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
