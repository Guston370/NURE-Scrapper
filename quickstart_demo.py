"""
NURE Quick Start Demo
======================
Demonstrates the pipeline using Open Food Facts API only
(no browser scraping, no captchas, completely free).

Run: python quickstart_demo.py
"""
import os
import sys
os.environ["PYTHONIOENCODING"] = "utf-8"

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console()


def main():
    console.print(Panel.fit(
        "[bold cyan]NURE Food Product Dataset Generator[/bold cyan]\n"
        "Quick Start Demo - Open Food Facts API\n"
        "[dim]No auth required | Free | Indian products[/dim]",
        title="NURE",
        border_style="cyan",
    ))

    from nure.scrapers.openfoodfacts import OpenFoodFactsScraper
    from nure.storage import DatasetStorage
    from nure.reporter import DatasetReporter
    from nure.image_pipeline import process_product_images
    from nure.config import PRODUCTS_DIR

    scraper = OpenFoodFactsScraper()
    storage = DatasetStorage()
    reporter = DatasetReporter()

    # Demo queries - small set for quick demo
    demo_queries = [
        "maggi noodles",
        "amul butter",
        "tata salt",
        "parle g biscuit",
        "aashirvaad atta",
    ]

    all_products = []
    console.print(f"\n[cyan]Scraping {len(demo_queries)} demo queries from Open Food Facts (India)...[/cyan]\n")

    for query in demo_queries:
        console.print(f"  → Searching: [yellow]{query}[/yellow]")
        products = scraper.search_indian_products(query=query, max_results=5)
        console.print(f"    Found: [green]{len(products)} products[/green]")

        for product in products:
            if storage.is_already_scraped(product_id=product.metadata.product_id):
                console.print(f"    [dim]Skip (already scraped): {product.metadata.product_name}[/dim]")
                continue

            # Save metadata (skip images for demo speed)
            storage.save_product(product)
            all_products.append(product)
            console.print(
                f"    [green]✓[/green] {product.metadata.product_name[:50]} "
                f"| barcode={product.metadata.barcode or 'N/A'} "
                f"| images={len(product.images)}"
            )

    console.print(f"\n[bold green]Scraped {len(all_products)} new products![/bold green]")

    # Export
    console.print("\n[cyan]Exporting master files...[/cyan]")
    all_on_disk = storage.load_all_products()
    storage.export_products_csv(all_on_disk)
    storage.export_products_json(all_on_disk)
    storage.export_firestore_json(all_on_disk)
    console.print("[green]✓ products.csv, products.json, firestore_products.json[/green]")

    # Reports
    console.print("\n[cyan]Generating reports...[/cyan]")
    reporter.generate_all_reports(all_on_disk)
    console.print("[green]✓ All reports generated in dataset/reports/[/green]")

    # Final summary
    console.print(Panel.fit(
        f"[bold]Dataset Summary[/bold]\n\n"
        f"Total products: [cyan]{len(all_on_disk)}[/cyan]\n"
        f"Brands: [cyan]{len(set(p.metadata.brand for p in all_on_disk))}[/cyan]\n"
        f"With barcodes: [cyan]{sum(1 for p in all_on_disk if p.has_barcode)}[/cyan]\n"
        f"With nutrition: [cyan]{sum(1 for p in all_on_disk if p.has_nutrition)}[/cyan]\n\n"
        f"[dim]Full pipeline: python main.py scrape-off[/dim]",
        title="[green]Demo Complete[/green]",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
