import csv, os
os.environ["PYTHONIOENCODING"] = "utf-8"
from pathlib import Path
from collections import Counter

rows = list(csv.DictReader(open("dataset/products.csv", encoding="utf-8")))
cats = Counter(r.get("category","") for r in rows)
has_barcode = sum(1 for r in rows if r.get("barcode","").strip())
has_weight  = sum(1 for r in rows if r.get("weight","").strip())
print(f"Total products : {len(rows)}")
print(f"With barcode   : {has_barcode}")
print(f"With weight    : {has_weight}")
print(f"Categories     : {len(cats)}")
print("Top 10 categories:")
for c, n in cats.most_common(10):
    print(f"  {c:<42} {n}")
