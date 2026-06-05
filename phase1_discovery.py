"""
NURE Phase 1 - Product Discovery
==================================
Discovers Indian food products across sources.
NO image downloads. Metadata only.

Run: python -X utf8 phase1_discovery.py
"""
import os, sys, json, csv, time, hashlib, re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional

os.environ["PYTHONIOENCODING"] = "utf-8"

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich.table import Table
from loguru import logger

console = Console()

# ── Paths ────────────────────────────────────────────────
DATASET_DIR  = Path("dataset")
REPORTS_DIR  = DATASET_DIR / "reports"
DATASET_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ── Logger ───────────────────────────────────────────────
logger.remove()
logger.add(sys.stdout, level="WARNING",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
logger.add(DATASET_DIR / "logs" / "phase1.log",
    level="DEBUG", rotation="50 MB", encoding="utf-8")
Path(DATASET_DIR / "logs").mkdir(exist_ok=True)

# ── HTTP Session ─────────────────────────────────────────
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "NURE-Dataset-Builder/1.0 (research project)",
    "Accept": "application/json",
})

# ── Indian Food Categories + OFF category tags ───────────
OFF_CATEGORY_TAGS = [
    ("Grains & Flour",      "flours",           "atta"),
    ("Grains & Flour",      "rice",              "basmati rice"),
    ("Dal & Pulses",        "pulses",            "toor dal"),
    ("Dal & Pulses",        "lentils",           "moong dal"),
    ("Spices & Masala",     "spices",            "turmeric powder"),
    ("Spices & Masala",     "condiments",        "garam masala"),
    ("Cooking Oil",         "oils",              "sunflower oil"),
    ("Cooking Oil",         "oils",              "mustard oil"),
    ("Dairy",               "butters",           "amul butter"),
    ("Dairy",               "cheeses",           "paneer"),
    ("Snacks",              "biscuits-and-cakes","parle g"),
    ("Snacks",              "snacks",            "kurkure"),
    ("Snacks",              "chips-and-crisps",  "lays"),
    ("Instant Foods",       "instant-meals",     "maggi noodles"),
    ("Instant Foods",       "instant-soups",     "knorr soup"),
    ("Sauces",              "ketchup",           "maggi ketchup"),
    ("Beverages",           "teas",              "tata tea"),
    ("Beverages",           "coffees",           "nescafe"),
    ("Health & Nutrition",  "nutritional-supplements", "horlicks"),
    ("Health & Nutrition",  "baby-foods",        "cerelac"),
    ("Sugar & Sweeteners",  "sugars",            "sugar"),
    ("Bakery",              "breads",            "bread"),
    ("Breakfast Cereals",   "breakfast-cereals", "corn flakes"),
    ("Noodles & Pasta",     "pasta",             "yippee noodles"),
    ("Salt & Pepper",       "salts",             "tata salt"),
    ("Ghee & Butter",       "ghee",              "amul ghee"),
    ("Pickles & Chutneys",  "condiments",        "mango pickle"),
    ("Chocolates",          "chocolates",        "dairy milk"),
    ("Ice Cream",           "ice-creams",        "kwality walls"),
    ("Jams & Spreads",      "jams",              "kissan jam"),
]

SEARCH_QUERIES = [
    # Grains
    "aashirvaad atta", "shaktibhog atta", "pillsbury atta", "fortune atta",
    "india gate basmati", "daawat basmati", "kohinoor basmati",
    # Dal
    "toor dal", "moong dal", "chana dal", "rajma", "kabuli chana",
    # Spices
    "everest masala", "mdh masala", "catch spices", "badshah masala",
    "sakthi masala", "eastern masala",
    # Oil
    "fortune sunflower oil", "saffola oil", "dhara oil", "goldwinner oil",
    "sundrop oil", "emami healthy cooking oil",
    # Dairy
    "amul butter", "amul cheese", "mother dairy", "nandini milk",
    "kwality dairy", "verka paneer",
    # Snacks
    "haldiram namkeen", "bingo snacks", "uncle chips", "act ii popcorn",
    "munchies", "bikaji bhujia", "balaji chips",
    # Biscuits
    "britannia good day", "oreo india", "mcvities", "glucose biscuit",
    "monaco biscuit", "jim jam", "bourbon", "marie gold",
    # Instant
    "maggi noodles", "top ramen", "yippee noodles", "knorr soup",
    "ching secret masala", "sunfeast yippee",
    # Beverages
    "tata tea premium", "red label tea", "wagh bakri tea", "lipton tea",
    "nescafe classic", "bru coffee", "continental coffee",
    # Health drinks
    "horlicks classic", "bournvita", "complan", "boost health drink",
    "pediasure", "protinex",
    # Chocolates
    "cadbury dairy milk", "kit kat india", "5 star chocolate",
    "munch chocolate", "melody chocolate", "eclairs",
    # Sauces
    "maggi hot sweet sauce", "kissan tomato ketchup", "dr oetker",
    "heinz ketchup india", "weikfield",
    # Baby food
    "nestum cerelac", "heinz baby food", "farex",
    # Salt & Sugar
    "tata salt", "annapurna salt", "catch salt", "dharampal sugar",
]


