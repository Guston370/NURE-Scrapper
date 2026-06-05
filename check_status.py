import json, csv, os
from pathlib import Path

rdir = Path("dataset/reports")
pdir = Path("dataset/products")

print("=" * 55)
print("NURE DATASET - PHASE COMPLETION STATUS")
print("=" * 55)

# dataset_report.json
try:
    dr = json.loads(Path("dataset/reports/dataset_report.json").read_text(encoding="utf-8"))
    print(f"\n[dataset_report.json]")
    print(f"  Phase last completed : {dr.get('phase')}")
    print(f"  Total products       : {dr.get('total_products')}")
    print(f"  Barcode coverage     : {dr.get('barcode_coverage_pct')}%")
    print(f"  Nutrition coverage   : {dr.get('nutrition_coverage_pct')}%")
    print(f"  Ingredients coverage : {dr.get('ingredients_coverage_pct')}%")
    print(f"  Metadata enriched    : {dr.get('metadata_enriched')}")
    print(f"  Images collected     : {dr.get('images_collected')}")
    print(f"  Total images         : {dr.get('total_images', 'N/A')}")
except Exception as e:
    print(f"  ERROR reading dataset_report.json: {e}")

# products.csv
try:
    rows = list(csv.DictReader(open("dataset/products.csv", encoding="utf-8")))
    print(f"\n[products.csv]")
    print(f"  Rows: {len(rows)}")
except Exception as e:
    print(f"  ERROR: {e}")

# products.json
try:
    pj = json.loads(Path("dataset/products.json").read_text(encoding="utf-8"))
    print(f"\n[products.json]")
    print(f"  Products: {len(pj)}")
except Exception as e:
    print(f"  ERROR: {e}")

# product folders
if pdir.exists():
    folders = [d for d in pdir.iterdir() if d.is_dir()]
    has_meta = sum(1 for d in folders if (d / "metadata.json").exists())
    has_info = sum(1 for d in folders if (d / "product_info.json").exists())
    imgs = sum(
        len(list((d / "images").glob("*.jpg")) + list((d / "images").glob("*.png")))
        for d in folders if (d / "images").exists()
    )
    print(f"\n[dataset/products/ folders]")
    print(f"  Total folders        : {len(folders)}")
    print(f"  With metadata.json   : {has_meta}")
    print(f"  With product_info    : {has_info}")
    print(f"  Total images on disk : {imgs}")
else:
    print("\n[dataset/products/] - NOT FOUND")

# firestore export
fe = Path("dataset/firestore_export/firestore_products.json")
print(f"\n[firestore_export]")
print(f"  Exists: {fe.exists()}")
if fe.exists():
    fd = json.loads(fe.read_text(encoding="utf-8"))
    docs = fd.get("__collections__", {}).get("products", {})
    print(f"  Documents: {len(docs)}")

# reports
print(f"\n[dataset/reports/]")
if rdir.exists():
    for r in sorted(rdir.iterdir()):
        print(f"  {r.name:<45} {r.stat().st_size:>10,} bytes")
else:
    print("  NOT FOUND")

print("\n" + "=" * 55)
print("PHASE CHECKLIST")
print("=" * 55)
p1 = Path("dataset/products.csv").exists()
p2 = Path("dataset/reports/category_summary.csv").exists()
p3 = Path("dataset/reports/missing_nutrition.csv").exists()
p4 = Path("dataset/products.json").exists()
p5 = imgs > 0 if pdir.exists() else False
p6 = Path("dataset/reports/training_readiness_report.json").exists()

print(f"  Phase 1 - Product Discovery      : {'DONE' if p1 else 'NOT DONE'}")
print(f"  Phase 2 - Cleanup & Categorize   : {'DONE' if p2 else 'NOT DONE'}")
print(f"  Phase 3 - Metadata Enrichment    : {'DONE' if p3 else 'NOT DONE'}")
print(f"  Phase 4 - Review (manual)        : READY TO REVIEW")
print(f"  Phase 5 - Image Collection       : {'DONE' if p5 else 'NOT DONE (no images yet)'}")
print(f"  Phase 6 - Final Audit            : {'DONE' if p6 else 'NOT DONE'}")
