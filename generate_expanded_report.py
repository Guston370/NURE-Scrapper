import os, json, csv, re
from pathlib import Path
from collections import defaultdict

DATASET_DIR = Path("dataset")
PRODUCTS_DIR = DATASET_DIR / "products"
REPORTS_DIR = DATASET_DIR / "reports"
LOG_FILE = DATASET_DIR / "logs" / "phase5.log"

def generate_expanded_report():
    print("Generating expanded validation report...")
    
    # 1. Load products mapping
    products = list(csv.DictReader(open(DATASET_DIR / "products.csv", encoding="utf-8")))
    pid_to_product = {}
    import hashlib
    for p in products:
        pid = p.get("product_id") or hashlib.md5(p.get("product_name", "x").encode()).hexdigest()[:10]
        pid_to_product[pid] = p

    # 2. Parse Logs for Verified Attribution
    file_sources = {}
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                if "Verified Source Attribution" in line:
                    match = re.search(r"Product: (\w+) \| File: ([^ ]+) \| Source: (\w+) \| URL: (.*)", line)
                    if match:
                        pid, filename, source, url = match.groups()
                        file_sources[filename] = source
    except Exception as e:
        print(f"Log parsing error: {e}")

    # 3. Scan physical files
    rows = []
    total_valid = 0
    src_stats = defaultdict(int)
    total_bytes = 0
    products_processed = 0

    for d in PRODUCTS_DIR.glob("*"):
        images_dir = d / "images"
        if images_dir.exists():
            files = list(images_dir.glob("*.jpg"))
            if not files:
                continue
                
            products_processed += 1
            pid = files[0].name.split("_")[0]
            prod = pid_to_product.get(pid, {})
            name = prod.get("product_name", d.name)
            brand = prod.get("brand", "Unknown")
            cat = prod.get("category", "Unknown")
            
            p_stats = defaultdict(int)
            for f in files:
                total_bytes += f.stat().st_size
                src = file_sources.get(f.name, "unknown")
                p_stats[src] += 1
                src_stats[src] += 1
                total_valid += 1
                
            rows.append({
                "Product Name": name,
                "Brand": brand,
                "Category": cat,
                "Image Count": len(files),
                "Gap To Minimum Threshold": max(0, 10 - len(files))
            })

    # Write CSV
    csv_path = REPORTS_DIR / "coverage_gap_report.csv"
    fields = ["Product Name", "Brand", "Category", "Image Count", "Gap To Minimum Threshold"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
        
    print(f"Wrote {csv_path.name}")

    # Process metrics
    if not products_processed:
        print("No products processed yet.")
        return

    img_counts = [r["Image Count"] for r in rows]
    median_imgs = sorted(img_counts)[len(img_counts)//2]
    below_10 = len([r for r in rows if r["Image Count"] < 10])
    below_5 = len([r for r in rows if r["Image Count"] < 5])
    
    total_sources = sum(src_stats.values())
    pct = {k: f"{(v/total_sources*100):.1f}%" for k,v in src_stats.items()} if total_sources else {}
    storage_mb = total_bytes / (1024 * 1024)

    # Category checks
    cat_stats = defaultdict(list)
    for r in rows:
        cat_stats[r["Category"]].append(r["Image Count"])
    
    severe_shortage = False
    for cat, counts in cat_stats.items():
        if all(c < 10 for c in counts):
            severe_shortage = True
            break

    avg_imgs = round(total_valid / products_processed, 1)
    below_10_pct = below_10 / products_processed * 100
    
    approval_recommended = (avg_imgs >= 10) and (below_10_pct < 15) and not severe_shortage

    report = {
        "Products Processed": products_processed,
        "Average Images Per Product": avg_imgs,
        "Median Images Per Product": median_imgs,
        "Lowest Image Count": min(img_counts),
        "Highest Image Count": max(img_counts),
        "Products Below 10 Images": below_10,
        "Products Below 5 Images": below_5,
        "Source Contribution Breakdown": pct,
        "Storage Consumed": f"{storage_mb:.2f} MB",
        "Evaluation Conditions": {
            "Average >= 10": avg_imgs >= 10,
            "Below 10 Threshold < 15%": below_10_pct < 15,
            "No Severe Category Shortages": not severe_shortage,
            "RECOMMEND_APPROVAL": approval_recommended
        }
    }
    
    json_path = REPORTS_DIR / "expanded_validation_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)

    print(f"Wrote {json_path.name}")
    print(f"Recommend Approval: {approval_recommended}")

if __name__ == "__main__":
    generate_expanded_report()