# ─────────────────────────────────────────────────────────
# Deduplication Registry
# ─────────────────────────────────────────────────────────

class ProductRegistry:
    """In-memory dedup registry by barcode and name+brand fingerprint."""

    def __init__(self):
        self._by_barcode: Dict[str, dict] = {}
        self._by_fingerprint: Dict[str, dict] = {}
        self.all_products: List[dict] = []

    def _fingerprint(self, name: str, brand: str) -> str:
        raw = re.sub(r"\s+", " ", f"{brand.lower().strip()}_{name.lower().strip()}")
        return hashlib.md5(raw.encode()).hexdigest()

    def add(self, p: dict) -> bool:
        """Returns True if product is new (not duplicate)."""
        barcode = p.get("barcode", "")
        fp = self._fingerprint(p.get("product_name",""), p.get("brand",""))

        if barcode and barcode in self._by_barcode:
            # Enrich existing with additional source info
            existing = self._by_barcode[barcode]
            if p.get("source") not in existing.get("sources", []):
                existing.setdefault("sources", []).append(p.get("source",""))
            return False

        if fp in self._by_fingerprint:
            existing = self._by_fingerprint[fp]
            existing.setdefault("sources", []).append(p.get("source",""))
            if barcode and not existing.get("barcode"):
                existing["barcode"] = barcode
            return False

        # New product
        p["sources"] = [p.get("source","")]
        p["product_id"] = fp[:12]
        if barcode:
            self._by_barcode[barcode] = p
        self._by_fingerprint[fp] = p
        self.all_products.append(p)
        return True

    def count(self) -> int:
        return len(self.all_products)


# ─────────────────────────────────────────────────────────
# Open Food Facts Scraper (v2 API - paginated)
# ─────────────────────────────────────────────────────────

OFF_SEARCH = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_FIELDS = (
    "code,product_name,product_name_en,brands,quantity,"
    "categories_tags,categories,manufacturing_places,"
    "origins,countries,image_front_url,url,_id"
)

def _parse_off_product(raw: dict, source: str = "openfoodfacts") -> Optional[dict]:
    name = (raw.get("product_name_en") or raw.get("product_name") or "").strip()
    brand = (raw.get("brands") or "").split(",")[0].strip()
    if not name or not brand:
        return None

    barcode = raw.get("code") or raw.get("_id") or ""
    weight  = raw.get("quantity") or ""
    cats    = raw.get("categories_tags") or []

    def clean_tag(t):
        return re.sub(r"^(en|fr|de):", "", t).replace("-", " ").title()

    category    = clean_tag(cats[0]) if cats else (raw.get("categories","").split(",")[0].strip())
    subcategory = clean_tag(cats[1]) if len(cats) > 1 else ""

    image_url   = raw.get("image_front_url") or ""
    product_url = (f"https://world.openfoodfacts.org/product/{barcode}"
                   if barcode else raw.get("url",""))

    return {
        "product_name": name,
        "brand": brand,
        "barcode": barcode,
        "category": category,
        "subcategory": subcategory,
        "weight": weight,
        "manufacturer": raw.get("manufacturing_places",""),
        "country_of_origin": raw.get("origins") or raw.get("countries",""),
        "product_url": product_url,
        "image_url_front": image_url,
        "source": source,
    }


