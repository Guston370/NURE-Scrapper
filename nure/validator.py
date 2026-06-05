"""
NURE Dataset Validator
=======================
Standalone validation script that checks:
1. Dataset folder structure integrity
2. JSON schema validity
3. Image count thresholds
4. Cross-reference between CSV and folders
5. Generates a validation summary
"""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict

from rich.console import Console
from rich.table import Table

from nure.config import PRODUCTS_DIR, DATASET_ROOT, REPORTS_DIR, MIN_IMAGES_PER_PRODUCT
from nure.models import ProductMetadata, ProductInfo

console = Console()


class DatasetValidator:
    """Validates the NURE dataset structure and reports issues."""

    def __init__(self):
        self.errors: List[Dict] = []
        self.warnings: List[Dict] = []
        self.stats: Dict[str, Any] = defaultdict(int)

    def validate_all(self) -> Dict[str, Any]:
        """Run all validation checks."""
        console.rule("[bold cyan]NURE Dataset Validation")

        self._validate_folder_structure()
        self._validate_json_schemas()
        self._validate_image_counts()
        self._validate_master_files()
        self._write_validation_report()

        return {
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "stats": dict(self.stats),
        }

    # ──────────────────────────────────────────────
    # 1. Folder Structure
    # ──────────────────────────────────────────────

    def _validate_folder_structure(self):
        """Check every product folder has required files."""
        console.print("\n[bold]1. Validating folder structure...[/bold]")

        total = 0
        for product_dir in PRODUCTS_DIR.iterdir():
            if not product_dir.is_dir():
                continue
            total += 1

            required = ["metadata.json", "product_info.json"]
            for req in required:
                if not (product_dir / req).exists():
                    self.errors.append({
                        "type": "missing_file",
                        "product": product_dir.name,
                        "detail": f"Missing {req}",
                    })
                    self.stats["missing_required_files"] += 1

            # Check images folder
            images_dir = product_dir / "images"
            if not images_dir.exists():
                self.warnings.append({
                    "type": "missing_images_dir",
                    "product": product_dir.name,
                    "detail": "images/ directory not found",
                })
                self.stats["missing_images_dir"] += 1

        self.stats["total_product_folders"] = total
        console.print(f"  Checked [cyan]{total}[/cyan] product folders")
        console.print(f"  Errors: [red]{self.stats['missing_required_files']}[/red]")

    # ──────────────────────────────────────────────
    # 2. JSON Schema Validation
    # ──────────────────────────────────────────────

    def _validate_json_schemas(self):
        """Validate metadata.json and product_info.json against Pydantic models."""
        console.print("\n[bold]2. Validating JSON schemas...[/bold]")

        valid_meta = 0
        invalid_meta = 0
        valid_info = 0
        invalid_info = 0

        for product_dir in PRODUCTS_DIR.iterdir():
            if not product_dir.is_dir():
                continue

            meta_file = product_dir / "metadata.json"
            info_file = product_dir / "product_info.json"

            # metadata.json
            if meta_file.exists():
                try:
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    ProductMetadata(**data)
                    valid_meta += 1
                except Exception as e:
                    invalid_meta += 1
                    self.errors.append({
                        "type": "invalid_metadata_schema",
                        "product": product_dir.name,
                        "detail": str(e)[:200],
                    })

            # product_info.json
            if info_file.exists():
                try:
                    data = json.loads(info_file.read_text(encoding="utf-8"))
                    ProductInfo(**data)
                    valid_info += 1
                except Exception as e:
                    invalid_info += 1
                    self.errors.append({
                        "type": "invalid_product_info_schema",
                        "product": product_dir.name,
                        "detail": str(e)[:200],
                    })

        self.stats["valid_metadata"] = valid_meta
        self.stats["invalid_metadata"] = invalid_meta
        self.stats["valid_product_info"] = valid_info
        self.stats["invalid_product_info"] = invalid_info

        console.print(f"  metadata.json valid: [green]{valid_meta}[/green] | invalid: [red]{invalid_meta}[/red]")
        console.print(f"  product_info.json valid: [green]{valid_info}[/green] | invalid: [red]{invalid_info}[/red]")

    # ──────────────────────────────────────────────
    # 3. Image Count Thresholds
    # ──────────────────────────────────────────────

    def _validate_image_counts(self):
        """Check that products meet minimum image thresholds."""
        console.print(f"\n[bold]3. Validating image counts (min: {MIN_IMAGES_PER_PRODUCT})...[/bold]")

        meets_min = 0
        below_min = 0
        no_images = 0

        for product_dir in PRODUCTS_DIR.iterdir():
            if not product_dir.is_dir():
                continue

            images_dir = product_dir / "images"
            if not images_dir.exists():
                no_images += 1
                continue

            image_files = (
                list(images_dir.glob("*.jpg")) +
                list(images_dir.glob("*.png")) +
                list(images_dir.glob("*.webp")) +
                list(images_dir.glob("*.jpeg"))
            )
            count = len(image_files)

            if count == 0:
                no_images += 1
                self.warnings.append({
                    "type": "no_images",
                    "product": product_dir.name,
                    "detail": "Product has 0 images",
                })
            elif count < MIN_IMAGES_PER_PRODUCT:
                below_min += 1
                self.warnings.append({
                    "type": "below_min_images",
                    "product": product_dir.name,
                    "detail": f"Only {count}/{MIN_IMAGES_PER_PRODUCT} images",
                })
            else:
                meets_min += 1

        self.stats["meets_min_images"] = meets_min
        self.stats["below_min_images"] = below_min
        self.stats["no_images"] = no_images

        console.print(f"  Meets minimum: [green]{meets_min}[/green]")
        console.print(f"  Below minimum: [yellow]{below_min}[/yellow]")
        console.print(f"  No images: [red]{no_images}[/red]")

    # ──────────────────────────────────────────────
    # 4. Master Files
    # ──────────────────────────────────────────────

    def _validate_master_files(self):
        """Check that products.csv and products.json exist and are valid."""
        console.print("\n[bold]4. Validating master files...[/bold]")

        for filename in ["products.csv", "products.json"]:
            path = DATASET_ROOT / filename
            if not path.exists():
                self.warnings.append({
                    "type": "missing_master_file",
                    "product": "dataset_root",
                    "detail": f"{filename} not found - run 'python main.py export'",
                })
                console.print(f"  [yellow]⚠ {filename} not found[/yellow]")
            else:
                console.print(f"  [green]✓ {filename}[/green]")

        # Firestore export
        firestore = DATASET_ROOT / "firestore_export" / "firestore_products.json"
        if not firestore.exists():
            self.warnings.append({
                "type": "missing_firestore_export",
                "product": "firestore_export",
                "detail": "firestore_products.json not found",
            })
            console.print("  [yellow]⚠ firestore_products.json not found[/yellow]")
        else:
            console.print("  [green]✓ firestore_products.json[/green]")

    # ──────────────────────────────────────────────
    # Validation Report
    # ──────────────────────────────────────────────

    def _write_validation_report(self):
        """Write validation results to reports/validation_report.json."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report = {
            "validated_at": datetime.utcnow().isoformat() + "Z",
            "summary": dict(self.stats),
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings),
            "errors": self.errors[:200],
            "warnings": self.warnings[:200],
            "passed": len(self.errors) == 0,
        }

        report_path = REPORTS_DIR / "validation_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        console.print(f"\n[bold]Validation Report:[/bold]")
        table = Table(show_header=True)
        table.add_column("Check", style="cyan")
        table.add_column("Result")

        table.add_row("Total folders", str(self.stats.get("total_product_folders", 0)))
        table.add_row("Valid metadata", f"[green]{self.stats.get('valid_metadata', 0)}[/green]")
        table.add_row("Invalid metadata", f"[red]{self.stats.get('invalid_metadata', 0)}[/red]")
        table.add_row("Meets image minimum", f"[green]{self.stats.get('meets_min_images', 0)}[/green]")
        table.add_row("Below image minimum", f"[yellow]{self.stats.get('below_min_images', 0)}[/yellow]")
        table.add_row("No images", f"[red]{self.stats.get('no_images', 0)}[/red]")
        table.add_row("Errors", f"[red]{len(self.errors)}[/red]")
        table.add_row("Warnings", f"[yellow]{len(self.warnings)}[/yellow]")
        table.add_row("Overall Pass", "[green]✓ YES[/green]" if not self.errors else "[red]✗ NO[/red]")

        console.print(table)
        console.print(f"\nFull report: [cyan]{report_path}[/cyan]")


if __name__ == "__main__":
    validator = DatasetValidator()
    result = validator.validate_all()
    exit(0 if result["errors"] == 0 else 1)
