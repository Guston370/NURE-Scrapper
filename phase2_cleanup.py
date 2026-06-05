"""
NURE Phase 2 - Dataset Cleanup
================================
Fixes category pollution, removes non-Indian brands,
normalizes brand names, and re-exports products.csv.

Run: python -X utf8 phase2_cleanup.py
"""
import os, sys, json, csv, re
from pathlib import Path
from collections import defaultdict

os.environ["PYTHONIOENCODING"] = "utf-8"
from rich.console import Console
from rich.table import Table

console = Console()
DATASET_DIR = Path("dataset")
REPORTS_DIR = DATASET_DIR / "reports"

# ── Brands to REMOVE (non-Indian / irrelevant) ──────────
BLOCKED_BRANDS = {
    "Harry & David", "Harry And David", "Walkers", "Picard", "Thiriet",
    "Carrefour", "Lidl", "LIDL", "Aldi", "Aldi-Benner Company", "Tesco", "TESCO",
    "Sainsbury's", "Sinsbury's", "Woolworths", "Coles", "Waitrose", "Asda",
    "Morrison's", "Marks & Spencer", "Marks & Spencers", "Super U", "Monoprix",
    "Leclerc", "LECLERC", "E.Leclerc", "Delhaize", "Albert Heijn", "Lidl",
    "Auchan", "Carabreizh", "Jardin bio", "Sojasun", "Pural", "Andros",
    "Vahiné", "Vahine", "Sainte Lucie", "La Belle Aude", "Rians",
    "Bon Gelati", "Cremissimo", "Blue Ribbon", "Arla", "ja!", "Paturages",
    "Ker Ronan", "Thornbridge", "La Vie Claire", "Mövenpick", "HDG",
    "Invitation à la Ferme", "Invitation A La Ferme", "la maison guiot",
    "Picard", "Bio Village", "Albona", "Cook", "Elodie", "Andros",
    "Tartefrais", "L'Eclair de Génie", "L'Éclair de Génie", "AMO ESSERE",
    "peripella", "Hafner", "Carrefour Le Marché", "Boni", "Pallas",
    "Adélie", "Délifrance", "Poppies", "La Lorraine", "GIE BPGR",
    "Superior on Main", "Kez's", "Karima karamel", "Werther's Original",
    "Cachafaz", "Misura", "BelVita", "Belvita", "Gullón", "Freee",
    "Mayver's", "Uncle Ray's", "Uncle Rye's", "Uncle Rays  Llc",
    "Uncle Rays  Llc.", "Uncle Ray's  Llc", "Uncle Ray's  Llc,",
    "Uncle Saba's lentil and chickpea chips", "Uncle Wally's Bake Shoppe",
    "Munch Better", "Munchies/Hostess", "Munchies Doritos", "Munch!",
    "#Munch", "Hashtag munch", "Hashtag Munch", "Keto Munch", "Munch Mellows",
    "Matt's Munchies", "Mom's Munchies", "Green Mustache", "Bulk",
    "Safe Catch", "Bob's Red Mill", "Trader Joe's", "Star Markets Co.",
    "Harris Teeter", "Aurora Products", "Foodhold", "Choice Foods Llc",
    "Broderick's", "Zarubi", "Hamutag", "Waymouth Farms", "Alani",
    "Conagra Brands", "Frito Lay", "FritoLay", "Frito Lays", "Doritos",
    "Cheetos", "Kettle", "Mt. Olive", "Goya", "Natco", "TRS", "Top Op",
    "Schani", "Jaimin", "Bodrum", "Cosmoveda", "Laila", "East End",
    "Reishunger", "Zursun", "Ceren", "Shana", "CO-OP Gold", "AP",
    "Ali Baba", "Town Bus", "Suraj", "Rimpy", "Roshni", "Khazana",
    "Pattu", "Kasturi", "Jiva Organic", "LuLu", "Katoomba", "Aseer",
    "Falcon", "Bodrum", "Aldi", "Sainsbury's", "Sanitarium",
    "Sanitarium Up & Go Protein Energize", "SO Good", "Up&Go",
    "Kellogg's", "Weetabix", "Sunsol", "BC", "Pams", "Griffin's",
    "Nutty Naturals Holdings", "NamedSport", "Prozis", "Cereales Andinos",
    "Munch Better", "CBL MUNCHEE", "Tiffany", "Adoro", "Monaco", "Roma",
    "Arnott's", "ARNOTT'S", "Arnotts", "Arnott's Tim Tam", "Uncle Tobys",
    "Uncle Toby's", "UNCLE TOBYS", "All Stars", "The Happy Snack Company",
    "Dairy Farmers", "Téashop", "Teashop", "Adma International Ltd",
    "Balocco S.P.A.", "Crawford's", "Tower Gate", "Láma tuffnut",
    "Harvest Morn", "Carabreizh", "Mcvities", "Misura",
    "Jam n' jims", "Jim Jams", "Favorina", "Milky Way", "Milka",
    "Milkybar", "KitKat", "Oreo", "Mondelez International",
    "Aldi-Benner Company", "334006", "transfood", "haira", "Munch Better",
    "Crio Inc.", "Crio Bru", "Plenish", "Dr. Oetker", "Dr. Oetker Ristorante",
    "Dr. Oetker Vitalis", "Dr Oetker Ristorante", "Dr. Oetker Die Ofenfrische",
    "Danone", "Nutricia", "Nestlé Health Science",
}