def scrape_off_query(query: str, max_results: int = 50, india_only: bool = True) -> List[dict]:
    results = []
    page = 1
    page_size = min(50, max_results)

    while len(results) < max_results:
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page": page,
            "page_size": page_size,
            "fields": OFF_FIELDS,
        }
        if india_only:
            params["tagtype_0"] = "countries"
            params["tag_0"] = "en:india"

        try:
            resp = SESSION.get(OFF_SEARCH, params=params, timeout=20)
            if resp.status_code == 503:
                time.sleep(5)
                continue
            resp.raise_for_status()
            raw_list = resp.json().get("products", [])
        except Exception as e:
            logger.warning(f"OFF query '{query}' page {page} failed: {e}")
            break

        if not raw_list:
            break

        for raw in raw_list:
            p = _parse_off_product(raw)
            if p:
                results.append(p)

        if len(raw_list) < page_size:
            break
        page += 1
        time.sleep(1.2)  # polite delay

    return results[:max_results]


def scrape_off_category(category_tag: str, max_results: int = 100) -> List[dict]:
    """Use OFF category+country endpoint for broader discovery."""
    results = []
    page = 1
    url = f"https://world.openfoodfacts.org/category/{category_tag}/country/india.json"

    while len(results) < max_results:
        try:
            resp = SESSION.get(url, params={"page": page}, timeout=20)
            if resp.status_code in (404, 503):
                time.sleep(3)
                break
            resp.raise_for_status()
            raw_list = resp.json().get("products", [])
        except Exception as e:
            logger.warning(f"OFF category '{category_tag}' page {page} failed: {e}")
            break

        if not raw_list:
            break

        for raw in raw_list:
            p = _parse_off_product(raw)
            if p:
                results.append(p)

        if len(raw_list) < 20:
            break
        page += 1
        time.sleep(1.0)

    return results[:max_results]


# ─────────────────────────────────────────────────────────
# BigBasket Discovery (search endpoint)
# ─────────────────────────────────────────────────────────

from bs4 import BeautifulSoup

BB_SEARCH = "https://www.bigbasket.com/ps/?q={q}&nc=as"

def scrape_bigbasket_query(query: str, max_results: int = 30) -> List[dict]:
    results = []
    try:
        SESSION.headers["Referer"] = "https://www.bigbasket.com/"
        resp = SESSION.get(BB_SEARCH.format(q=requests.utils.quote(query)), timeout=20)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml")

        # JSON-LD or product cards
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                items = []
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    items = data.get("itemListElement", [])
                elif isinstance(data, list):
                    items = data
                for item in items:
                    prod = item.get("item") or item
                    if prod.get("@type") == "Product":
                        name = prod.get("name","").strip()
                        brand_raw = prod.get("brand", {})
                        brand = brand_raw.get("name","") if isinstance(brand_raw, dict) else str(brand_raw)
                        if name and brand:
                            results.append({
                                "product_name": name,
                                "brand": brand,
                                "barcode": prod.get("sku",""),
                                "category": "",
                                "subcategory": "",
                                "weight": "",
                                "manufacturer": "",
                                "country_of_origin": "India",
                                "product_url": prod.get("url",""),
                                "image_url_front": (prod.get("image") or [""])[0] if isinstance(prod.get("image"), list) else prod.get("image",""),
                                "source": "bigbasket",
                            })
            except Exception:
                continue

        # Fallback: anchor tags
        if not results:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/pd/" in href:
                    name = a.get_text(strip=True)
                    if name and len(name) > 3:
                        full_url = "https://www.bigbasket.com" + href if href.startswith("/") else href
                        results.append({
                            "product_name": name[:100],
                            "brand": query.split()[0].title(),
                            "barcode": "",
                            "category": "",
                            "subcategory": "",
                            "weight": "",
                            "manufacturer": "",
                            "country_of_origin": "India",
                            "product_url": full_url,
                            "image_url_front": "",
                            "source": "bigbasket",
                        })

    except Exception as e:
        logger.warning(f"BigBasket '{query}' failed: {e}")
    return results[:max_results]


# ─────────────────────────────────────────────────────────
# Report Generation
# ─────────────────────────────────────────────────────────

