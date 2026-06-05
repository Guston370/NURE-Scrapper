"""
NURE Food Product Dataset Generator
====================================
Core data models and schema definitions using Pydantic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
import re


def make_folder_name(product_name: str, brand: str, weight: str = "") -> str:
    """Generate an ML-friendly folder name for a product."""
    parts = []
    if brand:
        parts.append(brand)
    parts.append(product_name)
    if weight:
        parts.append(weight)

    combined = "_".join(parts)
    # Replace non-alphanumeric (except underscore) with underscore
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", combined)
    # Collapse multiple underscores
    cleaned = re.sub(r"_+", "_", cleaned)
    # Strip leading/trailing underscores
    cleaned = cleaned.strip("_")
    # Limit length
    return cleaned[:120]


def generate_product_id(brand: str, name: str, weight: str = "") -> str:
    """Generate a deterministic product ID from brand + name + weight."""
    raw = f"{brand.lower()}_{name.lower()}_{weight.lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ──────────────────────────────────────────────────────────────────────────────
# Nutrition Model
# ──────────────────────────────────────────────────────────────────────────────

class NutritionInfo(BaseModel):
    serving_size: Optional[str] = None
    energy_kcal: Optional[float] = None
    protein_g: Optional[float] = None
    carbohydrates_g: Optional[float] = None
    of_which_sugars_g: Optional[float] = None
    fat_g: Optional[float] = None
    of_which_saturated_fat_g: Optional[float] = None
    dietary_fiber_g: Optional[float] = None
    sodium_mg: Optional[float] = None
    additional_nutrients: Optional[Dict[str, Any]] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Image Record
# ──────────────────────────────────────────────────────────────────────────────

class ImageRecord(BaseModel):
    filename: str
    url: str
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    perceptual_hash: Optional[str] = None
    blur_score: Optional[float] = None
    quality_score: Optional[float] = None
    is_valid: bool = True
    rejection_reason: Optional[str] = None
    view_type: Optional[str] = None  # front, back, side, angle, shelf


# ──────────────────────────────────────────────────────────────────────────────
# Product Metadata (metadata.json)
# ──────────────────────────────────────────────────────────────────────────────

class ProductMetadata(BaseModel):
    product_id: str
    product_name: str
    brand: str
    barcode: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    weight: Optional[str] = None
    manufacturer: Optional[str] = None
    source: str
    product_url: Optional[str] = None
    image_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    folder_name: Optional[str] = None
    scraping_status: str = "pending"  # pending | success | partial | failed


# ──────────────────────────────────────────────────────────────────────────────
# Product Info (product_info.json)
# ──────────────────────────────────────────────────────────────────────────────

class ProductInfo(BaseModel):
    ingredients: List[str] = Field(default_factory=list)
    nutrition: NutritionInfo = Field(default_factory=NutritionInfo)
    allergens: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    country_of_origin: Optional[str] = None
    storage_information: Optional[str] = None
    fssai_information: Optional[str] = None
    health_claims: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    additional_info: Optional[Dict[str, Any]] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Full Product Record (in-memory)
# ──────────────────────────────────────────────────────────────────────────────

class Product(BaseModel):
    metadata: ProductMetadata
    info: ProductInfo = Field(default_factory=ProductInfo)
    images: List[ImageRecord] = Field(default_factory=list)

    @property
    def has_barcode(self) -> bool:
        return bool(self.metadata.barcode)

    @property
    def has_nutrition(self) -> bool:
        n = self.info.nutrition
        return any([
            n.energy_kcal, n.protein_g, n.carbohydrates_g, n.fat_g
        ])

    @property
    def has_ingredients(self) -> bool:
        return len(self.info.ingredients) > 0

    @property
    def valid_image_count(self) -> int:
        return sum(1 for img in self.images if img.is_valid)

    def to_firestore_doc(self) -> Dict[str, Any]:
        """Convert to Firestore-ready document."""
        return {
            "product_name": self.metadata.product_name,
            "brand": self.metadata.brand,
            "barcode": self.metadata.barcode or "",
            "category": self.metadata.category or "",
            "subcategory": self.metadata.subcategory or "",
            "weight": self.metadata.weight or "",
            "manufacturer": self.metadata.manufacturer or "",
            "source": self.metadata.source,
            "product_url": self.metadata.product_url or "",
            "ingredients": self.info.ingredients,
            "nutrition": self.info.nutrition.model_dump(exclude_none=True),
            "allergens": self.info.allergens,
            "description": self.info.description or "",
            "country_of_origin": self.info.country_of_origin or "",
            "storage_information": self.info.storage_information or "",
            "fssai_information": self.info.fssai_information or "",
            "health_claims": self.info.health_claims,
            "image_urls": [img.url for img in self.images if img.is_valid],
            "image_count": self.valid_image_count,
            "product_id": self.metadata.product_id,
            "created_at": self.metadata.created_at,
        }

    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to a flat dict suitable for CSV export."""
        return {
            "product_id": self.metadata.product_id,
            "product_name": self.metadata.product_name,
            "brand": self.metadata.brand,
            "barcode": self.metadata.barcode or "",
            "category": self.metadata.category or "",
            "subcategory": self.metadata.subcategory or "",
            "weight": self.metadata.weight or "",
            "manufacturer": self.metadata.manufacturer or "",
            "source": self.metadata.source,
            "product_url": self.metadata.product_url or "",
            "image_count": self.valid_image_count,
            "has_barcode": self.has_barcode,
            "has_nutrition": self.has_nutrition,
            "has_ingredients": self.has_ingredients,
            "country_of_origin": self.info.country_of_origin or "",
            "fssai_information": self.info.fssai_information or "",
            "scraping_status": self.metadata.scraping_status,
            "folder_name": self.metadata.folder_name or "",
            "dataset_path": f"dataset/products/{self.metadata.folder_name}" if self.metadata.folder_name else "",
        }


# ──────────────────────────────────────────────────────────────────────────────
# Scraping Task
# ──────────────────────────────────────────────────────────────────────────────

class ScrapingTask(BaseModel):
    source: str
    query: Optional[str] = None
    category: Optional[str] = None
    barcode: Optional[str] = None
    product_url: Optional[str] = None
    priority: int = 5  # 1 = highest
    retries: int = 0
    max_retries: int = 3
    status: str = "pending"  # pending | running | done | failed | skipped
    error_message: Optional[str] = None
    product_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Failed Product Record
# ──────────────────────────────────────────────────────────────────────────────

class FailedProduct(BaseModel):
    product_name: Optional[str] = None
    brand: Optional[str] = None
    source: Optional[str] = None
    product_url: Optional[str] = None
    error_message: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    retry_count: int = 0
