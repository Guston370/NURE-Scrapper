"""
NURE Dataset Pipeline - Orchestrator
======================================
Main orchestrator that:
1. Runs all scrapers across all configured categories
2. Downloads and validates images
3. Saves products to disk
4. Exports master CSV/JSON/Firestore files
5. Generates all audit reports

Supports resume capability - already-scraped products are skipped.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from nure.config import FOOD_CATEGORIES, SOURCE_PRIORITY, MIN_IMAGES_PER_PRODUCT
from nure.models import Product, FailedProduct
from nure.scrapers import get_scraper, list_sources
from nure.storage import DatasetStorage
from nure.reporter import DatasetReporter
from nure.image_pipeline import process_product_images
from nure.config import PRODUCTS_DIR


console = Console()


class NUREPipeline:
    """
    Main pipeline orchestrating scraping, image processing,
    storage, and reporting for the NURE food product dataset.
    """

    def __init__(
        self,
        sources: Optional[List[str]] = None,
        max_products_per_query: int = 50,
        skip_images: bool = False,
        max_workers: int = 3,
    ):
        self.sources = sources or SOURCE_PRIORITY
        self.max_per_query = max_products_per_query
        self.skip_images = skip_images
        self.max_workers = max_workers
        self.storage = DatasetStorage()
        self.reporter = DatasetReporter()
        self._all_products: List[Product] = []

    # ──────────────────────────────────────────────
    # Product Processing
    # ──────────────────────────────────────────────

    def _process_product(self, product: Product) -> Optional[Product]:
        """
        Process a single product:
        1. Check if already scraped (resume)
        2. Download + validate images
        3. Save to disk
        """
        pid = product.metadata.product_id

        if self.storage.is_already_scraped(product_id=pid):
            logger.debug(f"Skipping already-scraped product: {pid}")
            return None

        # Image pipeline
        if not self.skip_images and product.images:
            image_urls = [img.url for img in product.images if img.url]
            product_dir = PRODUCTS_DIR / (product.metadata.folder_name or pid)
            images_dir  = product_dir / "images"

            records, img_stats = process_product_images(
                image_urls=image_urls,
                output_dir=images_dir,
                product_id=pid,
            )
            product.images = records
            product.metadata.image_count = product.valid_image_count

        # Save to disk
        try:
            self.storage.save_product(product)
            return product
        except Exception as e:
            logger.error(f"Failed to save product {pid}: {e}")
            self.storage.record_failure(FailedProduct(
                product_name=product.metadata.product_name,
                brand=product.metadata.brand,
                source=product.metadata.source,
                product_url=product.metadata.product_url,
                error_message=str(e),
            ))
            return None

    # ──────────────────────────────────────────────
    # Scraping Loop
    # ──────────────────────────────────────────────

    def _scrape_source_query(
        self,
        source: str,
        query: str,
        category: str,
    ) -> List[Product]:
        """Scrape one query from one source."""
        try:
            scraper = get_scraper(source)
            products = scraper.search_products(
                query=query,
                category=category,
                max_results=self.max_per_query,
            )
            logger.info(
                f"[{source}] '{query}' → {len(products)} products found"
            )
            return products
        except Exception as e:
            logger.error(f"[{source}] Query '{query}' failed: {e}")
            return []

    def run(self):
        """
        Full pipeline run.
        Iterates all categories × queries × sources.
        """
        console.rule("[bold cyan]NURE Food Product Dataset Pipeline")
        console.print(f"[green]Sources:[/green] {', '.join(self.sources)}")
        console.print(f"[green]Categories:[/green] {len(FOOD_CATEGORIES)}")
        console.print(f"[green]Resume:[/green] {self.storage.scraped_count} products already in dataset\n")

        total_new = 0
        total_failed = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            for category_name, queries in FOOD_CATEGORIES.items():
                cat_task = progress.add_task(
                    f"[cyan]{category_name}",
                    total=len(queries) * len(self.sources)
                )

                for query in queries:
                    for source in self.sources:
                        progress.update(
                            cat_task,
                            description=f"[cyan]{source}[/cyan] • {query[:30]}"
                        )

                        raw_products = self._scrape_source_query(
                            source, query, category_name
                        )

                        for product in raw_products:
                            result = self._process_product(product)
                            if result:
                                self._all_products.append(result)
                                total_new += 1
                            else:
                                total_failed += 1

                        progress.advance(cat_task)

                        # Flush failures periodically
                        if total_failed % 10 == 0:
                            self.storage.flush_failures()

        # Final flush
        self.storage.flush_failures()

        console.print(f"\n[bold green]Scraping complete![/bold green]")
        console.print(f"New products: [cyan]{total_new}[/cyan]")
        console.print(f"Total in dataset: [cyan]{self.storage.scraped_count}[/cyan]")
        console.print(f"Failed: [red]{total_failed}[/red]\n")

        # Run post-processing
        self._post_process()

    # ──────────────────────────────────────────────
    # Open Food Facts dedicated run (highest priority)
    # ──────────────────────────────────────────────

    def run_openfoodfacts_bulk(self, max_per_category: int = 200):
        """
        Dedicated run for Open Food Facts with Indian country filter.
        Produces the richest nutrition + barcode data.
        """
        from nure.scrapers.openfoodfacts import OpenFoodFactsScraper

        console.rule("[bold yellow]Open Food Facts Bulk Scraper (India)")
        scraper = OpenFoodFactsScraper()
        total = 0

        for category_name, queries in FOOD_CATEGORIES.items():
            for query in queries:
                logger.info(f"[OFF-Bulk] Scraping Indian products: '{query}'")
                products = scraper.search_indian_products(
                    query=query,
                    max_results=max_per_category,
                )

                for product in products:
                    result = self._process_product(product)
                    if result:
                        self._all_products.append(result)
                        total += 1

        console.print(f"[green]OFF bulk complete: {total} products scraped[/green]")

    # ──────────────────────────────────────────────
    # Post-Processing
    # ──────────────────────────────────────────────

    def _post_process(self):
        """Export master files and generate all reports."""
        console.rule("[bold yellow]Post-Processing & Report Generation")

        # Load ALL products (including from previous runs)
        all_on_disk = self.storage.load_all_products()
        logger.info(f"Total products on disk: {len(all_on_disk)}")

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as p:
            t = p.add_task("Exporting products.csv ...", total=None)
            self.storage.export_products_csv(all_on_disk)
            p.update(t, description="[green]✓ products.csv")

            p.update(t, description="Exporting products.json ...")
            self.storage.export_products_json(all_on_disk)
            p.update(t, description="[green]✓ products.json")

            p.update(t, description="Exporting Firestore JSON ...")
            self.storage.export_firestore_json(all_on_disk)
            p.update(t, description="[green]✓ firestore_export/firestore_products.json")

            p.update(t, description="Generating all reports ...")
            report_paths = self.reporter.generate_all_reports(all_on_disk)
            p.update(t, description=f"[green]✓ {len(report_paths)} reports generated")

        # Print summary table
        self._print_summary(all_on_disk)

    def _print_summary(self, products: List[Product]):
        """Print a rich summary table."""
        table = Table(title="NURE Dataset Summary", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        total = len(products)
        brands = len(set(p.metadata.brand for p in products))
        categories = len(set(p.metadata.category or "" for p in products))
        total_images = sum(p.valid_image_count for p in products)
        with_barcode = sum(1 for p in products if p.has_barcode)
        with_nutrition = sum(1 for p in products if p.has_nutrition)
        with_ingredients = sum(1 for p in products if p.has_ingredients)

        table.add_row("Total Products", str(total))
        table.add_row("Total Brands", str(brands))
        table.add_row("Total Categories", str(categories))
        table.add_row("Total Images", str(total_images))
        table.add_row("Avg Images/Product", f"{total_images/total:.1f}" if total else "0")
        table.add_row("With Barcode", f"{with_barcode} ({with_barcode/total*100:.1f}%)" if total else "0")
        table.add_row("With Nutrition", f"{with_nutrition} ({with_nutrition/total*100:.1f}%)" if total else "0")
        table.add_row("With Ingredients", f"{with_ingredients} ({with_ingredients/total*100:.1f}%)" if total else "0")

        console.print(table)

    def reports_only(self):
        """Run only post-processing (no scraping) on existing dataset."""
        console.rule("[bold cyan]Report Generation Only")
        self._post_process()
