"""
NURE Phase 5 - PRODUCTION Image Collection Pipeline
=====================================================
Full 878-product run with resume, checkpoints, and failure tracking.
"""
import os, sys, json, csv, io, time, re, hashlib, shutil
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

os.environ["PYTHONIOENCODING"] = "utf-8"

import requests
from PIL import Image, ImageFilter
from loguru import logger
from rich.console import Console
from rich.progress import (Progress, SpinnerColumn, TextColumn,
                           BarColumn, MofNCompleteColumn, TimeElapsedColumn)

try:
    import imagehash
    PHASH_OK = True
except ImportError:
    PHASH_OK = False

from nure.image_sources import collect_fast_image_urls
from nure.playwright_sources import collect_playwright_images

console = Console()

DATASET_DIR  = Path("dataset")
REPORTS_DIR  = DATASET_DIR / "reports"
PRODUCTS_DIR = DATASET_DIR / "products"
LOGS_DIR     = DATASET_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

logger.remove()
logger.add(sys.stdout, level="WARNING",
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add(LOGS_DIR / "phase5_production.log", level="DEBUG",
    rotation="100 MB", encoding="utf-8")

# ── Quality thresholds ────────────────────────────────────
MIN_W, MIN_H    = 200, 200
MAX_RATIO       = 5.0
BLUR_THRESHOLD  = 50.0
DEDUP_THRESHOLD = 10

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
})

MIN_IMAGES = 10
TARGET_IMAGES = 20
CHECKPOINT_INTERVALS = [25, 50, 100, 250, 500, 750]

# ── Globals for tracking ──────────────────────────────────
g_total_attempted = 0
g_total_valid = 0
g_total_dup = 0
g_total_corrupt = 0
g_total_blur = 0
g_source_rows = []
g_quality_rows = []
g_failed_products = []
g_below_10 = []
g_start_time = None

# ─────────────────────────────────────────────────────────
# Quality Pipeline (same as validated pilot)
# ─────────────────────────────────────────────────────────

def _blur(img: Image.Image) -> float:
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    px = list(edges.getdata())
    if not px:
        return 0.0
    mean = sum(px) / len(px)
    return sum((p - mean) ** 2 for p in px) / len(px)


def _phash(img: Image.Image) -> Optional[str]:
    if not PHASH_OK:
        return None
    try:
        return str(imagehash.phash(img))
    except Exception:
        return None


def _is_dup(h: str, seen: List[str]) -> bool:
    if not PHASH_OK or not h:
        return False
    nh = imagehash.hex_to_hash(h)
    return any((nh - imagehash.hex_to_hash(s)) <= DEDUP_THRESHOLD for s in seen)


def download_and_validate(url: str):
    try:
        if url.startswith("file:///"):
            local_path = url[8:].replace("/", os.sep)
            p = Path(local_path)
            if not p.exists():
                return None, "file_not_found", None
            raw = p.read_bytes()
        else:
            r = SESSION.get(url, timeout=(3, 3))
            if r.status_code != 200:
                return None, f"http_{r.status_code}", None
            raw = r.content
        if len(raw) < 2000:
            return None, "too_small_bytes", None
    except Exception:
        return None, "download_error", None

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None, "corrupt", None

    w, h = img.size
    if w < MIN_W or h < MIN_H:
        return None, f"too_small_{w}x{h}", None

    ratio = max(w, h) / max(min(w, h), 1)
    if ratio > MAX_RATIO:
        return None, f"bad_ratio_{ratio:.1f}", None

    bs = _blur(img)
    if bs < BLUR_THRESHOLD:
        return None, f"blurry_{bs:.0f}", None

    return raw, "", img


