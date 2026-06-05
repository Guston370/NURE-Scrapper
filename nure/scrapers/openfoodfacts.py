"""
NURE Scraper - Open Food Facts
================================
Uses the Open Food Facts API (free, no auth required).
Ideal for Indian products with barcode, nutrition, and ingredient data.

API Docs: https://wiki.openfoodfacts.org/API
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from nure.models import (
    Product, ProductMetadata, ProductInfo, NutritionInfo,
    ImageRecord, generate_product_id, make_folder_name
)
from nure.config import OFF_API_URL, OFF_APP_NAME, OFF_APP_VERSION
from nure.scrapers.base import BaseScraper


# ──────────────────────────────────────────────────────────────────────────────

OFF_PRODUCT_URL = "https://world.openfoodfacts.org/product/{barcode}"
OFF_SEARCH_URL  = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_INDIA_URL   = "https://world.openfoodfacts.org/country/india"
OFF_PRODUCT_API = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_SEARCH_API  = "https://world.openfoodfacts.org/api/v2/search"


class OpenFoodFactsScraper(BaseScraper):
    """Scraper for Open Food Facts - primary data source."""

    source_name = "openfoodfacts"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": f"{OFF_APP_NAME}/{OFF_APP_VERSION}",
        })

    # ──────────────────────────────────────────────
    # Parsing Helpers
    # ──────────────────────────────────────────────

    def _parse_nutrition(self, nutriments: Dict[str, Any]) -> NutritionInfo:
        """Extract structured nutrition from OFF nutriments dict."""
        def get_val(key):
            return nutriments.get(f"{key}_100g") or nutriments.get(key)

        return NutritionInfo(
            serving_size=nutriments.get("serving_size"),
            energy_kcal=get_val("energy-kcal"),
            protein_g=get_val("proteins"),
            carbohydrates_g=get_val("carbohydrates"),
            of_which_sugars_g=get_val("sugars"),
            fat_g=get_val("fat"),
            of_which_saturated_fat_g=get_val("saturated-fat"),
            dietary_fiber_g=get_val("fiber"),
            sodium_mg=get_val("sodium"),
            additional_nutrients={
                k: v for k, v in nutriments.items()
                if k not in {
                    "energy-kcal_100g", "proteins_100g", "carbohydrates_100g",
                    "sugars_100g", "fat_100g", "saturated-fat_100g",
                    "fiber_100g", "sodium_100g", "serving_size"
                }
            },
        )

    def _parse_ingredients(self, product_data: Dict) -> List[str]:
        """Extract ingredient list."""
        raw = product_data.get("ingredients_text_en") or product_data.get("ingredients_text", "")
        if not raw:
            return []
        # Clean and split
        raw = re.sub(r"\(.*?\)", "", raw)  # Remove sub-ingredients
        parts = re.split(r"[,;]", raw)
        return [p.strip() for p in parts if p.strip()]

    def _parse_product(self, data: Dict) -> Optional[Product]:
        """Convert an OFF product dict into a Product model."""
        try:
            name = (
                data.get("product_name_en")
                or data.get("product_name")
                or data.get("product_name_hi")
                or ""
            ).strip()
            brand = (data.get("brands") or "").split(",")[0].strip()

            if not name or not brand:
                return None

            barcode = data.get("code") or data.get("_id") or None
            weight  = data.get("quantity") or data.get("net_weight") or ""

            product_id  = generate_product_id(brand, name, weight)
            folder_name = make_folder_name(name, brand, weight)

            # Images
            images = []
            image_fields = [
                ("front", data.get("image_front_url")),
                ("front_small", data.get("image_front_small_url")),
                ("ingredients", data.get("image_ingredients_url")),
                ("nutrition", data.get("image_nutrition_url")),
                ("packaging", data.get("image_packaging_url")),
            ]
            for view_type, url in image_fields:
                if url:
                    images.append(ImageRecord(
                        filename=f"{product_id}_{view_type}.jpg",
                        url=url,
                        view_type=view_type,
                    ))

            # Additional image URLs from selected_images
            sel = data.get("selected_images", {})
            for field_name, field_data in sel.items():
                for size, url in (field_data.get("display") or {}).items():
                    if url and not any(img.url == url for img in images):
                        images.append(ImageRecord(
                            filename=f"{product_id}_{field_name}_{size}.jpg",
                            url=url,
                            view_type=field_name,
                        ))

            metadata = ProductMetadata(
                product_id=product_id,
                product_name=name,
                brand=brand,
                barcode=barcode,
                category=(data.get("categories_tags") or [""])[0].replace("en:", "").replace("-", " ").title() if data.get("categories_tags") else data.get("categories", ""),
                subcategory=(data.get("categories_tags") or ["", ""])[1].replace("en:", "").replace("-", " ").title() if len(data.get("categories_tags") or []) > 1 else "",
                weight=weight,
                manufacturer=data.get("manufacturing_places") or data.get("producer") or "",
                source=self.source_name,
                product_url=f"https://world.openfoodfacts.org/product/{barcode}" if barcode else data.get("url", ""),
                image_count=len(images),
                folder_name=folder_name,
                scraping_status="success",
            )

            info = ProductInfo(
                ingredients=self._parse_ingredients(data),
                nutrition=self._parse_nutrition(data.get("nutriments", {})),
                allergens=[
                    a.replace("en:", "").replace("-", " ").title()
                    for a in (data.get("allergens_tags") or [])
                ],
                description=data.get("generic_name_en") or data.get("generic_name") or "",
                country_of_origin=data.get("origins") or data.get("countries") or "",
                storage_information=data.get("conservation_conditions") or "",
                health_claims=data.get("labels", "").split(",") if data.get("labels") else [],
                additional_info={
                    "ecoscore_grade": data.get("ecoscore_grade"),
                    "nutriscore_grade": data.get("nutriscore_grade"),
                    "nova_group": data.get("nova_group"),
                    "packaging": data.get("packaging"),
                },
            )

            return Product(metadata=metadata, info=info, images=images)

        except Exception as e:
            logger.error(f"[OFF] Failed to parse product: {e}")
            return None

    # ──────────────────────────────────────────────
    # API Methods
    # ──────────────────────────────────────────────

    def get_products_by_barcode(self, barcode: str) -> Optional[Product]:
        """Look up a single product by barcode."""
        url = OFF_PRODUCT_API.format(barcode=barcode)
        resp = self.get_with_retry(url)
        if not resp:
            return None

        data = resp.json()
        if data.get("status") != 1:
            logger.warning(f"[OFF] Barcode not found: {barcode}")
            return None

        return self._parse_product(data.get("product", {}))

    def search_products(
        self,
        query: str,
        category: str = "",
        max_results: int = 50,
    ) -> List[Product]:
        """Search products by text query."""
        products = []
        page = 1
        page_size = min(50, max_results)

        while len(products) < max_results:
            params = {
                "search_terms": query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page": page,
                "page_size": page_size,
                "fields": (
                    "code,product_name,product_name_en,product_name_hi,"
                    "brands,quantity,categories_tags,categories,"
                    "ingredients_text_en,ingredients_text,"
                    "nutriments,allergens_tags,labels,"
                    "image_front_url,image_front_small_url,"
                    "image_ingredients_url,image_nutrition_url,"
                    "image_packaging_url,selected_images,"
                    "generic_name_en,generic_name,"
                    "origins,countries,manufacturing_places,"
                    "conservation_conditions,nutriscore_grade,"
                    "ecoscore_grade,nova_group,packaging,"
                    "url,_id"
                ),
            }

            if category:
                params["tagtype_0"] = "categories"
                params["tag_0"] = category

            resp = self.get_with_retry(OFF_SEARCH_URL, params=params)
            if not resp:
                break

            data = resp.json()
            raw_products = data.get("products", [])

            if not raw_products:
                logger.info(f"[OFF] No more results for '{query}' on page {page}")
                break

            for raw in raw_products:
                product = self._parse_product(raw)
                if product:
                    products.append(product)

            page += 1
            if len(raw_products) < page_size:
                break

        logger.info(f"[OFF] Found {len(products)} products for query: '{query}'")
        return products[:max_results]

    def search_indian_products(
        self,
        query: str,
        max_results: int = 50,
    ) -> List[Product]:
        """Search specifically for Indian products."""
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": min(50, max_results),
            "tagtype_0": "countries",
            "tag_0": "en:india",
            "fields": (
                "code,product_name,product_name_en,brands,quantity,"
                "categories_tags,ingredients_text_en,nutriments,"
                "allergens_tags,image_front_url,image_ingredients_url,"
                "image_nutrition_url,selected_images,origins,"
                "manufacturing_places,conservation_conditions,"
                "nutriscore_grade,nova_group,_id,url"
            ),
        }

        resp = self.get_with_retry(OFF_SEARCH_URL, params=params)
        if not resp:
            return []

        raw_products = resp.json().get("products", [])
        results = []
        for raw in raw_products:
            p = self._parse_product(raw)
            if p:
                results.append(p)

        logger.info(f"[OFF] Found {len(results)} Indian products for '{query}'")
        return results

    def get_product_details(self, product_url: str) -> Optional[Product]:
        """Parse a product URL to extract barcode and fetch details."""
        # Extract barcode from URL
        match = re.search(r"/product/(\d+)", product_url)
        if not match:
            return None
        return self.get_products_by_barcode(match.group(1))

    def scrape_by_category_tag(
        self,
        category_tag: str,
        country_tag: str = "en:india",
        max_results: int = 100,
    ) -> List[Product]:
        """Scrape all products for a given OFF category tag."""
        products = []
        page = 1

        while len(products) < max_results:
            url = f"https://world.openfoodfacts.org/category/{category_tag}/country/{country_tag.replace('en:', '')}.json"
            params = {"page": page}
            resp = self.get_with_retry(url, params=params)
            if not resp:
                break

            data = resp.json()
            raw = data.get("products", [])
            if not raw:
                break

            for item in raw:
                p = self._parse_product(item)
                if p:
                    products.append(p)

            page += 1
            if len(raw) < 20:
                break

        logger.info(f"[OFF] Category '{category_tag}': {len(products)} products scraped")
        return products[:max_results]
