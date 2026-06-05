"""
NURE Dataset Generator - Configuration
========================================
Central config loaded from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

DATASET_ROOT      = Path(os.getenv("DATASET_ROOT", "./dataset"))
PRODUCTS_DIR      = Path(os.getenv("PRODUCTS_DIR", "./dataset/products"))
REPORTS_DIR       = Path(os.getenv("REPORTS_DIR", "./dataset/reports"))
LOGS_DIR          = Path(os.getenv("LOGS_DIR", "./dataset/logs"))
FIRESTORE_DIR     = Path(os.getenv("FIRESTORE_EXPORT_DIR", "./dataset/firestore_export"))

for _p in [DATASET_ROOT, PRODUCTS_DIR, REPORTS_DIR, LOGS_DIR, FIRESTORE_DIR]:
    _p.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Scraping
# ──────────────────────────────────────────────────────────────────────────────

MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))
REQUEST_DELAY           = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
MAX_RETRIES             = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT         = int(os.getenv("REQUEST_TIMEOUT", "30"))

# ──────────────────────────────────────────────────────────────────────────────
# Image Quality
# ──────────────────────────────────────────────────────────────────────────────

MIN_IMAGE_WIDTH           = int(os.getenv("MIN_IMAGE_WIDTH", "200"))
MIN_IMAGE_HEIGHT          = int(os.getenv("MIN_IMAGE_HEIGHT", "200"))
MAX_ASPECT_RATIO          = float(os.getenv("MAX_ASPECT_RATIO", "5.0"))
BLUR_THRESHOLD            = float(os.getenv("BLUR_THRESHOLD", "100.0"))
MIN_IMAGES_PER_PRODUCT    = int(os.getenv("MIN_IMAGES_PER_PRODUCT", "10"))
TARGET_IMAGES_PER_PRODUCT = int(os.getenv("TARGET_IMAGES_PER_PRODUCT", "25"))

# ──────────────────────────────────────────────────────────────────────────────
# Open Food Facts
# ──────────────────────────────────────────────────────────────────────────────

OFF_API_URL     = os.getenv("OPENFOODFACTS_API_URL", "https://world.openfoodfacts.org/cgi/search.pl")
OFF_APP_NAME    = os.getenv("OPENFOODFACTS_APP_NAME", "NURE-Dataset-Builder")
OFF_APP_VERSION = os.getenv("OPENFOODFACTS_APP_VERSION", "1.0.0")

# ──────────────────────────────────────────────────────────────────────────────
# Firebase
# ──────────────────────────────────────────────────────────────────────────────

FIREBASE_SA_PATH    = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO")
LOG_ROTATION = os.getenv("LOG_ROTATION", "100 MB")

# ──────────────────────────────────────────────────────────────────────────────
# HTTP Headers (generic browser simulation)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ──────────────────────────────────────────────────────────────────────────────
# Source Priority
# ──────────────────────────────────────────────────────────────────────────────

SOURCE_PRIORITY = [
    "openfoodfacts",
    "blinkit",
    "bigbasket",
    "jiomart",
    "instamart",
    "amazon_india",
    "flipkart",
]

# ──────────────────────────────────────────────────────────────────────────────
# Indian Food Categories for seed queries
# ──────────────────────────────────────────────────────────────────────────────

FOOD_CATEGORIES = {
    "Grains & Flour": [
        "atta", "maida", "suji", "besan", "rice flour", "multigrain atta",
        "wheat flour", "oats", "poha", "dalia"
    ],
    "Rice & Dal": [
        "basmati rice", "jasmine rice", "toor dal", "moong dal", "chana dal",
        "masoor dal", "urad dal", "rajma", "chhole"
    ],
    "Spices & Masala": [
        "turmeric powder", "chilli powder", "coriander powder", "cumin seeds",
        "garam masala", "biryani masala", "chicken masala", "sambar powder",
        "rasam powder", "kitchen king masala"
    ],
    "Cooking Oil": [
        "sunflower oil", "mustard oil", "groundnut oil", "coconut oil",
        "refined oil", "olive oil", "rice bran oil"
    ],
    "Dairy & Beverages": [
        "amul butter", "amul cheese", "paneer", "curd", "ghee",
        "milk powder", "condensed milk", "lassi", "buttermilk"
    ],
    "Snacks": [
        "lays chips", "kurkure", "haldiram namkeen", "bhujia", "popcorn",
        "biscuits", "crackers", "wafers", "corn flakes"
    ],
    "Instant Foods": [
        "maggi noodles", "top ramen", "yippee noodles", "instant pasta",
        "instant soup", "instant upma", "instant poha", "instant oats"
    ],
    "Sauces & Condiments": [
        "tomato ketchup", "mayonnaise", "chutney", "pickle", "vinegar",
        "soy sauce", "chilli sauce", "green sauce"
    ],
    "Health & Nutrition": [
        "protein powder", "whey protein", "health drink", "horlicks",
        "bournvita", "complan", "pediasure", "ensure"
    ],
    "Bakery": [
        "bread", "pav", "buns", "rusk", "cake", "cookies",
        "muffins", "pastry", "croissant"
    ],
    "Sugar & Sweeteners": [
        "sugar", "jaggery", "brown sugar", "honey", "stevia",
        "powdered sugar", "rock sugar"
    ],
    "Tea & Coffee": [
        "tata tea", "red label tea", "green tea", "brooke bond tea",
        "nescafe coffee", "bru coffee", "filter coffee"
    ],
    "Canned & Packaged": [
        "canned tomato", "canned beans", "coconut milk can", "mushroom can",
        "canned corn", "fruit cocktail can"
    ],
    "Baby Food": [
        "cerelac", "nestle baby food", "baby biscuit", "baby snack",
        "horlicks junior", "munchkin"
    ],
}