# ── Brand Name Normalization ─────────────────────────────
BRAND_NORMALIZE = {
    r"(?i)^britannia.*$": "Britannia",
    r"(?i)^daawat.*$": "Daawat",
    r"(?i)^nescaf[eé].*$": "Nescafe",
    r"(?i)^haldiram.*$": "Haldiram's",
    r"(?i)^lipton.*$": "Lipton",
    r"(?i)^maggi.*$": "Maggi",
    r"(?i)^knorr.*$": "Knorr",
    r"(?i)^mcviti.*$": "McVitie's",
    r"(?i)^tata.*salt.*$": "Tata Salt",
    r"(?i)^tata.*tea.*$": "Tata Tea",
    r"(?i)^tata$": "Tata",
    r"(?i)^act\s*ii?$": "ACT II",
    r"(?i)^india\s*gate.*$": "India Gate",
    r"(?i)^kohinoor.*$": "Kohinoor",
    r"(?i)^wagh\s*bakri.*$": "Wagh Bakri",
    r"(?i)^continental.*$": "Continental",
    r"(?i)^sunfeast.*$": "Sunfeast",
    r"(?i)^itc.*$": "ITC",
    r"(?i)^bru$": "Bru",
    r"(?i)^cadbury.*$": "Cadbury",
    r"(?i)^amul.*$": "Amul",
    r"(?i)^mother\s*dairy.*$": "Mother Dairy",
    r"(?i)^nandini.*$": "Nandini",
    r"(?i)^everest.*$": "Everest",
    r"(?i)^mdh.*$": "MDH",
    r"(?i)^catch.*$": "Catch",
    r"(?i)^sakthi.*$": "Sakthi",
    r"(?i)^eastern.*$": "Eastern",
    r"(?i)^dhara.*$": "Dhara",
    r"(?i)^fortune.*$": "Fortune",
    r"(?i)^sundrop.*$": "Sundrop",
    r"(?i)^saffola.*$": "Saffola",
    r"(?i)^horlick.*$": "Horlicks",
    r"(?i)^complan.*$": "Complan",
    r"(?i)^pediasure.*$": "PediaSure",
    r"(?i)^protinex.*$": "Protinex",
    r"(?i)^abbott.*$": "Abbott",
    r"(?i)^abbot.*$": "Abbott",
    r"(?i)^kissan.*$": "Kissan",
    r"(?i)^ching.*$": "Ching's Secret",
    r"(?i)^mtr.*$": "MTR",
    r"(?i)^aashirvaad.*$": "Aashirvaad",
    r"(?i)^pillsbury.*$": "Pillsbury",
    r"(?i)^bikaji.*$": "Bikaji",
    r"(?i)^bikano.*$": "Bikano",
    r"(?i)^balaji.*$": "Balaji",
    r"(?i)^bingo.*$": "Bingo",
    r"(?i)^top\s*ramen.*$": "Top Ramen",
    r"(?i)^yippee.*$": "Yippee",
    r"(?i)^nissin.*$": "Nissin",
    r"(?i)^daawat.*$": "Daawat",
    r"(?i)^verka.*$": "Verka",
    r"(?i)^parle.*$": "Parle",
    r"(?i)^red\s*label.*$": "Red Label",
    r"(?i)^weikfield.*$": "Weikfield",
    r"(?i)^heinz.*$": "Heinz",
    r"(?i)^nestle.*$": "Nestle",
}

