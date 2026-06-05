"""
NURE Phase 6 - Metadata Enrichment
==================================
Targets missing Ingredients and Nutrition from multiple sources.
"""
import os, sys, json, csv, time, re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright

os.environ["PYTHONIOENCODING"] = "utf-8"

DATASET_DIR = Path("dataset")
REPORTS_DIR = DATASET_DIR / "reports"
PRODUCTS_CSV = DATASET_DIR / "products.csv"

logger.remove()
logger.add(sys.stdout, level="INFO", format="<cyan>{time:HH:mm:ss}</cyan> | <level>{level}</level> | {message}")
logger.add(DATASET_DIR / "logs" / "phase6_enrichment.log", level="DEBUG")


def _is_empty(val):
    if not val: return True
    if str(val).strip() in ["", "[]", "{}", "None", "NaN"]: return True
    return False

# ── Scrapers ──────────────────────────────────────────────

def scrape_bigbasket_metadata(query: str, page) -> dict:
    """Scrape BigBasket for Ingredients & Nutrition."""
    data = {}
    try:
        page.goto(f"https://www.bigbasket.com/ps/?q={quote_plus(query)}", timeout=10000)
        time.sleep(2)
        # Click the first product
        first_product = page.locator("a[href^='/pd/']").first
        if not first_product.is_visible():
            return data
        first_product.click()
        page.wait_for_selector("h1", timeout=5000)
        time.sleep(2)
        
        # Extract text from sections
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # BigBasket has "Ingredients", "Nutritional Facts", "About the Product"
        for section in soup.find_all("div", class_=re.compile("section", re.I)):
            text = section.get_text(" ", strip=True)
            if "Ingredients" in text and len(text) > 20 and not data.get("ingredients"):
                # Clean up the prefix
                idx = text.lower().find("ingredients")
                data["ingredients"] = text[idx:].strip()[:1000]
            if "Nutritional Facts" in text and len(text) > 20 and not data.get("nutrition"):
                idx = text.lower().find("nutritional")
                data["nutrition"] = text[idx:].strip()[:1000]
            if "About the Product" in text and len(text) > 20 and not data.get("description"):
                idx = text.lower().find("about")
                data["description"] = text[idx:].strip()[:1000]
                
    except Exception as e:
        logger.debug(f"BigBasket scrape error: {e}")
    return data


def scrape_blinkit_metadata(query: str, page) -> dict:
    """Scrape Blinkit for Ingredients & Nutrition."""
    data = {}
    try:
        page.goto(f"https://blinkit.com/s/?q={quote_plus(query)}", timeout=10000)
        time.sleep(2)
        first_product = page.locator("a[href^='/prn/']").first
        if not first_product.is_visible():
            return data
        first_product.click()
        page.wait_for_selector("h1", timeout=5000)
        time.sleep(2)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        for div in soup.find_all("div"):
            text = div.get_text(" ", strip=True)
            # Blinkit often has "Ingredients", "Nutritional Information"
            if "Ingredients" in text and len(text) > 20 and len(text) < 2000 and not data.get("ingredients"):
                data["ingredients"] = text
            if "Nutritional Information" in text and len(text) > 20 and len(text) < 2000 and not data.get("nutrition"):
                data["nutrition"] = text
    except Exception as e:
        logger.debug(f"Blinkit scrape error: {e}")
    return data


