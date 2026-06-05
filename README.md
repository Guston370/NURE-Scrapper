# NURE Food Product Dataset Generator

> A production-ready, modular food product dataset generation system for computer vision, barcode lookup, nutrition analysis, and mobile scanning applications.

---

## 📁 Project Structure

```
WebScrapper_bar/
├── main.py                          # CLI entry point
├── quickstart_demo.py               # Quick demo script
├── requirements.txt
├── .env.example                     # Config template
│
├── nure/
│   ├── __init__.py
│   ├── config.py                    # Central configuration
│   ├── models.py                    # Pydantic data models
│   ├── logger.py                    # Loguru logging setup
│   ├── pipeline.py                  # Main orchestrator
│   ├── storage.py                   # Dataset I/O engine
│   ├── reporter.py                  # Report generator
│   ├── image_pipeline.py            # Image quality pipeline
│   ├── validator.py                 # Dataset structure validator
│   ├── firebase_uploader.py         # Firestore upload
│   └── scrapers/
│       ├── __init__.py              # Scraper registry
│       ├── base.py                  # Abstract base scraper
│       ├── openfoodfacts.py         # Open Food Facts (primary)
│       ├── bigbasket.py             # BigBasket
│       ├── blinkit.py               # Blinkit
│       └── jiomart.py               # JioMart
│
└── dataset/                         # Generated dataset (auto-created)
    ├── products/
    │   └── {ProductName_Brand_Weight}/
    │       ├── images/
    │       ├── metadata.json
    │       └── product_info.json
    ├── products.csv                  # Master inventory
    ├── products.json                 # Full structured data
    ├── logs/
    ├── reports/
    │   ├── dataset_report.json
    │   ├── training_readiness_report.json
    │   ├── brand_summary.csv
    │   ├── category_summary.csv
    │   ├── barcode_coverage.csv
    │   ├── nutrition_coverage.csv
    │   ├── ingredients_coverage.csv
    │   ├── missing_barcodes.csv
    │   ├── missing_nutrition.csv
    │   ├── missing_ingredients.csv
    │   ├── image_quality_report.csv
    │   └── duplicate_images_report.csv
    └── firestore_export/
        └── firestore_products.json
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```powershell
cd e:\ML\WebScrapper_bar
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment

```powershell
copy .env.example .env
# Edit .env with your settings (Firebase config is optional)
```

### 3. Run the Demo (Fastest)

```powershell
python quickstart_demo.py
```

This uses the Open Food Facts public API - no authentication needed, no scraping barriers.

---

## 🛠️ CLI Commands

### Full Pipeline (All Sources)

```powershell
python main.py scrape
python main.py scrape --sources openfoodfacts,bigbasket --max-per-query 100
python main.py scrape --skip-images   # Metadata only, faster
```

### Open Food Facts Bulk (Recommended Start)

```powershell
python main.py scrape-off
python main.py scrape-off --max-per-category 500 --skip-images
```

### Generate Reports Only (from existing dataset)

```powershell
python main.py reports
```

### Export Master Files

```powershell
python main.py export
```

### Validate Dataset

```powershell
python main.py validate
```

### Barcode Lookup

```powershell
python main.py barcode 8901063150217
python main.py barcode 8901063150217 --save
```

### List Available Sources

```powershell
python main.py list-sources
```

### Upload to Firebase

```powershell
python -m nure.firebase_uploader
python -m nure.firebase_uploader --dry-run        # Test without uploading
python -m nure.firebase_uploader --batch-size 50
```

---

## 📊 Generated Reports

| File | Description |
|------|-------------|
| `dataset_report.json` | Overall stats: totals, coverage, completion % |
| `training_readiness_report.json` | ML readiness scores (0–100) per task |
| `brand_summary.csv` | Per-brand product count, image count, coverage |
| `category_summary.csv` | Per-category coverage statistics |
| `barcode_coverage.csv` | Barcode availability per product |
| `nutrition_coverage.csv` | Nutrition data availability |
| `ingredients_coverage.csv` | Ingredient list availability |
| `missing_barcodes.csv` | All products without barcodes |
| `missing_nutrition.csv` | All products without nutrition data |
| `missing_ingredients.csv` | All products without ingredient lists |
| `image_quality_report.csv` | Per-product image quality stats |
| `duplicate_images_report.csv` | All removed duplicate images |

---

## 🔌 Adding New Scrapers

