"""
Playwright-based image collectors for JS-rendered ecommerce sites.
"""
import time
import re
from typing import List, Dict
from urllib.parse import quote_plus
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def collect_playwright_images(product: dict, sources: List[str], max_urls_per_source: int = 15) -> Dict[str, List[str]]:
    """
    Collect images using Playwright for the specified sources.
    Supported sources: blinkit, bigbasket, jiomart, flipkart
    """
    brand   = product.get("brand", "").strip()
    name    = product.get("product_name", "").strip()
    weight  = product.get("weight", "").strip()
    
    q_base = f"{brand} {name}".strip()
    q_wt   = f"{brand} {name} {weight}".strip() if weight else q_base

    results = {src: [] for src in sources}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        page = context.new_page()

        for src in sources:
            urls = []
            query = q_base if src != "flipkart" else q_wt # Use weight for flipkart
            
            try:
                if src == "blinkit":
                    page.goto(f"https://blinkit.com/s/?q={quote_plus(query)}", timeout=5000)
                    page.wait_for_selector("img", timeout=3000)
                    time.sleep(0.5) # let JS render images
                    images = page.locator("img").all()
                    for img in images:
                        src_attr = img.get_attribute("src") or ""
                        if re.search(r'cdn\.grofers\.com/.*?\.(jpg|jpeg|png|webp)', src_attr, re.I):
                            if src_attr not in urls:
                                urls.append(src_attr)
                        if len(urls) >= max_urls_per_source:
                            break

                elif src == "bigbasket":
                    page.goto(f"https://www.bigbasket.com/ps/?q={quote_plus(query)}", timeout=5000)
                    page.wait_for_selector("img", timeout=3000)
                    time.sleep(0.5)
                    images = page.locator("img").all()
                    for img in images:
                        src_attr = img.get_attribute("src") or ""
                        if re.search(r'(bbimages|bigbasket).*?\.(jpg|jpeg|png|webp)', src_attr, re.I):
                            if src_attr not in urls:
                                urls.append(src_attr)
                        if len(urls) >= max_urls_per_source:
                            break

                elif src == "jiomart":
                    page.goto(f"https://www.jiomart.com/search/{quote_plus(query)}", timeout=5000)
                    page.wait_for_selector("img", timeout=3000)
                    time.sleep(0.5)
                    images = page.locator("img").all()
                    for img in images:
                        src_attr = img.get_attribute("src") or ""
                        if re.search(r'jiomart.*?\.(jpg|jpeg|png|webp)', src_attr, re.I):
                            if src_attr not in urls:
                                urls.append(src_attr)
                        if len(urls) >= max_urls_per_source:
                            break

                elif src == "flipkart":
                    page.goto(f"https://www.flipkart.com/search?q={quote_plus(query)}&marketplace=GROCERY", timeout=5000)
                    page.wait_for_selector("img", timeout=3000)
                    time.sleep(0.5)
                    images = page.locator("img").all()
                    for img in images:
                        src_attr = img.get_attribute("src") or ""
                        m = re.search(r'(https://rukminim[^"]+\.(?:jpg|jpeg|png|webp))', src_attr)
                        if m:
                            raw = m.group(1)
                            hd = re.sub(r"/\d+/\d+/", "/832/832/", raw)
                            if hd not in urls:
                                urls.append(hd)
                        if len(urls) >= max_urls_per_source:
                            break
                            
            except PlaywrightTimeoutError:
                logger.debug(f"Playwright timeout for {src} on {query[:30]}")
            except Exception as e:
                logger.debug(f"Playwright error for {src}: {e}")
            
            logger.info(f"Playwright {src} '{query[:30]}': {len(urls)} URLs")
            results[src] = urls[:max_urls_per_source]

        browser.close()
    
    return results