def scrape_amazon_metadata(query: str) -> dict:
    """Scrape Amazon via fast HTTP."""
    data = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = requests.get(f"https://www.amazon.in/s?k={quote_plus(query)}&i=grocery", headers=headers, timeout=5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Find first link
            link = soup.find("a", class_="a-link-normal s-no-outline")
            if link and "href" in link.attrs:
                url = "https://www.amazon.in" + link["href"]
                r2 = requests.get(url, headers=headers, timeout=5)
                if r2.status_code == 200:
                    p_soup = BeautifulSoup(r2.text, "html.parser")
                    # Look for Important information section
                    imp = p_soup.find("div", id="important-information")
                    if imp:
                        text = imp.get_text(" ", strip=True)
                        if "Ingredients" in text:
                            data["ingredients"] = text
    except Exception as e:
        pass
    return data


def get_ocr_metadata(images_dir: Path) -> dict:
    """Fallback OCR (Mock implementation unless pytesseract is installed)."""
    data = {}
    try:
        import pytesseract
        from PIL import Image
        for img_path in list(images_dir.glob("*.jpg"))[:3]:
            text = pytesseract.image_to_string(Image.open(img_path))
            if "Ingredients" in text or "INGREDIENTS" in text:
                data["ingredients"] = text.replace('\n', ' ')
            if "Nutrition" in text or "Energy" in text or "Protein" in text:
                data["nutrition"] = text.replace('\n', ' ')
    except ImportError:
        pass # Gracefully skip OCR if pytesseract is missing
    return data


# ── Main ──────────────────────────────────────────────────

def main():
    if not PRODUCTS_CSV.exists():
        logger.error("products.csv not found")
        return
        
    with open(PRODUCTS_CSV, encoding="utf-8") as f:
        products = list(csv.DictReader(f))
        
    orig_fields = list(products[0].keys())
    if "description" not in orig_fields: orig_fields.append("description")
    
    nut_before = sum(1 for p in products if not _is_empty(p.get("nutrition")))
    ing_before = sum(1 for p in products if not _is_empty(p.get("ingredients")))
    
    targets = []
    for p in products:
        if _is_empty(p.get("nutrition")) or _is_empty(p.get("ingredients")):
            targets.append(p)
            
    logger.info(f"Total products: {len(products)}")
    logger.info(f"Targeting {len(targets)} products missing metadata")
    
    success_rows = []
    failure_rows = []
    
    # Check if progress file exists to resume tracking counts
    progress_file = REPORTS_DIR / "enrichment_progress.json"
    if progress_file.exists():
        try:
            prev_prog = json.loads(progress_file.read_text(encoding="utf-8"))
            nut_before = prev_prog.get("products_missing_nutrition_before", nut_before)
            ing_before = prev_prog.get("products_missing_ingredients_before", ing_before)
        except Exception:
            pass
            
    processed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        
        for p in targets:
            brand = p.get("brand", "")
            name = p.get("product_name", "")
            query = f"{brand} {name}".strip()
            
            logger.info(f"Enriching [{processed}/{len(targets)}]: {query}")
            
            nut_added = False
            ing_added = False
            source_used = []
            
            was_nut_missing = _is_empty(p.get("nutrition"))
            was_ing_missing = _is_empty(p.get("ingredients"))
            
            # BigBasket
            bb = scrape_bigbasket_metadata(query, page)
            if bb.get("ingredients") and _is_empty(p.get("ingredients")): 
                p["ingredients"] = bb["ingredients"]
                ing_added = True
                source_used.append("BigBasket")
            if bb.get("nutrition") and _is_empty(p.get("nutrition")): 
                p["nutrition"] = bb["nutrition"]
                nut_added = True
                source_used.append("BigBasket")
            if bb.get("description") and _is_empty(p.get("description")): 
                p["description"] = bb["description"]
            
            # Blinkit
            if _is_empty(p.get("ingredients")) or _is_empty(p.get("nutrition")):
                bl = scrape_blinkit_metadata(query, page)
                if bl.get("ingredients") and _is_empty(p.get("ingredients")): 
                    p["ingredients"] = bl["ingredients"]
                    ing_added = True
                    if "Blinkit" not in source_used: source_used.append("Blinkit")
                if bl.get("nutrition") and _is_empty(p.get("nutrition")): 
                    p["nutrition"] = bl["nutrition"]
                    nut_added = True
                    if "Blinkit" not in source_used: source_used.append("Blinkit")

            # Amazon
            if _is_empty(p.get("ingredients")):
                am = scrape_amazon_metadata(query)
                if am.get("ingredients"): 
                    p["ingredients"] = am["ingredients"]
                    ing_added = True
                    if "Amazon" not in source_used: source_used.append("Amazon")
                
            # OCR Fallback
            if _is_empty(p.get("ingredients")) or _is_empty(p.get("nutrition")):
                folder = re.sub(r"_+", "_", "_".join([re.sub(r"[^a-zA-Z0-9]", "_", x) for x in [brand, name, p.get("weight","")] if x]))[:100].strip("_")
                img_dir = DATASET_DIR / "products" / folder / "images"
                if img_dir.exists():
                    ocr_data = get_ocr_metadata(img_dir)
                    if ocr_data.get("ingredients") and _is_empty(p.get("ingredients")): 
                        p["ingredients"] = ocr_data["ingredients"]
                        ing_added = True
                        if "OCR" not in source_used: source_used.append("OCR")
                    if ocr_data.get("nutrition") and _is_empty(p.get("nutrition")): 
                        p["nutrition"] = ocr_data["nutrition"]
                        nut_added = True
                        if "OCR" not in source_used: source_used.append("OCR")

            # Tracking
            if nut_added or ing_added:
                success_rows.append([name, brand, "Yes" if nut_added else "No", "Yes" if ing_added else "No", ", ".join(source_used)])
            
            still_missing_nut = _is_empty(p.get("nutrition"))
            still_missing_ing = _is_empty(p.get("ingredients"))
            
            if still_missing_nut or still_missing_ing:
                failure_rows.append([
                    name, brand, 
                    "Yes" if still_missing_nut and was_nut_missing else "No",
                    "Yes" if still_missing_ing and was_ing_missing else "No",
                    "Not found in any source"
                ])

            processed += 1
            
            # Periodically save
            if processed % 50 == 0:
                with open(PRODUCTS_CSV, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=orig_fields)
                    w.writeheader()
                    w.writerows(products)
                    
                # Update progress JSON
                curr_nut_after = sum(1 for p in products if not _is_empty(p.get("nutrition")))
                curr_ing_after = sum(1 for p in products if not _is_empty(p.get("ingredients")))
                
                prog_data = {
                    "products_missing_nutrition_before": len(products) - nut_before,
                    "products_missing_nutrition_after": len(products) - curr_nut_after,
                    "products_missing_ingredients_before": len(products) - ing_before,
                    "products_missing_ingredients_after": len(products) - curr_ing_after,
                    "nutrition_coverage_current": round((curr_nut_after / len(products)) * 100, 1),
                    "ingredients_coverage_current": round((curr_ing_after / len(products)) * 100, 1),
                    "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S")
                }
                progress_file.write_text(json.dumps(prog_data, indent=2), encoding="utf-8")
                
                # Append to reports
                mode = "a" if progress_file.exists() else "w"
                file_exists_s = (REPORTS_DIR / "enrichment_success_report.csv").exists()
                with open(REPORTS_DIR / "enrichment_success_report.csv", "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if not file_exists_s: w.writerow(["Product Name", "Brand", "Nutrition Added", "Ingredients Added", "Source Used"])
                    w.writerows(success_rows)
                success_rows = []
                
                file_exists_f = (REPORTS_DIR / "enrichment_failure_report.csv").exists()
                with open(REPORTS_DIR / "enrichment_failure_report.csv", "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if not file_exists_f: w.writerow(["Product Name", "Brand", "Missing Nutrition", "Missing Ingredients", "Reason"])
                    w.writerows(failure_rows)
                failure_rows = []
                
        browser.close()
        
    # Final save
    with open(PRODUCTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=orig_fields)
        w.writeheader()
        w.writerows(products)
        
    nut_after = sum(1 for p in products if not _is_empty(p.get("nutrition")))
    ing_after = sum(1 for p in products if not _is_empty(p.get("ingredients")))
    
    nut_pct = round((nut_after / len(products)) * 100, 1)
    ing_pct = round((ing_after / len(products)) * 100, 1)
    
    logger.info(f"Nutrition coverage: {nut_before} -> {nut_after} ({nut_pct}%)")
    logger.info(f"Ingredients coverage: {ing_before} -> {ing_after} ({ing_pct}%)")
    
    report = {
        "products_checked": len(targets),
        "nutrition_before": nut_before,
        "nutrition_after": nut_after,
        "ingredients_before": ing_before,
        "ingredients_after": ing_after,
        "nutrition_coverage_pct": nut_pct,
        "ingredients_coverage_pct": ing_pct
    }
    
    with open(REPORTS_DIR / "nutrition_enrichment_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    missing_nut = [p for p in products if _is_empty(p.get("nutrition"))]
    with open(REPORTS_DIR / "missing_nutrition_final.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Product Name", "Brand", "Barcode"])
        for p in missing_nut:
            w.writerow([p.get("product_name"), p.get("brand"), p.get("barcode")])
            
    missing_ing = [p for p in products if _is_empty(p.get("ingredients"))]
    with open(REPORTS_DIR / "missing_ingredients_final.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Product Name", "Brand", "Barcode"])
        for p in missing_ing:
            w.writerow([p.get("product_name"), p.get("brand"), p.get("barcode")])

if __name__ == "__main__":
    main()
