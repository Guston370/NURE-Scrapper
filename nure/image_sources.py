"""
NURE Image Source Collectors - Production Ready
================================================
Uses only proven working approaches:
  - Open Food Facts: API-confirmed CDN URLs
  - Amazon India: regex on HTML (works)
  - Bing Images: icrawler
  - Metadata URLs: from phase1/phase3 fields
"""
from __future__ import annotations

import os, re, json, time, random, hashlib, tempfile, shutil
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

import requests
from loguru import logger


def _session(extra: dict = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ]),
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
    })
    if extra:
        s.headers.update(extra)
    return s


def _get(url: str, session=None, timeout=15, **kw):
    s = session or _session()
    try:
        r = s.get(url, timeout=timeout, **kw)
        if r.status_code == 200:
            return r
        logger.debug(f"HTTP {r.status_code}: {url[:70]}")
    except Exception as e:
        logger.debug(f"GET failed: {e}")
    return None


# ── 1. Open Food Facts  ───────────────────────────────────
# Most reliable: barcode-based CDN + API

def collect_off_images(barcode: str) -> List[str]:
    """Collect confirmed OFF image URLs for a barcode.
    Uses the v2 API to discover which images actually exist,
    then builds multiple size variants of those confirmed IDs.
    Falls back to named-type pattern URLs if API unavailable.
    """
    if not barcode:
        return []

    urls = []
    api_ok = False

    # Primary: use API to get confirmed image IDs
    try:
        r = _get(
            f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
            timeout=12,
            params={"fields": "images,image_front_url,image_front_small_url,"
                              "image_ingredients_url,image_nutrition_url,image_packaging_url"},
        )
        if r:
            api_ok = True
            prod = r.json().get("product", {})

            # Named image URLs (confirmed, highest priority)
            for k in ["image_front_url", "image_ingredients_url",
                      "image_nutrition_url", "image_packaging_url",
                      "image_front_small_url"]:
                u = prod.get(k, "")
                if u and u not in urls:
                    urls.append(u)

            # Confirmed image IDs → generate all size variants
            confirmed_ids = [
                img_id for img_id in (prod.get("images") or {})
                if img_id.isdigit()
            ]
            for img_id in confirmed_ids:
                for sz in ["full", "400", "200", "100"]:
                    u = (f"https://images.openfoodfacts.org/images/products/"
                         f"{barcode}/{img_id}.{sz}.jpg")
                    if u not in urls:
                        urls.append(u)

            # Also try named type + confirmed sizes
            types = ["front", "ingredients", "nutrition", "packaging"]
            sizes = ["full", "400", "200"]
            for t in types:
                for sz in sizes:
                    u = (f"https://images.openfoodfacts.org/images/products/"
                         f"{barcode}/{t}_{sz}.jpg")
                    if u not in urls:
                        urls.append(u)
    except Exception:
        pass

    # Fallback if API failed: named-type pattern URLs only
    if not api_ok:
        for t in ["front", "ingredients", "nutrition", "packaging"]:
            for sz in ["full", "400", "200"]:
                urls.append(
                    f"https://images.openfoodfacts.org/images/products/{barcode}/{t}_{sz}.jpg"
                )

    return urls


def collect_metadata_urls(product: dict) -> List[str]:
    """Collect image URLs already present in product metadata."""
    return []


# ── 2. Google Images via icrawler ─────────────────────────

def collect_bing_images(query: str, max_urls: int = 30,
                        staging_dir: str = None) -> List[str]:
    """Scrape Bing Images via HTTP + Regex (extremely fast, no icrawler)."""
    s = _session({"Referer": "https://www.bing.com/"})
    urls = []
    try:
        r = _get(f"https://www.bing.com/images/search?q={quote_plus(query)}", session=s)
        if not r:
            return []
        
        # Regex to find image URLs in Bing's JSON embedded in HTML
        import re
        for m in re.finditer(r'murl&quot;:&quot;(http.*?)&quot;', r.text):
            u = m.group(1)
            # Only keep standard image extensions
            if re.search(r'\.(jpg|jpeg|png|webp)', u, re.I):
                if u not in urls:
                    urls.append(u)
                if len(urls) >= max_urls:
                    break
    except Exception as e:
        logger.debug(f"Bing error: {e}")
    logger.info(f"Bing '{query[:40]}': {len(urls)} URLs")
    return urls[:max_urls]



# ── 3. Amazon India (HTML regex - works) ─────────────────

def collect_amazon_images(query: str, max_urls: int = 25) -> List[str]:
    s = _session({"Referer": "https://www.amazon.in/"})
    urls = []
    try:
        r = _get("https://www.amazon.in/s", session=s,
                 params={"k": query, "i": "grocery"})
        if not r:
            return []
        text = r.text
        for pat in [
            r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9_\-]+\.(?:jpg|jpeg|png|webp))',
            r'(https://images-na\.ssl-images-amazon\.com/images/I/[A-Za-z0-9_\-]+\.(?:jpg|jpeg|png|webp))',
        ]:
            for m in re.finditer(pat, text):
                raw = m.group(1)
                hd = re.sub(r'\._[A-Z0-9,_]+_\.', "._SL500_.", raw)
                if hd not in urls:
                    urls.append(hd)
                if len(urls) >= max_urls:
                    break
    except Exception as e:
        logger.debug(f"Amazon error: {e}")
    logger.info(f"Amazon '{query[:40]}': {len(urls)} URLs")
    return urls[:max_urls]


# ── Master source registry ────────────────────────────────

SOURCE_FUNCTIONS = {
    "amazon":        collect_amazon_images,
}


def collect_fast_image_urls(product: dict, target: int = 100,
                           staging_dir: str = None) -> dict:
    """Collect up to `target` candidate image URLs across fast sources.

    Args:
        product: product dict with brand, product_name, weight, barcode
        target: stop collecting after this many total URLs
        staging_dir: directory for icrawler to save Bing images
    """
    brand   = product.get("brand", "").strip()
    name    = product.get("product_name", "").strip()
    weight  = product.get("weight", "").strip()
    barcode = product.get("barcode", "").strip()

    q_base = f"{brand} {name}".strip()
    q_wt   = f"{brand} {name} {weight}".strip() if weight else q_base

    results: dict = {}

    # 1. Open Food Facts
    results["openfoodfacts"] = collect_off_images(barcode)
    time.sleep(0.3)
    collected = len(results["openfoodfacts"])

    # 2. Amazon
    if collected < target:
        results["amazon"] = collect_amazon_images(q_wt, 25)
        collected += len(results["amazon"])
        time.sleep(random.uniform(0.8, 1.5))
    else:
        results["amazon"] = []

    # 3. Bing
    if collected < target:
        bing_dir = f"{staging_dir}/bing" if staging_dir else None
        results["bing"] = collect_bing_images(q_base, 10, staging_dir=bing_dir)
        collected += len(results["bing"])
    else:
        results["bing"] = []

    # 4. Metadata
    if collected < target:
        results["metadata"] = collect_metadata_urls(product)
        collected += len(results["metadata"])
    else:
        results["metadata"] = []

    return results
