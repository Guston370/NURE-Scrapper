"""
End-to-end test: Download and validate images for 3 real products.
Shows exactly how many images pass quality pipeline per product.
"""
import os, sys, csv, io, time
os.environ["PYTHONIOENCODING"] = "utf-8"
from pathlib import Path

import requests
from PIL import Image, ImageFilter

DATASET_DIR = Path("dataset")
products_csv = DATASET_DIR / "products.csv"

# Pick 3 well-known products with barcodes
test_products = []
with open(products_csv, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row.get("barcode") and row.get("brand") in ["Maggi", "Amul", "Britannia", "Haldiram's", "Aashirvaad"]:
            test_products.append(row)
        if len(test_products) >= 3:
            break

print(f"Testing on {len(test_products)} products:\n")

from nure.image_sources import collect_all_image_urls

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 Chrome/124"

def validate_url(url):
    try:
        if url.startswith("file:///"):
            p = Path(url[8:].replace("/", os.sep))
            raw = p.read_bytes() if p.exists() else None
        else:
            r = SESSION.get(url, timeout=8, stream=True)
            raw = r.content if r.status_code == 200 else None
        if not raw or len(raw) < 2000:
            return False, "too_small"
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if w < 200 or h < 200:
            return False, f"res_{w}x{h}"
        return True, "ok"
    except Exception as e:
        return False, str(e)[:30]

for product in test_products:
    name  = product.get("product_name","")
    brand = product.get("brand","")
    bc    = product.get("barcode","")
    print(f"{'='*60}")
    print(f"Product: {brand} - {name} | Barcode: {bc}")

    all_urls = collect_all_image_urls(product, target=60)
    total_urls = sum(len(v) for v in all_urls.values())
    print(f"URLs collected: {total_urls} across {len(all_urls)} sources")
    for src, urls in all_urls.items():
        if urls:
            print(f"  {src:<20}: {len(urls)} URLs")

    print(f"Validating (checking first 30 URLs)...")
    valid = 0
    tested = 0
    flat_urls = []
    for src, urls in all_urls.items():
        for u in urls:
            flat_urls.append((u, src))

    for url, src in flat_urls[:30]:
        ok, reason = validate_url(url)
        if ok:
            valid += 1
        tested += 1
        time.sleep(0.1)

    print(f"Result: {valid}/{tested} URLs passed quality validation")
    print(f"Estimated valid images for full run: ~{int(valid/tested * total_urls)} images\n")