# ── Category Mapping (clean OFF tags → Indian categories) ─
CATEGORY_MAP = {
    "Uncategorized": None,  # re-derive from subcategory/brand
    "Plant Based Foods And Beverages": None,
    "Beverages And Beverages Preparations": "Beverages",
    "Snacks": "Snacks & Namkeen",
    "Dairies": "Dairy",
    "Baby Foods": "Baby Food",
    "Meals": "Ready-to-Eat",
    "Condiments": "Sauces & Condiments",
    "Dietary Supplements": "Health & Nutrition",
    "Desserts": "Desserts & Ice Cream",
    "Frozen Foods": "Frozen Foods",
    "Breakfasts": "Breakfast Cereals",
    "Sweeteners": "Sugar & Sweeteners",
    "Namkeen": "Snacks & Namkeen",
    "Food Additives": "Other",
    "Indian Readymeals": "Ready-to-Eat",
    "Meats And Their Products": "Meat & Seafood",
    "Nutritional Supplement": "Health & Nutrition",
    "Nutritional Shake": "Health & Nutrition",
    "Cocoa And Its Products": "Chocolates & Confectionery",
    "Seafood": "Meat & Seafood",
    "Oils": "Cooking Oil",
    "Ricebran Oil": "Cooking Oil",
    "Cooking Oil": "Cooking Oil",
    "Fats": "Dairy",
    "Masala": "Spices & Masala",
    "Spice Blends": "Spices & Masala",
    "Dal Makhani": "Ready-to-Eat",
    "Cooking Helpers": "Sauces & Condiments",
    "Health Drinks": "Health & Nutrition",
    "Nutritional Drink": "Health & Nutrition",
    "Balanced Nutritional Drink": "Health & Nutrition",
    "Beverage Mix": "Beverages",
}

