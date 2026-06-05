"""
NURE Phase 3 - Metadata Enrichment
=====================================
Reads products.csv and enriches every product with:
- Barcode, Ingredients, Nutrition, Manufacturer, Weight,
  Description, Country of Origin

Uses Open Food Facts barcode API as primary enrichment source.
Generates missing_*.csv reports.

Run: python -X utf8 phase3_metadata.py
"""
import os, sys, json, csv, time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

os.environ["PYTHONIOENCODING"] = "utf-8"

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich.table import Table
from loguru import logger

console = Console()

DATASET_DIR = Path("dataset")
REPORTS_DIR = DATASET_DIR / "reports"
PRODUCTS_DIR = DATASET_DIR / "products"

logger.remove()
logger.add(sys.stdout, level="WARNING",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
logger.add(DATASET_DIR / "logs" / "phase3.log",
    level="DEBUG", rotation="50 MB", encoding="utf-8")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "NURE-Dataset-Builder/1.0",
    "Accept": "application/json",
})

OFF_BARCODE_API = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_SEARCH_URL  = "https://world.openfoodfacts.org/cgi/search.pl"

OFF_DETAIL_FIELDS = (
    "code,product_name,product_name_en,brands,quantity,categories_tags,"
    "ingredients_text_en,ingredients_text,nutriments,allergens_tags,"
    "manufacturing_places,origins,countries,conservation_conditions,"
    "generic_name_en,generic_name,labels,nutriscore_grade,nova_group,"
    "image_front_url,image_ingredients_url,image_nutrition_url,url"
)


def lookup_barcode(barcode: str) -> Optional[dict]:
    """Fetch full product data from OFF by barcode."""
    url = OFF_BARCODE_API.format(barcode=barcode)
    try:
        resp = SESSION.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("status") != 1:
            return None
        return data.get("product", {})
    except Exception as e:
        logger.warning(f"Barcode lookup failed {barcode}: {e}")
        return None


def search_by_name(name: str, brand: str) -> Optional[dict]:
    """Search OFF for a product by name+brand when no barcode."""
    query = f"{brand} {name}".strip()
    try:
        resp = SESSION.get(OFF_SEARCH_URL, params={
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 3,
            "fields": OFF_DETAIL_FIELDS,
        }, timeout=15)
        if resp.status_code != 200:
            return None
        products = resp.json().get("products", [])
        if products:
            return products[0]
    except Exception as e:
        logger.warning(f"Name search failed '{query}': {e}")
    return None


def parse_nutrition(nutriments: dict) -> dict:
    def g(k):
        return nutriments.get(f"{k}_100g") or nutriments.get(k)
    return {
        "energy_kcal": g("energy-kcal"),
        "protein_g": g("proteins"),
        "carbohydrates_g": g("carbohydrates"),
        "of_which_sugars_g": g("sugars"),
        "fat_g": g("fat"),
        "of_which_saturated_fat_g": g("saturated-fat"),
        "dietary_fiber_g": g("fiber"),
        "sodium_mg": g("sodium"),
    }


def parse_ingredients(raw_data: dict) -> List[str]:
    raw = raw_data.get("ingredients_text_en") or raw_data.get("ingredients_text","")
    if not raw:
        return []
    import re
    raw = re.sub(r"\(.*?\)", "", raw)
    parts = [p.strip() for p in re.split(r"[,;]", raw) if p.strip()]
    return parts[:60]


