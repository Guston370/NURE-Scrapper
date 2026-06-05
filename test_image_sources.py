"""Quick test: collect image URLs for 1 product from all sources."""
import os, sys, json
os.environ["PYTHONIOENCODING"] = "utf-8"
from pathlib import Path
from nure.image_sources import (
    collect_off_images, collect_google_images, collect_bing_images,
    collect_bigbasket_images, collect_blinkit_images, collect_jiomart_images,
    collect_amazon_images, collect_flipkart_images,
)

# Pick a well-known product
product = {
    "product_name": "2 Minute Noodles Masala",
    "brand": "Maggi",
    "weight": "70g",
    "barcode": "8901058851015",
}

print(f"Testing URL collection for: {product['brand']} {product['product_name']}\n")

q = f"{product['brand']} {product['product_name']}"

tests = [
    ("Open Food Facts", lambda: collect_off_images(product["barcode"])),
    ("Google (icrawler)",lambda: collect_google_images(q, 10)),
    ("Bing (icrawler)", lambda: collect_bing_images(q, 10)),
    ("Amazon India",    lambda: collect_amazon_images(q, 15)),
    ("BigBasket",       lambda: collect_bigbasket_images(q, 15)),
    ("Blinkit",         lambda: collect_blinkit_images(q, 15)),
    ("JioMart",         lambda: collect_jiomart_images(q, 15)),
    ("Flipkart",        lambda: collect_flipkart_images(q, 15)),
]

total = 0
for name, fn in tests:
    try:
        urls = fn()
        print(f"  {name:<20} {len(urls):>3} URLs  | sample: {(urls[0][:80] if urls else 'none')}")
        total += len(urls)
    except Exception as e:
        print(f"  {name:<20}  ERROR: {e}")

print(f"\nTotal URLs collected: {total}")
print("(These are candidate URLs - quality pipeline will filter them down)")