def process_urls_for_product(urls_map, images_dir, pid, target,
                             seen_urls, seen_hashes, saved, source_counts, stats):
    all_urls = []
    for src, urls in urls_map.items():
        for u in urls:
            if u:
                all_urls.append((u, src))

    stats["total_attempted"] += len(all_urls)

    for url, source in all_urls:
        if saved >= target:
            break

        url_hash = hashlib.md5(url.encode()).hexdigest()
        if url_hash in seen_urls:
            continue
        seen_urls.add(url_hash)

        raw, reason, img = download_and_validate(url)

        if reason:
            key_map = {"http": "http_fail", "download": "http_fail",
                       "too": "too_small", "bad": "bad_ratio",
                       "blurry": "blurry", "corrupt": "corrupt"}
            for prefix, stat_key in key_map.items():
                if reason.startswith(prefix):
                    stats[stat_key] += 1
                    break
            continue

        stats["downloaded_ok"] += 1

        h = _phash(img)
        if h and _is_dup(h, seen_hashes):
            stats["duplicate"] += 1
            continue
        if h:
            seen_hashes.append(h)

        filename = f"{pid}_{saved:03d}.jpg"
        try:
            img.save(str(images_dir / filename), "JPEG", quality=92, optimize=True)
            saved += 1
            source_counts[source] += 1
            stats["final_valid"] += 1
            logger.info(f"Verified Source Attribution | Product: {pid} | File: {filename} | Source: {source} | URL: {url}")
        except Exception as e:
            logger.warning(f"Save failed {filename}: {e}")

        time.sleep(0.15)

    return saved


def download_product_images(product, images_dir, target=20, min_images=10):
    images_dir.mkdir(parents=True, exist_ok=True)

    pid = product.get("product_id") or hashlib.md5(
        product.get("product_name", "x").encode()).hexdigest()[:12]

    staging_dir = str(images_dir.parent / ".icrawler_staging")

    source_counts = defaultdict(int)
    stats = {"total_attempted": 0, "downloaded_ok": 0, "http_fail": 0,
             "corrupt": 0, "too_small": 0, "bad_ratio": 0,
             "blurry": 0, "duplicate": 0, "final_valid": 0}

    seen_urls = set()
    seen_hashes = []
    saved = 0

    # 1. Fast Sources
    fast_urls_map = collect_fast_image_urls(product, target=15, staging_dir=staging_dir)
    saved = process_urls_for_product(fast_urls_map, images_dir, pid, target,
                                     seen_urls, seen_hashes, saved, source_counts, stats)

    # 2. Playwright Fallback
    if saved < min_images:
        logger.info(f"Product {pid} has {saved} images (min {min_images}). Using Playwright fallback.")
        pw_sources = ["blinkit", "bigbasket", "jiomart", "flipkart"]
        pw_urls_map = collect_playwright_images(product, pw_sources, max_urls_per_source=15)
        saved = process_urls_for_product(pw_urls_map, images_dir, pid, target,
                                         seen_urls, seen_hashes, saved, source_counts, stats)

    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        pass

    return stats, dict(source_counts)


# ─────────────────────────────────────────────────────────
# Resume Support
# ─────────────────────────────────────────────────────────

def get_product_folder(product):
    brand = re.sub(r"[^a-zA-Z0-9]", "_", product.get("brand", "Unknown"))
    name  = re.sub(r"[^a-zA-Z0-9]", "_", product.get("product_name", "Unknown"))
    wt    = re.sub(r"[^a-zA-Z0-9]", "_", product.get("weight", ""))
    parts = [brand, name] + ([wt] if wt else [])
    folder = re.sub(r"_+", "_", "_".join(p for p in parts if p))[:100].strip("_")
    return PRODUCTS_DIR / folder


def is_product_complete(product):
    """Check if a product already has >= MIN_IMAGES downloaded."""
    folder = get_product_folder(product)
    images_dir = folder / "images"
    if not images_dir.exists():
        return False, 0
    count = len(list(images_dir.glob("*.jpg")))
    return count >= MIN_IMAGES, count


# ─────────────────────────────────────────────────────────
# Progress & Checkpoint Writers
# ─────────────────────────────────────────────────────────