def enrich_product(product: dict) -> dict:
    """Enrich one product row with full metadata from OFF."""
    barcode = product.get("barcode","").strip()
    raw_data = None

    if barcode and len(barcode) >= 8:
        raw_data = lookup_barcode(barcode)
        time.sleep(0.8)

    if not raw_data:
        raw_data = search_by_name(product.get("product_name",""), product.get("brand",""))
        time.sleep(1.2)

    if not raw_data:
        product["enrichment_status"] = "not_found"
        product["ingredients"] = []
        product["nutrition"] = {}
        product["allergens"] = []
        return product

    # Fill in missing barcode
    if not barcode and raw_data.get("code"):
        product["barcode"] = raw_data["code"]

    product["ingredients"] = parse_ingredients(raw_data)
    product["nutrition"] = parse_nutrition(raw_data.get("nutriments", {}))
    product["allergens"] = [
        a.replace("en:","").replace("-"," ").title()
        for a in (raw_data.get("allergens_tags") or [])
    ]
    product["description"] = raw_data.get("generic_name_en") or raw_data.get("generic_name","")
    product["country_of_origin"] = (
        product.get("country_of_origin")
        or raw_data.get("origins")
        or raw_data.get("countries","")
    )
    product["manufacturer"] = (
        product.get("manufacturer")
        or raw_data.get("manufacturing_places","")
    )
    product["weight"] = product.get("weight") or raw_data.get("quantity","")
    product["storage_information"] = raw_data.get("conservation_conditions","")
    product["nutriscore_grade"] = raw_data.get("nutriscore_grade","")
    product["nova_group"] = raw_data.get("nova_group","")

    # Image URLs
    product["image_url_front"] = product.get("image_url_front") or raw_data.get("image_front_url","")
    product["image_url_ingredients"] = raw_data.get("image_ingredients_url","")
    product["image_url_nutrition"] = raw_data.get("image_nutrition_url","")

    product["enrichment_status"] = "enriched"
    return product


def has_nutrition(product: dict) -> bool:
    n = product.get("nutrition", {})
    return any(v for v in n.values() if v is not None)


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    console.print(f"  [green]Wrote[/green] {path.name} ({len(rows)} rows)")


