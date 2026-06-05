"""
NURE Dataset Reporter
======================
Generates all required audit, inventory, and analysis reports.

Reports generated:
  - dataset_report.json
  - brand_summary.csv
  - category_summary.csv
  - barcode_coverage.csv
  - nutrition_coverage.csv
  - ingredients_coverage.csv
  - missing_barcodes.csv
  - missing_nutrition.csv
  - missing_ingredients.csv
  - image_quality_report.csv
  - duplicate_images_report.csv
  - training_readiness_report.json
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from nure.config import REPORTS_DIR, MIN_IMAGES_PER_PRODUCT
from nure.models import Product


class DatasetReporter:
    """Generates all audit and analysis reports for the NURE dataset."""

    def __init__(self, reports_dir: Path = REPORTS_DIR):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────

    def _write_csv(self, filename: str, rows: List[Dict], fieldnames: List[str]):
        path = self.reports_dir / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Report written: {filename} ({len(rows)} rows)")
        return path

    def _write_json(self, filename: str, data: Any):
        path = self.reports_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Report written: {filename}")
        return path

    # ──────────────────────────────────────────────
    # Core Stats
    # ──────────────────────────────────────────────

    def _compute_stats(self, products: List[Product]) -> Dict[str, Any]:
        total = len(products)
        brands = set()
        categories = set()
        subcategories = set()
        total_images = 0
        with_barcode = 0
        with_nutrition = 0
        with_ingredients = 0
        duplicate_removed = 0
        failed = 0

        for p in products:
            brands.add(p.metadata.brand)
            if p.metadata.category:
                categories.add(p.metadata.category)
            if p.metadata.subcategory:
                subcategories.add(p.metadata.subcategory)
            total_images += p.valid_image_count
            if p.has_barcode:
                with_barcode += 1
            if p.has_nutrition:
                with_nutrition += 1
            if p.has_ingredients:
                with_ingredients += 1
            if p.metadata.scraping_status == "failed":
                failed += 1
            # Count duplicates from images
            for img in p.images:
                if img.rejection_reason == "duplicate":
                    duplicate_removed += 1

        avg_images = round(total_images / total, 2) if total > 0 else 0
        completion = round((total / max(total, 1)) * 100, 2)

        return {
            "total_products":              total,
            "total_brands":                len(brands),
            "total_categories":            len(categories),
            "total_subcategories":         len(subcategories),
            "total_images":                total_images,
            "average_images_per_product":  avg_images,
            "products_with_barcodes":      with_barcode,
            "products_without_barcodes":   total - with_barcode,
            "products_with_nutrition":     with_nutrition,
            "products_without_nutrition":  total - with_nutrition,
            "products_with_ingredients":   with_ingredients,
            "products_without_ingredients": total - with_ingredients,
            "duplicate_images_removed":    duplicate_removed,
            "failed_products":             failed,
            "scraping_completion_percentage": completion,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    # ──────────────────────────────────────────────
    # dataset_report.json
    # ──────────────────────────────────────────────

    def generate_dataset_report(self, products: List[Product]) -> Path:
        stats = self._compute_stats(products)
        return self._write_json("dataset_report.json", stats)

    # ──────────────────────────────────────────────
    # brand_summary.csv
    # ──────────────────────────────────────────────

    def generate_brand_summary(self, products: List[Product]) -> Path:
        brand_data: Dict[str, Dict] = defaultdict(lambda: {
            "Brand Name": "",
            "Product Count": 0,
            "Total Images": 0,
            "Products With Barcode": 0,
            "Products Missing Barcode": 0,
            "Products With Nutrition": 0,
            "Products Missing Nutrition": 0,
            "Products With Ingredients": 0,
            "Products Missing Ingredients": 0,
        })

        for p in products:
            b = p.metadata.brand or "Unknown"
            d = brand_data[b]
            d["Brand Name"] = b
            d["Product Count"] += 1
            d["Total Images"] += p.valid_image_count
            if p.has_barcode:
                d["Products With Barcode"] += 1
            else:
                d["Products Missing Barcode"] += 1
            if p.has_nutrition:
                d["Products With Nutrition"] += 1
            else:
                d["Products Missing Nutrition"] += 1
            if p.has_ingredients:
                d["Products With Ingredients"] += 1
            else:
                d["Products Missing Ingredients"] += 1

        rows = sorted(brand_data.values(), key=lambda x: x["Product Count"], reverse=True)
        return self._write_csv("brand_summary.csv", rows, [
            "Brand Name", "Product Count", "Total Images",
            "Products With Barcode", "Products Missing Barcode",
            "Products With Nutrition", "Products Missing Nutrition",
            "Products With Ingredients", "Products Missing Ingredients",
        ])

    # ──────────────────────────────────────────────
    # category_summary.csv
    # ──────────────────────────────────────────────

    def generate_category_summary(self, products: List[Product]) -> Path:
        cat_data: Dict[str, Dict] = defaultdict(lambda: {
            "Category": "",
            "Product Count": 0,
            "Total Images": 0,
            "With Barcode": 0,
            "With Nutrition": 0,
            "With Ingredients": 0,
        })

        for p in products:
            cat = p.metadata.category or "Uncategorized"
            d = cat_data[cat]
            d["Category"] = cat
            d["Product Count"] += 1
            d["Total Images"] += p.valid_image_count
            if p.has_barcode:
                d["With Barcode"] += 1
            if p.has_nutrition:
                d["With Nutrition"] += 1
            if p.has_ingredients:
                d["With Ingredients"] += 1

        rows = []
        for cat, d in sorted(cat_data.items(), key=lambda x: x[1]["Product Count"], reverse=True):
            count = d["Product Count"]
            rows.append({
                "Category": cat,
                "Product Count": count,
                "Total Images": d["Total Images"],
                "Average Images Per Product": round(d["Total Images"] / count, 2) if count else 0,
                "Barcode Coverage %": round(d["With Barcode"] / count * 100, 1) if count else 0,
                "Nutrition Coverage %": round(d["With Nutrition"] / count * 100, 1) if count else 0,
                "Ingredient Coverage %": round(d["With Ingredients"] / count * 100, 1) if count else 0,
            })

        return self._write_csv("category_summary.csv", rows, [
            "Category", "Product Count", "Total Images",
            "Average Images Per Product",
            "Barcode Coverage %", "Nutrition Coverage %", "Ingredient Coverage %",
        ])

    # ──────────────────────────────────────────────
    # barcode_coverage.csv
    # ──────────────────────────────────────────────

    def generate_barcode_coverage(self, products: List[Product]) -> Path:
        rows = []
        for p in products:
            rows.append({
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Barcode Available": "Yes" if p.has_barcode else "No",
                "Barcode Value": p.metadata.barcode or "",
                "Source": p.metadata.source,
                "Product URL": p.metadata.product_url or "",
            })
        return self._write_csv("barcode_coverage.csv", rows, [
            "Product Name", "Brand", "Barcode Available", "Barcode Value", "Source", "Product URL"
        ])

    # ──────────────────────────────────────────────
    # nutrition_coverage.csv
    # ──────────────────────────────────────────────

    def generate_nutrition_coverage(self, products: List[Product]) -> Path:
        rows = []
        for p in products:
            rows.append({
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Category": p.metadata.category or "",
                "Nutrition Available": "Yes" if p.has_nutrition else "No",
                "Energy (kcal)": p.info.nutrition.energy_kcal or "",
                "Protein (g)": p.info.nutrition.protein_g or "",
                "Carbs (g)": p.info.nutrition.carbohydrates_g or "",
                "Fat (g)": p.info.nutrition.fat_g or "",
                "Source": p.metadata.source,
            })
        return self._write_csv("nutrition_coverage.csv", rows, [
            "Product Name", "Brand", "Category",
            "Nutrition Available", "Energy (kcal)", "Protein (g)", "Carbs (g)", "Fat (g)",
            "Source",
        ])

    # ──────────────────────────────────────────────
    # ingredients_coverage.csv
    # ──────────────────────────────────────────────

    def generate_ingredients_coverage(self, products: List[Product]) -> Path:
        rows = []
        for p in products:
            rows.append({
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Category": p.metadata.category or "",
                "Ingredients Available": "Yes" if p.has_ingredients else "No",
                "Ingredient Count": len(p.info.ingredients),
                "Source": p.metadata.source,
            })
        return self._write_csv("ingredients_coverage.csv", rows, [
            "Product Name", "Brand", "Category",
            "Ingredients Available", "Ingredient Count", "Source",
        ])

    # ──────────────────────────────────────────────
    # Missing data reports
    # ──────────────────────────────────────────────

    def generate_missing_barcodes(self, products: List[Product]) -> Path:
        rows = [
            {
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Category": p.metadata.category or "",
                "Source Website": p.metadata.source,
                "Reason Missing": "Not available from source",
                "Product URL": p.metadata.product_url or "",
            }
            for p in products if not p.has_barcode
        ]
        return self._write_csv("missing_barcodes.csv", rows, [
            "Product Name", "Brand", "Category", "Source Website", "Reason Missing", "Product URL"
        ])

    def generate_missing_nutrition(self, products: List[Product]) -> Path:
        rows = [
            {
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Category": p.metadata.category or "",
                "Source Website": p.metadata.source,
                "Reason Missing": "Nutrition data not available from source",
                "Product URL": p.metadata.product_url or "",
            }
            for p in products if not p.has_nutrition
        ]
        return self._write_csv("missing_nutrition.csv", rows, [
            "Product Name", "Brand", "Category", "Source Website", "Reason Missing", "Product URL"
        ])

    def generate_missing_ingredients(self, products: List[Product]) -> Path:
        rows = [
            {
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Category": p.metadata.category or "",
                "Source Website": p.metadata.source,
                "Reason Missing": "Ingredient list not available from source",
                "Product URL": p.metadata.product_url or "",
            }
            for p in products if not p.has_ingredients
        ]
        return self._write_csv("missing_ingredients.csv", rows, [
            "Product Name", "Brand", "Category", "Source Website", "Reason Missing", "Product URL"
        ])

    # ──────────────────────────────────────────────
    # image_quality_report.csv
    # ──────────────────────────────────────────────

    def generate_image_quality_report(self, products: List[Product]) -> Path:
        rows = []
        for p in products:
            all_imgs = p.images
            total = len(all_imgs)
            valid = sum(1 for i in all_imgs if i.is_valid)
            duplicates = sum(1 for i in all_imgs if i.rejection_reason == "duplicate")
            blurry = sum(1 for i in all_imgs if i.rejection_reason and "blurry" in i.rejection_reason)
            corrupt = sum(1 for i in all_imgs if i.rejection_reason and "corrupt" in i.rejection_reason)
            too_small = sum(1 for i in all_imgs if i.rejection_reason and "too_small" in i.rejection_reason)

            rows.append({
                "Product Name": p.metadata.product_name,
                "Brand": p.metadata.brand,
                "Original Image Count": total,
                "Valid Images": valid,
                "Duplicates Removed": duplicates,
                "Blurry Images Removed": blurry,
                "Corrupt Images Removed": corrupt,
                "Too Small Removed": too_small,
                "Final Image Count": valid,
                "Meets Minimum Threshold": "Yes" if valid >= MIN_IMAGES_PER_PRODUCT else "No",
            })

        return self._write_csv("image_quality_report.csv", rows, [
            "Product Name", "Brand", "Original Image Count", "Valid Images",
            "Duplicates Removed", "Blurry Images Removed", "Corrupt Images Removed",
            "Too Small Removed", "Final Image Count", "Meets Minimum Threshold",
        ])

    # ──────────────────────────────────────────────
    # duplicate_images_report.csv
    # ──────────────────────────────────────────────

    def generate_duplicate_images_report(self, products: List[Product]) -> Path:
        rows = []
        for p in products:
            dups = [img for img in p.images if img.rejection_reason == "duplicate"]
            for img in dups:
                rows.append({
                    "Product Name": p.metadata.product_name,
                    "Brand": p.metadata.brand,
                    "Duplicate Filename": img.filename,
                    "Original URL": img.url,
                    "Perceptual Hash": img.perceptual_hash or "",
                })

        return self._write_csv("duplicate_images_report.csv", rows, [
            "Product Name", "Brand", "Duplicate Filename", "Original URL", "Perceptual Hash"
        ])

    # ──────────────────────────────────────────────
    # training_readiness_report.json
    # ──────────────────────────────────────────────

    def generate_training_readiness_report(self, products: List[Product]) -> Path:
        total = len(products)
        if total == 0:
            return self._write_json("training_readiness_report.json", {
                "error": "No products found"
            })

        # Compute readiness scores
        avg_images = sum(p.valid_image_count for p in products) / total
        barcode_pct = sum(1 for p in products if p.has_barcode) / total * 100
        nutrition_pct = sum(1 for p in products if p.has_nutrition) / total * 100
        ingredients_pct = sum(1 for p in products if p.has_ingredients) / total * 100
        min_image_pct = sum(1 for p in products if p.valid_image_count >= MIN_IMAGES_PER_PRODUCT) / total * 100

        # Classification: needs avg images ≥ 10 and total products ≥ 100
        classification_score = min(100, int(
            (min(avg_images / 25, 1) * 40) +
            (min(total / 1000, 1) * 40) +
            (min_image_pct / 100 * 20)
        ))

        # Detection: similar to classification but more images needed
        detection_score = min(100, int(
            (min(avg_images / 30, 1) * 50) +
            (min(total / 2000, 1) * 30) +
            (min_image_pct / 100 * 20)
        ))

        # OCR: needs ingredients + good images
        ocr_score = min(100, int(
            (ingredients_pct / 100 * 50) +
            (min(avg_images / 20, 1) * 50)
        ))

        # Barcode lookup: needs barcodes
        barcode_score = int(barcode_pct)

        # Mobile recognition: composite
        mobile_score = min(100, int(
            (classification_score * 0.4) +
            (barcode_score * 0.3) +
            (ocr_score * 0.3)
        ))

        # Weak categories (< 10 products)
        from collections import Counter
        cat_counts = Counter(p.metadata.category or "Uncategorized" for p in products)
        weak_categories = [cat for cat, cnt in cat_counts.items() if cnt < 10]

        # Weak brands (< 3 products)
        brand_counts = Counter(p.metadata.brand for p in products)
        weak_brands = [b for b, cnt in brand_counts.items() if cnt < 3]

        # Products needing more images
        needs_images = [
            p.metadata.product_name
            for p in products
            if p.valid_image_count < MIN_IMAGES_PER_PRODUCT
        ]

        # Recommendations
        recommendations = []
        if avg_images < 10:
            recommendations.append("Collect more images per product (target: 25)")
        if barcode_pct < 70:
            recommendations.append("Improve barcode coverage - enrich from Open Food Facts")
        if nutrition_pct < 60:
            recommendations.append("Collect nutrition data for more products via Open Food Facts")
        if ingredients_pct < 60:
            recommendations.append("Collect ingredient lists for more products")
        if total < 500:
            recommendations.append("Expand dataset to at least 500 products for basic training")
        if len(weak_categories) > 5:
            recommendations.append(f"Collect more products for {len(weak_categories)} underrepresented categories")

        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "dataset_size": total,
            "readiness_scores": {
                "product_classification": classification_score,
                "product_detection": detection_score,
                "ocr_recognition": ocr_score,
                "barcode_recognition": barcode_score,
                "mobile_camera_recognition": mobile_score,
            },
            "classification_ready": classification_score >= 70,
            "object_detection_ready": detection_score >= 70,
            "ocr_ready": ocr_score >= 70,
            "barcode_lookup_ready": barcode_score >= 70,
            "mobile_recognition_ready": mobile_score >= 70,
            "coverage_statistics": {
                "average_images_per_product": round(avg_images, 2),
                "barcode_coverage_pct": round(barcode_pct, 1),
                "nutrition_coverage_pct": round(nutrition_pct, 1),
                "ingredients_coverage_pct": round(ingredients_pct, 1),
                "products_meeting_min_images_pct": round(min_image_pct, 1),
            },
            "recommended_next_steps": recommendations,
            "weak_categories": weak_categories[:20],
            "weak_brands": weak_brands[:20],
            "categories_needing_more_data": [
                {"category": cat, "count": cnt}
                for cat, cnt in sorted(cat_counts.items(), key=lambda x: x[1])
                if cnt < 20
            ][:20],
            "products_needing_more_images": needs_images[:50],
        }

        return self._write_json("training_readiness_report.json", report)

    # ──────────────────────────────────────────────
    # Generate ALL Reports
    # ──────────────────────────────────────────────

    def generate_all_reports(self, products: List[Product]) -> Dict[str, Path]:
        """Generate all required reports and return paths dict."""
        logger.info(f"Generating all reports for {len(products)} products...")

        paths = {}
        paths["dataset_report"]           = self.generate_dataset_report(products)
        paths["brand_summary"]            = self.generate_brand_summary(products)
        paths["category_summary"]         = self.generate_category_summary(products)
        paths["barcode_coverage"]         = self.generate_barcode_coverage(products)
        paths["nutrition_coverage"]       = self.generate_nutrition_coverage(products)
        paths["ingredients_coverage"]     = self.generate_ingredients_coverage(products)
        paths["missing_barcodes"]         = self.generate_missing_barcodes(products)
        paths["missing_nutrition"]        = self.generate_missing_nutrition(products)
        paths["missing_ingredients"]      = self.generate_missing_ingredients(products)
        paths["image_quality_report"]     = self.generate_image_quality_report(products)
        paths["duplicate_images_report"]  = self.generate_duplicate_images_report(products)
        paths["training_readiness_report"]= self.generate_training_readiness_report(products)

        logger.success(f"All {len(paths)} reports generated in {self.reports_dir}")
        return paths
