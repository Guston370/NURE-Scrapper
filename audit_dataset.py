import os, csv, json
from pathlib import Path
import re

DATASET_DIR = Path('dataset')
PRODUCTS_CSV = DATASET_DIR / 'products.csv'
REPORTS_DIR = DATASET_DIR / 'reports'
PRODUCTS_DIR = DATASET_DIR / 'products'

products = list(csv.DictReader(open(PRODUCTS_CSV, encoding='utf-8')))

audit = {
    'products_with_real_nutrition': 0,
    'products_with_placeholder_nutrition': 0,
    'products_with_real_ingredients': 0,
    'products_with_placeholder_ingredients': 0,
    'products_with_real_images': 0,
    'products_with_mock_images': 0,
    'total_real_images': 0,
    'total_mock_images': 0
}

fake_nut = []
fake_ing = []
fake_img = []

for p in products:
    brand = re.sub(r'[^a-zA-Z0-9]', '_', p.get('brand', 'Unknown'))
    name  = re.sub(r'[^a-zA-Z0-9]', '_', p.get('product_name', 'Unknown'))
    wt    = re.sub(r'[^a-zA-Z0-9]', '_', p.get('weight', ''))
    parts = [brand, name] + ([wt] if wt else [])
    folder = re.sub(r'_+', '_', '_'.join(x for x in parts if x))[:100].strip('_')
    
    nut = str(p.get('nutrition', '')).strip()
    is_empty_nut = not nut or nut in ['', '[]', '{}', 'None', 'NaN'] or "'energy_kcal': None" in nut
    
    if nut == 'Energy: 100kcal':
        audit['products_with_placeholder_nutrition'] += 1
        fake_nut.append(p)
    elif not is_empty_nut:
        audit['products_with_real_nutrition'] += 1
        
    ing = str(p.get('ingredients', '')).strip()
    is_empty_ing = not ing or ing in ['', '[]', '{}', 'None', 'NaN']
    
    if ing == 'Water, Sugar':
        audit['products_with_placeholder_ingredients'] += 1
        fake_ing.append(p)
    elif not is_empty_ing:
        audit['products_with_real_ingredients'] += 1

    img_dir = PRODUCTS_DIR / folder / 'images'
    real_img_count = 0
    mock_img_count = 0
    has_mock = False
    
    if img_dir.exists():
        for f in img_dir.glob('*.jpg'):
            if f.name.startswith('mock_'):
                mock_img_count += 1
                has_mock = True
            else:
                real_img_count += 1
                
    audit['total_real_images'] += real_img_count
    audit['total_mock_images'] += mock_img_count
    
    if real_img_count > 0:
        audit['products_with_real_images'] += 1
    if has_mock:
        audit['products_with_mock_images'] += 1
        fake_img.append({**p, 'mock_images_count': mock_img_count, 'real_images_count': real_img_count})

with open(REPORTS_DIR / 'dataset_integrity_report.json', 'w', encoding='utf-8') as f:
    json.dump(audit, f, indent=2)

with open(REPORTS_DIR / 'placeholder_nutrition_products.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Product Name', 'Brand', 'Barcode'])
    for p in fake_nut: w.writerow([p.get('product_name'), p.get('brand'), p.get('barcode')])
    
with open(REPORTS_DIR / 'placeholder_ingredients_products.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Product Name', 'Brand', 'Barcode'])
    for p in fake_ing: w.writerow([p.get('product_name'), p.get('brand'), p.get('barcode')])
    
with open(REPORTS_DIR / 'mock_image_products.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Product Name', 'Brand', 'Barcode', 'Mock Images Count', 'Real Images Count'])
    for p in fake_img: w.writerow([p.get('product_name'), p.get('brand'), p.get('barcode'), p.get('mock_images_count'), p.get('real_images_count')])

total = len(products)
real_nut_cov = (audit['products_with_real_nutrition'] / total) * 100
real_ing_cov = (audit['products_with_real_ingredients'] / total) * 100
real_img_cov = (audit['products_with_real_images'] / total) * 100
real_avg_img = audit['total_real_images'] / max(1, audit['products_with_real_images'])

print(f'1. Real nutrition coverage %: {real_nut_cov:.1f}%')
print(f'2. Real ingredients coverage %: {real_ing_cov:.1f}%')
print(f'3. Real image coverage %: {real_img_cov:.1f}%')
print(f'4. Real average images per product: {real_avg_img:.1f}')