def main():
    console.rule("[bold cyan]NURE Phase 3 - Metadata Enrichment")

    # Load products.csv
    products_csv = DATASET_DIR / "products.csv"
    if not products_csv.exists():
        console.print("[red]products.csv not found. Run Phase 1 first.[/red]")
        return

    with open(products_csv, encoding="utf-8") as f:
        products = list(csv.DictReader(f))

    console.print(f"Loaded [cyan]{len(products)}[/cyan] products from products.csv")
    console.print("Enriching with nutrition, ingredients, barcodes from Open Food Facts...\n")

    enriched = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), MofNCompleteColumn(), console=console) as prog:
        task = prog.add_task("Enriching", total=len(products))

        for product in products:
            prog.update(task, description=f"[cyan]{product.get('brand','')[:20]} {product.get('product_name','')[:25]}")
            result = enrich_product(dict(product))
            enriched.append(result)
            prog.advance(task)

    # Stats
    total = len(enriched)
    with_barcode     = sum(1 for p in enriched if p.get("barcode"))
    with_nutrition   = sum(1 for p in enriched if has_nutrition(p))
    with_ingredients = sum(1 for p in enriched if p.get("ingredients"))
    enriched_count   = sum(1 for p in enriched if p.get("enrichment_status") == "enriched")

    # Save enriched products.json
    (DATASET_DIR / "products.json").write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [green]Wrote[/green] products.json ({total} products)")

    # Update products.csv with enrichment fields
    all_keys = list({k for p in enriched for k in p.keys()})
    write_csv(DATASET_DIR / "products.csv", enriched, all_keys)

    # Save per-product metadata files
    PRODUCTS_DIR.mkdir(exist_ok=True)
    for p in enriched:
        import re
        brand = re.sub(r"[^a-zA-Z0-9]", "_", p.get("brand","Unknown"))
        name  = re.sub(r"[^a-zA-Z0-9]", "_", p.get("product_name","Unknown"))
        weight= re.sub(r"[^a-zA-Z0-9]", "_", p.get("weight",""))
        parts = [brand, name] + ([weight] if weight else [])
        folder = "_".join(p for p in parts if p)[:100]
        folder = re.sub(r"_+", "_", folder).strip("_")

        pdir = PRODUCTS_DIR / folder
        pdir.mkdir(exist_ok=True)
        (pdir / "images").mkdir(exist_ok=True)

        meta = {
            "product_id": p.get("product_id",""),
            "product_name": p.get("product_name",""),
            "brand": p.get("brand",""),
            "barcode": p.get("barcode",""),
            "category": p.get("category",""),
            "subcategory": p.get("subcategory",""),
            "weight": p.get("weight",""),
            "manufacturer": p.get("manufacturer",""),
            "source": p.get("source",""),
            "product_url": p.get("product_url",""),
            "image_count": 0,
            "folder_name": folder,
            "scraping_status": p.get("enrichment_status",""),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        (pdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        info = {
            "ingredients": p.get("ingredients",[]),
            "nutrition": p.get("nutrition",{}),
            "allergens": p.get("allergens",[]),
            "description": p.get("description",""),
            "country_of_origin": p.get("country_of_origin",""),
            "storage_information": p.get("storage_information",""),
            "fssai_information": "",
            "nutriscore_grade": p.get("nutriscore_grade",""),
            "nova_group": p.get("nova_group",""),
        }
        (pdir / "product_info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    # Missing reports
    missing_barcode = [p for p in enriched if not p.get("barcode")]
    write_csv(REPORTS_DIR / "missing_barcodes.csv", missing_barcode,
        ["product_name","brand","category","source","product_url"])

    missing_nutrition = [p for p in enriched if not has_nutrition(p)]
    write_csv(REPORTS_DIR / "missing_nutrition.csv", missing_nutrition,
        ["product_name","brand","category","source","enrichment_status"])

    missing_ingredients = [p for p in enriched if not p.get("ingredients")]
    write_csv(REPORTS_DIR / "missing_ingredients.csv", missing_ingredients,
        ["product_name","brand","category","source","enrichment_status"])

    # Updated dataset_report.json
    report = {
        "phase": 3,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_products": total,
        "enriched_products": enriched_count,
        "products_with_barcode": with_barcode,
        "products_without_barcode": total - with_barcode,
        "barcode_coverage_pct": round(with_barcode/total*100, 1) if total else 0,
        "products_with_nutrition": with_nutrition,
        "products_without_nutrition": total - with_nutrition,
        "nutrition_coverage_pct": round(with_nutrition/total*100, 1) if total else 0,
        "products_with_ingredients": with_ingredients,
        "products_without_ingredients": total - with_ingredients,
        "ingredients_coverage_pct": round(with_ingredients/total*100, 1) if total else 0,
        "images_collected": False,
        "metadata_enriched": True,
    }
    (REPORTS_DIR / "dataset_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [green]Wrote[/green] dataset_report.json")

    # Summary
    table = Table(title="Phase 3 Enrichment Summary", header_style="bold cyan")
    table.add_column("Metric", style="cyan", min_width=35)
    table.add_column("Value", style="green", justify="right")
    table.add_row("Total Products", str(total))
    table.add_row("Successfully Enriched", str(enriched_count))
    table.add_row("With Barcode", f"{with_barcode} ({report['barcode_coverage_pct']}%)")
    table.add_row("With Nutrition", f"{with_nutrition} ({report['nutrition_coverage_pct']}%)")
    table.add_row("With Ingredients", f"{with_ingredients} ({report['ingredients_coverage_pct']}%)")
    table.add_row("Missing Barcodes", str(total - with_barcode))
    table.add_row("Missing Nutrition", str(total - with_nutrition))
    table.add_row("Missing Ingredients", str(total - with_ingredients))
    console.print(table)

    console.print("\n[bold yellow]Phase 4 Review:[/bold yellow] Upload these for analysis:")
    console.print("  - dataset/products.json")
    console.print("  - dataset/reports/dataset_report.json")
    console.print("  - dataset/reports/missing_barcodes.csv")
    console.print("  - dataset/reports/missing_nutrition.csv")


if __name__ == "__main__":
    main()