# ── Brand → Category inference ────────────────────────────
BRAND_CATEGORY = {
    "Aashirvaad": "Grains & Flour",
    "Pillsbury": "Grains & Flour",
    "Fortune": "Grains & Flour",
    "India Gate": "Grains & Flour",
    "Daawat": "Grains & Flour",
    "Kohinoor": "Grains & Flour",
    "Saffola": "Cooking Oil",
    "Dhara": "Cooking Oil",
    "Sundrop": "Cooking Oil",
    "Emami": "Cooking Oil",
    "Everest": "Spices & Masala",
    "MDH": "Spices & Masala",
    "Catch": "Spices & Masala",
    "Sakthi": "Spices & Masala",
    "Eastern": "Spices & Masala",
    "Badshah": "Spices & Masala",
    "Amul": "Dairy",
    "Mother Dairy": "Dairy",
    "Nandini": "Dairy",
    "Verka": "Dairy",
    "Horlicks": "Health & Nutrition",
    "Complan": "Health & Nutrition",
    "Bournvita": "Health & Nutrition",
    "PediaSure": "Health & Nutrition",
    "Protinex": "Health & Nutrition",
    "Abbott": "Health & Nutrition",
    "Britannia": "Biscuits & Bakery",
    "McVitie's": "Biscuits & Bakery",
    "Parle": "Biscuits & Bakery",
    "Sunfeast": "Biscuits & Bakery",
    "Maggi": "Instant Foods & Noodles",
    "Yippee": "Instant Foods & Noodles",
    "Top Ramen": "Instant Foods & Noodles",
    "Nissin": "Instant Foods & Noodles",
    "Knorr": "Instant Foods & Noodles",
    "Ching's Secret": "Sauces & Condiments",
    "Kissan": "Sauces & Condiments",
    "Weikfield": "Sauces & Condiments",
    "Haldiram's": "Snacks & Namkeen",
    "Bikaji": "Snacks & Namkeen",
    "Bikano": "Snacks & Namkeen",
    "Balaji": "Snacks & Namkeen",
    "Bingo": "Snacks & Namkeen",
    "ACT II": "Snacks & Namkeen",
    "Lipton": "Tea & Coffee",
    "Tata Tea": "Tea & Coffee",
    "Red Label": "Tea & Coffee",
    "Wagh Bakri": "Tea & Coffee",
    "Nescafe": "Tea & Coffee",
    "Bru": "Tea & Coffee",
    "Continental": "Tea & Coffee",
    "Heinz": "Baby Food",
    "MTR": "Ready-to-Eat",
    "Tata Salt": "Salt & Sugar",
    "ITC": "Snacks & Namkeen",
    "Cadbury": "Chocolates & Confectionery",
}

JUNK_CATEGORY_PATTERNS = re.compile(
    r"^(Hhhhj|Null|Pois\s|Fertiggericht|Getrocknete|Nouilles|Inst$|"
    r"Undefined|Assortiments|Bbq\s|Popcorn\sWith|Tata\sSalt$|Posicle|"
    r"Badam\sMilk|Energy$|Salted\sSnacks|Chocolate\sBiscuit|"
    r"Oat\sCookies|Spicy\sPotato|Ricebran)", re.I)


def normalize_brand(brand: str) -> str:
    for pattern, normalized in BRAND_NORMALIZE.items():
        if re.match(pattern, brand):
            return normalized
    return brand.strip()


def assign_category(product: dict, brand: str) -> str:
    raw_cat = product.get("category", "") or ""

    # Junk category → re-derive
    if not raw_cat or JUNK_CATEGORY_PATTERNS.match(raw_cat):
        return BRAND_CATEGORY.get(brand, "Other")

    # Map known OFF categories
    mapped = CATEGORY_MAP.get(raw_cat)
    if mapped is None:
        # Brand-based fallback for broad categories
        return BRAND_CATEGORY.get(brand, raw_cat)
    return mapped


def is_indian_relevant(product: dict, brand: str) -> bool:
    """Keep only products relevant to Indian market."""
    if brand in BLOCKED_BRANDS:
        return False
    # Keep if brand is a known Indian brand
    if brand in BRAND_CATEGORY:
        return True
    # Keep if country_of_origin mentions India
    coo = (product.get("country_of_origin") or "").lower()
    if "india" in coo:
        return True
    # Keep if OFF tagged as Indian
    url = product.get("product_url", "")
    if "openfoodfacts" in url:
        return True  # was already India-filtered in Phase 1
    return True  # default keep, blocked brands already filtered above