def write_csv(path: Path, rows: List[dict], fieldnames: List[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    console.print(f"  [green]Wrote[/green] {path.name} ({len(rows)} rows)")


def generate_reports(registry: ProductRegistry):
    products = registry.all_products
    total = len(products)

    # ── products.csv ──────────────────────────────────────
    write_csv(DATASET_DIR / "products.csv", products, [
        "product_id","product_name","brand","barcode","category","subcategory",
        "weight","manufacturer","country_of_origin","product_url","image_url_front",
        "source","sources",
    ])

    # ── products.json ─────────────────────────────────────
    (DATASET_DIR / "products.json").write_text(
        json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [green]Wrote[/green] products.json ({total} products)")

    # ── brand_summary.csv ─────────────────────────────────
    brands: Dict[str, dict] = defaultdict(lambda: {"brand": "", "product_count": 0,
        "with_barcode": 0, "categories": set()})
    for p in products:
        b = p.get("brand","Unknown")
        brands[b]["brand"] = b
        brands[b]["product_count"] += 1
        if p.get("barcode"):
            brands[b]["with_barcode"] += 1
        if p.get("category"):
            brands[b]["categories"].add(p["category"])

    brand_rows = []
    for b, d in sorted(brands.items(), key=lambda x: x[1]["product_count"], reverse=True):
        brand_rows.append({
            "brand": b,
            "product_count": d["product_count"],
            "with_barcode": d["with_barcode"],
            "without_barcode": d["product_count"] - d["with_barcode"],
            "categories": "; ".join(sorted(d["categories"])),
        })
    write_csv(REPORTS_DIR / "brand_summary.csv", brand_rows,
        ["brand","product_count","with_barcode","without_barcode","categories"])

    # ── category_summary.csv ─────────────────────────────
    cats: Dict[str, dict] = defaultdict(lambda: {"category": "", "product_count": 0,
        "with_barcode": 0, "brands": set()})
    for p in products:
        c = p.get("category","Uncategorized") or "Uncategorized"
        cats[c]["category"] = c
        cats[c]["product_count"] += 1
        if p.get("barcode"):
            cats[c]["with_barcode"] += 1
        if p.get("brand"):
            cats[c]["brands"].add(p["brand"])

    cat_rows = []
    for c, d in sorted(cats.items(), key=lambda x: x[1]["product_count"], reverse=True):
        cnt = d["product_count"]
        cat_rows.append({
            "category": c,
            "product_count": cnt,
            "with_barcode": d["with_barcode"],
            "barcode_coverage_pct": round(d["with_barcode"]/cnt*100, 1) if cnt else 0,
            "unique_brands": len(d["brands"]),
        })
    write_csv(REPORTS_DIR / "category_summary.csv", cat_rows,
        ["category","product_count","with_barcode","barcode_coverage_pct","unique_brands"])

    # ── dataset_report.json ────────────────────────────────
    with_barcode = sum(1 for p in products if p.get("barcode"))
    sources_used = sorted(set(p.get("source","") for p in products))
    report = {
        "phase": 1,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_products": total,
        "total_unique_brands": len(brands),
        "total_categories": len(cats),
        "products_with_barcode": with_barcode,
        "products_without_barcode": total - with_barcode,
        "barcode_coverage_pct": round(with_barcode/total*100, 1) if total else 0,
        "sources_used": sources_used,
        "images_collected": False,
        "metadata_enriched": False,
        "top_categories": [{"category": r["category"], "count": r["product_count"]}
                           for r in cat_rows[:10]],
        "top_brands": [{"brand": r["brand"], "count": r["product_count"]}
                       for r in brand_rows[:15]],
    }
    (REPORTS_DIR / "dataset_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [green]Wrote[/green] dataset_report.json")

    return report


# ─────────────────────────────────────────────────────────
# Main Phase 1 Runner
# ─────────────────────────────────────────────────────────

def main():
    console.rule("[bold cyan]NURE Phase 1 - Product Discovery")
    console.print("[dim]Target: Indian food products | No images | Metadata only[/dim]\n")

    registry = ProductRegistry()
    source_stats: Dict[str, int] = defaultdict(int)

    # ── Step 1: OFF Category Crawl (broadest coverage) ────
    console.print("[bold yellow]Step 1/3: Open Food Facts Category Crawl[/bold yellow]")
    off_cats_done = set()

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), MofNCompleteColumn(), console=console) as prog:
        task = prog.add_task("OFF categories", total=len(OFF_CATEGORY_TAGS))

        for category_name, tag, _ in OFF_CATEGORY_TAGS:
            prog.update(task, description=f"[cyan]OFF cat:[/cyan] {tag[:30]}")

            if tag not in off_cats_done:
                products = scrape_off_category(tag, max_results=100)
                off_cats_done.add(tag)
                new = 0
                for p in products:
                    p["category"] = p.get("category") or category_name
                    if registry.add(p):
                        new += 1
                        source_stats["openfoodfacts"] += 1
                logger.info(f"OFF cat '{tag}': {len(products)} fetched, {new} new")
            prog.advance(task)

    console.print(f"  After category crawl: [cyan]{registry.count()}[/cyan] unique products\n")

    # ── Step 2: OFF Query Search (targeted products) ───────
    console.print("[bold yellow]Step 2/3: Open Food Facts Query Search[/bold yellow]")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), MofNCompleteColumn(), console=console) as prog:
        task = prog.add_task("OFF queries", total=len(SEARCH_QUERIES))

        for query in SEARCH_QUERIES:
            prog.update(task, description=f"[cyan]Search:[/cyan] {query[:35]}")
            products = scrape_off_query(query, max_results=50, india_only=True)
            new = 0
            for p in products:
                if registry.add(p):
                    new += 1
                    source_stats["openfoodfacts"] += 1
            logger.info(f"OFF query '{query}': {len(products)} fetched, {new} new")

            # Also try without India filter for Indian brand products
            if new < 3:
                products2 = scrape_off_query(query, max_results=30, india_only=False)
                for p in products2:
                    if registry.add(p):
                        source_stats["openfoodfacts"] += 1

            prog.advance(task)

    console.print(f"  After query search: [cyan]{registry.count()}[/cyan] unique products\n")

    # ── Step 3: BigBasket Supplemental Discovery ───────────
    console.print("[bold yellow]Step 3/3: BigBasket Supplemental Discovery[/bold yellow]")

    bb_queries = [
        "maggi", "parle", "britannia", "amul", "haldiram",
        "everest masala", "aashirvaad", "tata salt", "fortune oil",
        "saffola", "dabur", "patanjali", "mtr food", "priya pickles",
        "lijjat papad", "bikaji", "bingo", "sunfeast", "hide seek",
    ]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), MofNCompleteColumn(), console=console) as prog:
        task = prog.add_task("BigBasket", total=len(bb_queries))

        for query in bb_queries:
            prog.update(task, description=f"[cyan]BB:[/cyan] {query[:35]}")
            products = scrape_bigbasket_query(query, max_results=30)
            new = 0
            for p in products:
                if registry.add(p):
                    new += 1
                    source_stats["bigbasket"] += 1
            logger.info(f"BigBasket '{query}': {len(products)} fetched, {new} new")
            prog.advance(task)
            time.sleep(2.5)

    console.print(f"  After BigBasket: [cyan]{registry.count()}[/cyan] unique products\n")

    # ── Generate Reports ───────────────────────────────────
    console.rule("[bold yellow]Generating Reports")
    report = generate_reports(registry)

    # ── Summary Table ──────────────────────────────────────
    console.rule("[bold green]Phase 1 Complete")

    table = Table(title="Phase 1 Discovery Summary", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan", min_width=35)
    table.add_column("Value", style="green", justify="right")

    table.add_row("Total Unique Products Discovered", str(report["total_products"]))
    table.add_row("Total Unique Brands", str(report["total_unique_brands"]))
    table.add_row("Total Categories", str(report["total_categories"]))
    table.add_row("Products With Barcode", f"{report['products_with_barcode']} ({report['barcode_coverage_pct']}%)")
    table.add_row("Products Without Barcode", str(report["products_without_barcode"]))
    table.add_row("Sources Used", ", ".join(report["sources_used"]))
    table.add_row("New from Open Food Facts", str(source_stats.get("openfoodfacts", 0)))
    table.add_row("New from BigBasket", str(source_stats.get("bigbasket", 0)))

    console.print(table)

    console.print("\n[bold]Top 10 Categories:[/bold]")
    for item in report["top_categories"]:
        console.print(f"  {item['category']:<40} {item['count']:>5} products")

    console.print("\n[bold]Top 15 Brands:[/bold]")
    for item in report["top_brands"]:
        console.print(f"  {item['brand']:<35} {item['count']:>5} products")

    console.print(f"\n[bold green]Output files:[/bold green]")
    console.print(f"  dataset/products.csv")
    console.print(f"  dataset/products.json")
    console.print(f"  dataset/reports/category_summary.csv")
    console.print(f"  dataset/reports/brand_summary.csv")
    console.print(f"  dataset/reports/dataset_report.json")

    console.print(f"\n[bold yellow]Phase 2 Review:[/bold yellow]")
    console.print("  Upload these 3 files for analysis:")
    console.print("  - dataset/reports/dataset_report.json")
    console.print("  - dataset/reports/category_summary.csv")
    console.print("  - dataset/reports/brand_summary.csv")


if __name__ == "__main__":
    main()
