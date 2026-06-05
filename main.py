"""
NURE Dataset Generator - CLI Entry Point
==========================================
Usage:
  python main.py scrape              # Full pipeline (all sources, all categories)
  python main.py scrape-off          # Open Food Facts bulk only (fastest, best data)
  python main.py reports             # Generate reports from existing dataset
  python main.py validate            # Validate dataset structure
  python main.py barcode <barcode>   # Lookup single product by barcode
  python main.py export              # Export CSV/JSON/Firestore only

Options:
  --sources         Comma-separated source list (e.g. openfoodfacts,bigbasket)
  --max-per-query   Max products per query per source (default: 50)
  --skip-images     Skip image downloading (metadata only)
  --workers         Concurrent workers for image downloads (default: 3)
"""

import sys
import click
from rich.console import Console
from loguru import logger

from nure.logger import setup_logger
from nure.pipeline import NUREPipeline
from nure.scrapers import list_sources

console = Console()
setup_logger("nure_main")


@click.group()
@click.version_option("1.0.0", prog_name="NURE Dataset Generator")
def cli():
    """NURE Food Product Dataset Generator CLI."""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# scrape
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option(
    "--sources",
    default=None,
    help="Comma-separated list of sources to use. Defaults to all available.",
)
@click.option(
    "--max-per-query",
    default=50,
    type=int,
    show_default=True,
    help="Maximum products to collect per query per source.",
)
@click.option(
    "--skip-images",
    is_flag=True,
    default=False,
    help="Skip image downloading (metadata only run).",
)
@click.option(
    "--workers",
    default=3,
    type=int,
    show_default=True,
    help="Number of concurrent image download workers.",
)
def scrape(sources, max_per_query, skip_images, workers):
    """Run the full scraping pipeline across all sources and categories."""
    source_list = [s.strip() for s in sources.split(",")] if sources else None

    console.print("[bold cyan]Starting NURE Full Pipeline...[/bold cyan]")
    console.print(f"Sources: [yellow]{source_list or 'all'}[/yellow]")
    console.print(f"Max per query: [yellow]{max_per_query}[/yellow]")
    console.print(f"Skip images: [yellow]{skip_images}[/yellow]\n")

    pipeline = NUREPipeline(
        sources=source_list,
        max_products_per_query=max_per_query,
        skip_images=skip_images,
        max_workers=workers,
    )
    pipeline.run()


# ──────────────────────────────────────────────────────────────────────────────
# scrape-off (Open Food Facts dedicated)
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("scrape-off")
@click.option(
    "--max-per-category",
    default=200,
    type=int,
    show_default=True,
    help="Max products per category from Open Food Facts.",
)
@click.option(
    "--skip-images",
    is_flag=True,
    default=False,
    help="Skip image downloading.",
)
def scrape_off(max_per_category, skip_images):
    """
    Bulk scrape from Open Food Facts only (Indian products).
    Fastest way to get barcode, nutrition, and ingredient data.
    """
    console.print("[bold yellow]NURE → Open Food Facts Bulk Scraper[/bold yellow]")
    pipeline = NUREPipeline(
        sources=["openfoodfacts"],
        skip_images=skip_images,
    )
    pipeline.run_openfoodfacts_bulk(max_per_category=max_per_category)
    pipeline._post_process()


# ──────────────────────────────────────────────────────────────────────────────
# reports
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
def reports():
    """Generate all audit reports from existing dataset (no scraping)."""
    console.print("[bold cyan]Generating reports from existing dataset...[/bold cyan]")
    pipeline = NUREPipeline()
    pipeline.reports_only()


# ──────────────────────────────────────────────────────────────────────────────
# export
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
def export():
    """Export products.csv, products.json, and Firestore JSON from existing dataset."""
    console.print("[bold cyan]Exporting dataset files...[/bold cyan]")
    from nure.storage import DatasetStorage

    storage = DatasetStorage()
    products = storage.load_all_products()
    console.print(f"Found [green]{len(products)}[/green] products on disk")

    storage.export_products_csv(products)
    storage.export_products_json(products)
    storage.export_firestore_json(products)

    console.print("[bold green]Export complete![/bold green]")


# ──────────────────────────────────────────────────────────────────────────────
# validate
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
def validate():
    """Validate dataset folder structure and report issues."""
    from nure.config import PRODUCTS_DIR
    import json

    console.print("[bold cyan]Validating dataset structure...[/bold cyan]")

    issues = []
    total = 0
    valid = 0

    for product_dir in PRODUCTS_DIR.iterdir():
        if not product_dir.is_dir():
            continue
        total += 1

        meta = product_dir / "metadata.json"
        info = product_dir / "product_info.json"
        images_dir = product_dir / "images"

        if not meta.exists():
            issues.append(f"{product_dir.name}: missing metadata.json")
            continue
        if not info.exists():
            issues.append(f"{product_dir.name}: missing product_info.json")
            continue
        if not images_dir.exists() or not any(images_dir.iterdir()):
            issues.append(f"{product_dir.name}: empty or missing images/")
            continue

        # Validate metadata JSON
        try:
            json.loads(meta.read_text(encoding="utf-8"))
        except Exception as e:
            issues.append(f"{product_dir.name}: invalid metadata.json - {e}")
            continue

        valid += 1

    console.print(f"\n[green]Valid products:[/green] {valid}/{total}")
    console.print(f"[red]Issues found:[/red] {len(issues)}")

    if issues:
        console.print("\n[bold red]Issues:[/bold red]")
        for issue in issues[:50]:
            console.print(f"  • {issue}")
        if len(issues) > 50:
            console.print(f"  ... and {len(issues) - 50} more")


# ──────────────────────────────────────────────────────────────────────────────
# barcode lookup
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("barcode")
@click.option("--save", is_flag=True, default=False, help="Save the product to dataset.")
def barcode(barcode, save):
    """Lookup a product by barcode from Open Food Facts."""
    console.print(f"[bold cyan]Looking up barcode: {barcode}[/bold cyan]")

    from nure.scrapers.openfoodfacts import OpenFoodFactsScraper
    scraper = OpenFoodFactsScraper()
    product = scraper.get_products_by_barcode(barcode)

    if not product:
        console.print(f"[red]Product not found for barcode: {barcode}[/red]")
        return

    console.print(f"[green]Found:[/green] {product.metadata.product_name}")
    console.print(f"  Brand:       {product.metadata.brand}")
    console.print(f"  Category:    {product.metadata.category}")
    console.print(f"  Weight:      {product.metadata.weight}")
    console.print(f"  Ingredients: {len(product.info.ingredients)} items")
    console.print(f"  Images:      {len(product.images)}")

    if save:
        storage = DatasetStorage()
        storage.save_product(product)
        console.print(f"[green]Product saved: {product.metadata.folder_name}[/green]")


# ──────────────────────────────────────────────────────────────────────────────
# list-sources
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("list-sources")
def list_sources_cmd():
    """List all available scraper sources."""
    console.print("[bold cyan]Available scraper sources:[/bold cyan]")
    for source in list_sources():
        console.print(f"  • {source}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