1. Create `nure/scrapers/mysource.py` extending `BaseScraper`
2. Implement `search_products()` and `get_product_details()`
3. Register in `nure/scrapers/__init__.py`:

```python
from nure.scrapers.mysource import MySourceScraper

SCRAPER_REGISTRY["mysource"] = MySourceScraper
```

4. Use via CLI: `python main.py scrape --sources mysource`

---

## 🗂️ Dataset Structure

### metadata.json

```json
{
  "product_id": "abc123def456",
  "product_name": "Whole Wheat Atta",
  "brand": "Aashirvaad",
  "barcode": "8901063150217",
  "category": "Grains & Flour",
  "subcategory": "Atta",
  "weight": "5 kg",
  "manufacturer": "ITC Limited",
  "source": "openfoodfacts",
  "product_url": "https://world.openfoodfacts.org/product/8901063150217",
  "image_count": 18,
  "folder_name": "Whole_Wheat_Atta_Aashirvaad_5_kg",
  "scraping_status": "success",
  "created_at": "2026-06-03T14:00:00Z"
}
```

### product_info.json

```json
{
  "ingredients": ["Whole Wheat Flour"],
  "nutrition": {
    "energy_kcal": 341,
    "protein_g": 12.5,
    "carbohydrates_g": 69.4,
    "fat_g": 1.7,
    "dietary_fiber_g": 11.0
  },
  "allergens": ["Gluten"],
  "description": "Stone Ground Whole Wheat Atta",
  "country_of_origin": "India",
  "storage_information": "Store in a cool dry place",
  "fssai_information": "FSSAI Lic. No. 10014022000385"
}
```

---

## 🔥 Firestore Schema

**Collection:** `products`  
**Document ID:** `barcode` (or `product_id` if barcode unavailable)

```json
{
  "product_name": "Maggi 2 Minute Noodles",
  "brand": "Maggi",
  "barcode": "8901058855908",
  "category": "Instant Foods",
  "ingredients": ["Wheat Flour", "Edible Vegetable Oil", "Salt"],
  "nutrition": { "energy_kcal": 390, "protein_g": 8.0 },
  "image_urls": ["https://..."],
  "source": "openfoodfacts"
}
```

---

## 📈 ML Training Readiness Scores

The `training_readiness_report.json` provides readiness scores (0–100) for:

| Task | Minimum Score |
|------|---------------|
| Product Classification | ≥ 70 |
| Product Detection | ≥ 70 |
| OCR Recognition | ≥ 70 |
| Barcode Lookup | ≥ 70 |
| Mobile Camera Recognition | ≥ 70 |

---

## ⚙️ Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATASET_ROOT` | `./dataset` | Root output directory |
| `MIN_IMAGE_WIDTH` | `200` | Minimum image width (px) |
| `MIN_IMAGE_HEIGHT` | `200` | Minimum image height (px) |
| `BLUR_THRESHOLD` | `100.0` | Laplacian variance blur threshold |
| `MIN_IMAGES_PER_PRODUCT` | `10` | Minimum images required |
| `TARGET_IMAGES_PER_PRODUCT` | `25` | Target images per product |
| `REQUEST_DELAY_SECONDS` | `2.0` | Delay between requests |
| `MAX_RETRIES` | `3` | HTTP retry count |
| `MAX_CONCURRENT_REQUESTS` | `5` | Concurrent request limit |

---

## 📋 Success Criteria Checklist

- [x] Product-level dataset (one folder per product)
- [x] ML-friendly folder names (`Brand_Product_Weight`)
- [x] `metadata.json` per product
- [x] `product_info.json` per product (ingredients, nutrition, allergens)
- [x] Image quality pipeline (blur, dedup, resolution, corrupt detection)
- [x] Resume capability (skip already-scraped products)
- [x] `products.csv` master inventory
- [x] `products.json` full structured data
- [x] Firestore-ready export (`firestore_products.json`)
- [x] 12 audit/analytics reports generated
- [x] Training readiness scoring (0–100 per task)
- [x] Modular scraper architecture (add sources easily)
- [x] Retry logic, rate limiting, error handling
- [x] Logging with rotation
- [x] Dataset validation command
- [x] Firebase Firestore uploader

---

## 🔒 Ethical Scraping

- Respects `robots.txt` and rate limits (2s+ delay between requests)
- Uses official public APIs where available (Open Food Facts)
- Dataset is for research/ML purposes only
- Do not scrape at high frequency — use `--max-per-query` responsibly
