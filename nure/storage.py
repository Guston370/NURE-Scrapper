"""
NURE Dataset Storage Engine
=============================
Handles writing product data to disk in the correct structure:

dataset/
├── products/
│   └── {FolderName}/
│       ├── images/
│       ├── metadata.json
│       └── product_info.json
├── products.csv
├── products.json
└── firestore_export/
    └── firestore_products.json

Also maintains an in-memory product registry for resume capability.
"""

from __future__ import annotations

import json
import csv
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from loguru import logger

from nure.config import (
    PRODUCTS_DIR, DATASET_ROOT, FIRESTORE_DIR
)
from nure.models import Product, FailedProduct


# ──────────────────────────────────────────────────────────────────────────────
# Registry file for resume capability
# ──────────────────────────────────────────────────────────────────────────────

REGISTRY_FILE  = DATASET_ROOT / ".product_registry.pkl"
FAILED_LOG     = DATASET_ROOT / "failed_products.csv"


class DatasetStorage:
    """Manages dataset I/O with resume capability."""

    def __init__(self):
        self._registry: Dict[str, str] = {}   # product_id → folder_name
        self._scraped_urls: Set[str] = set()   # deduplicate by URL
        self._failed: List[FailedProduct] = []
        self._load_registry()

    # ──────────────────────────────────────────────
    # Registry (Resume)
    # ──────────────────────────────────────────────

    def _load_registry(self):
        """Load persisted registry from disk."""
        if REGISTRY_FILE.exists():
            try:
                with open(REGISTRY_FILE, "rb") as f:
                    data = pickle.load(f)
                    self._registry = data.get("registry", {})
                    self._scraped_urls = data.get("scraped_urls", set())
                logger.info(f"Loaded registry: {len(self._registry)} products already processed")
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}")

    def _save_registry(self):
        """Persist registry to disk."""
        try:
            with open(REGISTRY_FILE, "wb") as f:
                pickle.dump({
                    "registry": self._registry,
                    "scraped_urls": self._scraped_urls,
                }, f)
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")

    def is_already_scraped(self, product_id: str = "", url: str = "") -> bool:
        """Check if a product has already been saved (for resume)."""
        if product_id and product_id in self._registry:
            return True
        if url and url in self._scraped_urls:
            return True
        return False

    # ──────────────────────────────────────────────
    # Product Save
    # ──────────────────────────────────────────────

    def save_product(self, product: Product) -> Path:
        """
        Save a product to disk:
        - Creates the product folder
        - Writes metadata.json
        - Writes product_info.json
        - Returns the product folder path
        """
        folder_name = product.metadata.folder_name or product.metadata.product_id
        product_dir = PRODUCTS_DIR / folder_name
        product_dir.mkdir(parents=True, exist_ok=True)

        # Images sub-folder
        (product_dir / "images").mkdir(exist_ok=True)

        # metadata.json
        meta_path = product_dir / "metadata.json"
        meta_dict = product.metadata.model_dump()
        meta_path.write_text(
            json.dumps(meta_dict, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # product_info.json
        info_path = product_dir / "product_info.json"
        info_dict = product.info.model_dump(exclude_none=True)
        info_path.write_text(
            json.dumps(info_dict, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # Register
        self._registry[product.metadata.product_id] = folder_name
        if product.metadata.product_url:
            self._scraped_urls.add(product.metadata.product_url)
        self._save_registry()

        logger.debug(f"Saved product: {folder_name}")
        return product_dir

    # ──────────────────────────────────────────────
    # Failed Products
    # ──────────────────────────────────────────────

    def record_failure(self, failure: FailedProduct):
        """Record a failed product for the failed_products.csv report."""
        self._failed.append(failure)

    def flush_failures(self):
        """Write all failures to failed_products.csv."""
        if not self._failed:
            return

        file_exists = FAILED_LOG.exists()
        with open(FAILED_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "product_name", "brand", "source", "product_url",
                "error_message", "timestamp", "retry_count"
            ])
            if not file_exists:
                writer.writeheader()
            for failure in self._failed:
                writer.writerow(failure.model_dump())

        self._failed.clear()

    # ──────────────────────────────────────────────
    # Bulk Exports
    # ──────────────────────────────────────────────

    def load_all_products(self) -> List[Product]:
        """
        Read all saved products from disk.
        Reconstructs Product objects from metadata.json + product_info.json.
        """
        from nure.models import ProductMetadata, ProductInfo

        products = []
        for product_dir in PRODUCTS_DIR.iterdir():
            if not product_dir.is_dir():
                continue

            meta_file = product_dir / "metadata.json"
            info_file = product_dir / "product_info.json"

            if not meta_file.exists():
                continue

            try:
                meta = ProductMetadata(**json.loads(meta_file.read_text(encoding="utf-8")))
                info = ProductInfo(**json.loads(info_file.read_text(encoding="utf-8"))) if info_file.exists() else ProductInfo()

                # Count images on disk
                images_dir = product_dir / "images"
                image_files = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")) + list(images_dir.glob("*.webp"))
                meta.image_count = len(image_files)

                products.append(Product(metadata=meta, info=info))
            except Exception as e:
                logger.warning(f"Failed to load product from {product_dir}: {e}")

        logger.info(f"Loaded {len(products)} products from disk")
        return products

    def export_products_csv(self, products: List[Product]) -> Path:
        """Export master products.csv."""
        csv_path = DATASET_ROOT / "products.csv"
        if not products:
            return csv_path

        fieldnames = list(products[0].to_csv_row().keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for p in products:
                writer.writerow(p.to_csv_row())

        logger.info(f"Exported {len(products)} products to {csv_path}")
        return csv_path

    def export_products_json(self, products: List[Product]) -> Path:
        """Export master products.json."""
        json_path = DATASET_ROOT / "products.json"
        data = [
            {
                **p.metadata.model_dump(),
                **p.info.model_dump(exclude_none=True),
                "image_paths": [
                    str(PRODUCTS_DIR / p.metadata.folder_name / "images" / img.filename)
                    for img in p.images if img.is_valid
                ] if p.images else [],
            }
            for p in products
        ]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(products)} products to {json_path}")
        return json_path

    def export_firestore_json(self, products: List[Product]) -> Path:
        """Export Firestore-ready import JSON."""
        firestore_path = FIRESTORE_DIR / "firestore_products.json"
        FIRESTORE_DIR.mkdir(parents=True, exist_ok=True)

        documents = {}
        for p in products:
            doc_id = p.metadata.barcode or p.metadata.product_id
            documents[doc_id] = p.to_firestore_doc()

        export = {
            "__collections__": {
                "products": {
                    doc_id: {"__data__": doc}
                    for doc_id, doc in documents.items()
                }
            }
        }

        with open(firestore_path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)

        logger.info(f"Firestore export: {len(documents)} documents → {firestore_path}")
        return firestore_path

    @property
    def scraped_count(self) -> int:
        return len(self._registry)