def write_progress(total, processed, total_imgs):
    elapsed = time.time() - g_start_time
    if processed > 0:
        per_product = elapsed / processed
        remaining = total - processed
        eta_secs = remaining * per_product
        eta = str(timedelta(seconds=int(eta_secs)))
    else:
        eta = "calculating..."

    report = {
        "total_products": total,
        "processed_products": processed,
        "remaining_products": total - processed,
        "total_images": total_imgs,
        "average_images_per_product": round(total_imgs / max(processed, 1), 1),
        "estimated_completion_time": eta,
        "last_updated": datetime.now().isoformat()
    }
    path = REPORTS_DIR / "run_progress.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def write_checkpoint(idx, rows, total_p, total_valid, total_dup):
    name = f"checkpoint_{idx}.json" if idx < total_p else "final_report.json"
    path = REPORTS_DIR / name

    img_counts = [r.get("Valid Images", 0) for r in rows]
    src_stats = defaultdict(int)
    for r in rows:
        for key in ["OpenFoodFacts", "Amazon", "Bing", "Blinkit", "BigBasket", "JioMart", "Flipkart"]:
            src_stats[key] += r.get(f"{key} Count", 0)

    total_src = sum(src_stats.values())
    pct = {k: f"{v/total_src*100:.1f}%" for k,v in src_stats.items()} if total_src else {}

    report = {
        "checkpoint": idx,
        "products_processed": len(rows),
        "total_images": total_valid,
        "average_images": round(total_valid / max(len(rows), 1), 1),
        "median_images": sorted(img_counts)[len(img_counts)//2] if img_counts else 0,
        "lowest": min(img_counts) if img_counts else 0,
        "highest": max(img_counts) if img_counts else 0,
        "below_10": len([c for c in img_counts if c < 10]),
        "source_breakdown": pct,
        "duplicates_removed": total_dup,
        "timestamp": datetime.now().isoformat()
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console.print(f"  [green]Checkpoint[/green] {name}")


def write_failed_products(rows):
    path = REPORTS_DIR / "failed_products.csv"
    fields = ["Product Name", "Brand", "Failure Reason", "Attempted Sources"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_below_10(rows):
    path = REPORTS_DIR / "products_below_10_images.csv"
    fields = ["Product Name", "Brand", "Image Count", "Missing Images"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_final_dataset_report(rows, total_p, total_valid, total_dup, total_corrupt, total_blur):
    img_counts = [r.get("Valid Images", 0) for r in rows]
    src_stats = defaultdict(int)
    for r in rows:
        for key in ["OpenFoodFacts", "Amazon", "Bing", "Blinkit", "BigBasket", "JioMart", "Flipkart"]:
            src_stats[key] += r.get(f"{key} Count", 0)

    total_src = sum(src_stats.values())
    pct = {k: f"{v/total_src*100:.1f}%" for k,v in src_stats.items()} if total_src else {}

    # Physical storage
    total_bytes = 0
    for root, dirs, files in os.walk(PRODUCTS_DIR):
        if "images" in root:
            for f in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except:
                    pass
    storage_mb = total_bytes / (1024 * 1024)

    report = {
        "Total Products Processed": total_p,
        "Total Images Downloaded": total_valid,
        "Average Images Per Product": round(total_valid / max(total_p, 1), 1),
        "Median Images Per Product": sorted(img_counts)[len(img_counts)//2] if img_counts else 0,
        "Lowest Image Count": min(img_counts) if img_counts else 0,
        "Highest Image Count": max(img_counts) if img_counts else 0,
        "Products Below 10 Images": len([c for c in img_counts if c < 10]),
        "Total Storage Used": f"{storage_mb:.2f} MB",
        "Source Contribution Breakdown": pct,
        "Duplicate Images Removed": total_dup,
        "Corrupt Images Removed": total_corrupt,
        "Blur Rejections": total_blur,
        "generated_at": datetime.now().isoformat()
    }
    path = REPORTS_DIR / "final_dataset_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [green]Wrote[/green] final_dataset_report.json")


def write_firestore_readiness(products):
    missing = []
    ok = 0
    for p in products:
        issues = []
        if not p.get("product_name"): issues.append("missing product_name")
        if not p.get("brand"): issues.append("missing brand")
        if not p.get("category"): issues.append("missing category")
        if not p.get("barcode"): issues.append("missing barcode")

        folder = get_product_folder(p)
        if not (folder / "metadata.json").exists() and not (folder / "product_info.json").exists():
            issues.append("missing metadata file")

        images_dir = folder / "images"
        img_count = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0

        if issues:
            missing.append({"product": p.get("product_name",""), "issues": issues, "images": img_count})
        else:
            ok += 1

    report = {
        "total_products": len(products),
        "firestore_ready": ok,
        "products_with_issues": len(missing),
        "issues": missing[:50],  # cap for readability
        "generated_at": datetime.now().isoformat()
    }
    path = REPORTS_DIR / "firestore_readiness_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  [green]Wrote[/green] firestore_readiness_report.json")


# ─────────────────────────────────────────────────────────
# Main Production Loop
# ─────────────────────────────────────────────────────────

def main():
    global g_start_time, g_total_attempted, g_total_valid, g_total_dup
    global g_total_corrupt, g_total_blur

    console.rule("[bold cyan]NURE Phase 5 - PRODUCTION Dataset Collection")

    products_csv = DATASET_DIR / "products.csv"
    if not products_csv.exists():
        console.print("[red]products.csv not found.[/red]")
        return

    with open(products_csv, encoding="utf-8") as f:
        products = list(csv.DictReader(f))

    total = len(products)
    console.print(f"Total products : [cyan]{total}[/cyan]")
    console.print(f"Min images     : [cyan]{MIN_IMAGES}[/cyan]")
    console.print(f"Target images  : [cyan]{TARGET_IMAGES}[/cyan]")

    # Count already completed
    skipped = 0
    for p in products:
        complete, count = is_product_complete(p)
        if complete:
            skipped += 1
    console.print(f"Already done   : [cyan]{skipped}[/cyan]")
    console.print(f"Remaining      : [cyan]{total - skipped}[/cyan]\n")

    g_start_time = time.time()
    processed = 0

    # Initialize progress file
    write_progress(total, 0, 0)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as prog:
        task = prog.add_task("Collecting images", total=total)

        try:
            for i, product in enumerate(products):
                pname = product.get("product_name", "Unknown")[:35]
                pbrand = product.get("brand", "")[:15]
                prog.update(task, description=f"[cyan]{pbrand}[/cyan] {pname}")

                folder = get_product_folder(product)
                images_dir = folder / "images"

                # RESUME: skip completed products
                complete, existing_count = is_product_complete(product)
                if complete:
                    # Record as skipped in stats
                    sc = defaultdict(int)
                    sc["resumed"] = existing_count
                    _record_product(product, {"total_attempted":0,"downloaded_ok":existing_count,
                                              "http_fail":0,"corrupt":0,"too_small":0,
                                              "bad_ratio":0,"blurry":0,"duplicate":0,
                                              "final_valid":existing_count},
                                    dict(sc), "skipped_resume")
                    g_total_valid += existing_count
                    processed += 1
                    prog.advance(task)
                    continue

                # DOWNLOAD
                try:
                    stats, source_counts = download_product_images(
                        product, images_dir, TARGET_IMAGES, MIN_IMAGES)
                except Exception as e:
                    logger.error(f"Fatal error on {pname}: {e}")
                    g_failed_products.append({
                        "Product Name": product.get("product_name", ""),
                        "Brand": product.get("brand", ""),
                        "Failure Reason": str(e)[:200],
                        "Attempted Sources": "all"
                    })
                    processed += 1
                    prog.advance(task)
                    continue

                g_total_valid += stats["final_valid"]
                g_total_dup += stats["duplicate"]
                g_total_corrupt += stats["corrupt"]
                g_total_blur += stats["blurry"]
                g_total_attempted += stats["total_attempted"]

                status = "done" if stats["final_valid"] >= MIN_IMAGES else "below_min"
                _record_product(product, stats, source_counts, status)

                if stats["final_valid"] == 0:
                    g_failed_products.append({
                        "Product Name": product.get("product_name", ""),
                        "Brand": product.get("brand", ""),
                        "Failure Reason": "zero images from all sources",
                        "Attempted Sources": ",".join(source_counts.keys()) if source_counts else "all"
                    })

                if stats["final_valid"] < MIN_IMAGES:
                    g_below_10.append({
                        "Product Name": product.get("product_name", ""),
                        "Brand": product.get("brand", ""),
                        "Image Count": stats["final_valid"],
                        "Missing Images": MIN_IMAGES - stats["final_valid"]
                    })

                processed += 1
                prog.advance(task)

                # Progress update every 25
                if processed % 25 == 0:
                    write_progress(total, processed, g_total_valid)

                # Checkpoints
                if processed in CHECKPOINT_INTERVALS:
                    write_checkpoint(processed, g_source_rows, total,
                                     g_total_valid, g_total_dup)

                # Console update every 100
                if processed % 100 == 0:
                    console.print(f"\n  [bold green]Progress: {processed}/{total}[/bold green] | "
                                  f"Images: {g_total_valid} | "
                                  f"Avg: {g_total_valid/max(processed,1):.1f} | "
                                  f"Failed: {len(g_failed_products)} | "
                                  f"Below 10: {len(g_below_10)}\n")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Writing reports for processed items...[/yellow]")

    # ── Final Reports ─────────────────────────────────────
    console.rule("[bold yellow]Writing Final Reports")

    write_progress(total, processed, g_total_valid)
    write_checkpoint(processed, g_source_rows, total, g_total_valid, g_total_dup)
    write_failed_products(g_failed_products)
    write_below_10(g_below_10)
    write_final_dataset_report(g_source_rows, processed, g_total_valid,
                               g_total_dup, g_total_corrupt, g_total_blur)
    write_firestore_readiness(products)

    console.print(f"\n[bold green]Phase 5 PRODUCTION complete![/bold green]")
    console.print(f"  Products processed: {processed}/{total}")
    console.print(f"  Total images: {g_total_valid}")
    console.print(f"  Failed: {len(g_failed_products)}")
    console.print(f"  Below 10: {len(g_below_10)}")


def _record_product(product, stats, source_counts, status):
    valid = stats["final_valid"]
    sr = {
        "Product Name":        product.get("product_name", ""),
        "Brand":               product.get("brand", ""),
        "Category":            product.get("category", ""),
        "OpenFoodFacts Count": source_counts.get("openfoodfacts", 0),
        "Amazon Count":        source_counts.get("amazon", 0),
        "Bing Count":          source_counts.get("bing", 0),
        "Blinkit Count":       source_counts.get("blinkit", 0),
        "BigBasket Count":     source_counts.get("bigbasket", 0),
        "JioMart Count":       source_counts.get("jiomart", 0),
        "Flipkart Count":      source_counts.get("flipkart", 0),
        "Valid Images":        valid,
        "Duplicates Removed":  stats["duplicate"],
    }
    g_source_rows.append(sr)

    qr = {
        "product_name":       product.get("product_name", ""),
        "brand":              product.get("brand", ""),
        "total_attempted":    stats["total_attempted"],
        "downloaded_ok":      stats["downloaded_ok"],
        "duplicates_removed": stats["duplicate"],
        "blurry_removed":     stats["blurry"],
        "corrupt_removed":    stats["corrupt"],
        "too_small_removed":  stats.get("too_small", 0),
        "final_valid_images": valid,
        "status":             status,
    }
    g_quality_rows.append(qr)


if __name__ == "__main__":
    main()