def main():
    console.rule("[bold cyan]NURE Phase 2 - Dataset Cleanup")

    products_csv = DATASET_DIR / "products.csv"
    if not products_csv.exists():
        console.print("[red]products.csv not found. Run Phase 1 first.[/red]")
        return

    with open(products_csv, encoding="utf-8") as f:
        raw_products = list(csv.DictReader(f))

    console.print(f"Input: [cyan]{len(raw_products)}[/cyan] products")

    kept, removed = [], []
    brand_counts = defaultdict(int)

    for p in raw_products:
        brand_raw = p.get("brand", "").strip()
        brand = normalize_brand(brand_raw)
        p["brand"] = brand

        if not is_indian_relevant(p, brand):
            removed.append(p)
            continue

        p["category"] = assign_category(p, brand)
        brand_counts[brand] += 1
        kept.append(p)

    console.print(f"Kept: [green]{len(kept)}[/green] | Removed: [red]{len(removed)}[/red]")

    # Deduplicate by normalized brand+name
    seen = set()
    deduped = []
    for p in kept:
        key = f"{p['brand'].lower()}_{p['product_name'].lower()[:40]}"
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    console.print(f"After dedup: [cyan]{len(deduped)}[/cyan] products")

    # Re-export
    all_keys = list(deduped[0].keys()) if deduped else []
    with open(products_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(deduped)
    console.print(f"  [green]Updated[/green] products.csv")

    # Regenerate category_summary
    cats = defaultdict(lambda: {"category": "", "product_count": 0, "with_barcode": 0, "brands": set()})
    for p in deduped:
        c = p.get("category","Other") or "Other"
        cats[c]["category"] = c
        cats[c]["product_count"] += 1
        if p.get("barcode"):
            cats[c]["with_barcode"] += 1
        cats[c]["brands"].add(p.get("brand",""))

    cat_rows = []
    for c, d in sorted(cats.items(), key=lambda x: x[1]["product_count"], reverse=True):
        n = d["product_count"]
        cat_rows.append({
            "category": c,
            "product_count": n,
            "with_barcode": d["with_barcode"],
            "barcode_coverage_pct": round(d["with_barcode"]/n*100,1) if n else 0,
            "unique_brands": len(d["brands"]),
        })

    REPORTS_DIR.mkdir(exist_ok=True)
    with open(REPORTS_DIR / "category_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["category","product_count","with_barcode","barcode_coverage_pct","unique_brands"])
        w.writeheader()
        w.writerows(cat_rows)
    console.print(f"  [green]Updated[/green] category_summary.csv")

    # Regenerate brand_summary
    brands_d = defaultdict(lambda: {"brand":"","product_count":0,"with_barcode":0,"categories":set()})
    for p in deduped:
        b = p.get("brand","Unknown")
        brands_d[b]["brand"] = b
        brands_d[b]["product_count"] += 1
        if p.get("barcode"):
            brands_d[b]["with_barcode"] += 1
        brands_d[b]["categories"].add(p.get("category",""))

    brand_rows = []
    for b, d in sorted(brands_d.items(), key=lambda x: x[1]["product_count"], reverse=True):
        brand_rows.append({
            "brand": b,
            "product_count": d["product_count"],
            "with_barcode": d["with_barcode"],
            "without_barcode": d["product_count"] - d["with_barcode"],
            "categories": "; ".join(sorted(d["categories"])),
        })

    with open(REPORTS_DIR / "brand_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["brand","product_count","with_barcode","without_barcode","categories"])
        w.writeheader()
        w.writerows(brand_rows)
    console.print(f"  [green]Updated[/green] brand_summary.csv")

    # Summary table
    table = Table(title="Post-Cleanup Dataset", header_style="bold cyan")
    table.add_column("Metric", style="cyan", min_width=30)
    table.add_column("Value", style="green", justify="right")
    total = len(deduped)
    wb = sum(1 for p in deduped if p.get("barcode"))
    table.add_row("Total Products", str(total))
    table.add_row("Total Unique Brands", str(len(brands_d)))
    table.add_row("Total Categories", str(len(cats)))
    table.add_row("With Barcode", f"{wb} ({wb/total*100:.1f}%)" if total else "0")
    table.add_row("Removed (non-Indian)", str(len(removed)))
    console.print(table)

    console.print("\n[bold yellow]Top Categories After Cleanup:[/bold yellow]")
    for row in cat_rows[:15]:
        console.print(f"  {row['category']:<40} {row['product_count']:>5} products | {row['unique_brands']} brands")

    console.print("\n[bold green]Cleanup complete. Run Phase 3 next:[/bold green]")
    console.print("  python -X utf8 phase3_metadata.py")


if __name__ == "__main__":
    main()
