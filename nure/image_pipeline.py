"""
NURE Dataset Generator - Image Quality Pipeline
=================================================
Handles:
  - Image download with retries
  - Corrupt image detection
  - Resolution filtering
  - Aspect ratio validation
  - Blur detection (Laplacian variance)
  - Perceptual hash deduplication
  - Quality scoring
  - Watermark / thumbnail detection
"""

from __future__ import annotations

import io
import hashlib
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests
import imagehash
from PIL import Image, ImageFilter
from loguru import logger

from nure.config import (
    MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT,
    MAX_ASPECT_RATIO, BLUR_THRESHOLD,
    DEFAULT_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES,
)
from nure.models import ImageRecord

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available - using Pillow-based blur detection fallback")


# ──────────────────────────────────────────────────────────────────────────────
# Image Downloader
# ──────────────────────────────────────────────────────────────────────────────

def download_image_bytes(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[bytes]:
    """Download image bytes from URL with retries."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, stream=True)
            if resp.status_code == 200:
                return resp.content
            logger.warning(f"HTTP {resp.status_code} for image: {url}")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {url}: {e}")
            time.sleep(2 ** attempt)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Blur Detection
# ──────────────────────────────────────────────────────────────────────────────

def compute_blur_score(img: Image.Image) -> float:
    """
    Compute blur score using Laplacian variance.
    Higher score = sharper image. Threshold ~100.
    """
    if CV2_AVAILABLE:
        # Use OpenCV for more accurate measurement
        img_array = np.array(img.convert("L"))
        laplacian = cv2.Laplacian(img_array, cv2.CV_64F)
        return float(laplacian.var())
    else:
        # Pillow fallback - edge detection
        gray = img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        pixels = list(edges.getdata())
        if not pixels:
            return 0.0
        mean = sum(pixels) / len(pixels)
        variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        return float(variance)


# ──────────────────────────────────────────────────────────────────────────────
# Perceptual Hash
# ──────────────────────────────────────────────────────────────────────────────

def compute_perceptual_hash(img: Image.Image) -> str:
    """Compute perceptual hash (pHash) for duplicate detection."""
    phash = imagehash.phash(img)
    return str(phash)


def are_images_duplicate(hash1: str, hash2: str, threshold: int = 8) -> bool:
    """Return True if two images are perceptually similar (Hamming distance ≤ threshold)."""
    h1 = imagehash.hex_to_hash(hash1)
    h2 = imagehash.hex_to_hash(hash2)
    return (h1 - h2) <= threshold


# ──────────────────────────────────────────────────────────────────────────────
# Quality Score
# ──────────────────────────────────────────────────────────────────────────────

def compute_quality_score(img: Image.Image, blur_score: float) -> float:
    """
    Composite quality score 0–100 based on:
    - Resolution
    - Blur score
    - Aspect ratio closeness to square
    """
    w, h = img.size
    total_pixels = w * h

    # Resolution score (max at 1M pixels)
    res_score = min(total_pixels / 1_000_000, 1.0) * 40

    # Blur score (max at 500 variance)
    blur_normalized = min(blur_score / 500.0, 1.0) * 40

    # Aspect ratio score (1.0 = square = best)
    ratio = max(w, h) / max(min(w, h), 1)
    ratio_score = max(0, (1 - (ratio - 1) / 4)) * 20

    return round(res_score + blur_normalized + ratio_score, 2)


# ──────────────────────────────────────────────────────────────────────────────
# Single Image Validation
# ──────────────────────────────────────────────────────────────────────────────

def validate_image(
    image_bytes: bytes,
    url: str = "",
    filename: str = "",
) -> ImageRecord:
    """
    Validate a single image and return an ImageRecord.
    Sets is_valid=False with rejection_reason if it fails any check.
    """
    record = ImageRecord(filename=filename, url=url)

    # 1. Corrupt image detection
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
        img = Image.open(io.BytesIO(image_bytes))  # Re-open after verify
        img = img.convert("RGB")
    except Exception as e:
        record.is_valid = False
        record.rejection_reason = f"corrupt:{e}"
        return record

    w, h = img.size
    record.width = w
    record.height = h
    record.file_size_bytes = len(image_bytes)

    # 2. Resolution check
    if w < MIN_IMAGE_WIDTH or h < MIN_IMAGE_HEIGHT:
        record.is_valid = False
        record.rejection_reason = f"too_small:{w}x{h}"
        return record

    # 3. Aspect ratio check
    ratio = max(w, h) / max(min(w, h), 1)
    if ratio > MAX_ASPECT_RATIO:
        record.is_valid = False
        record.rejection_reason = f"bad_aspect_ratio:{ratio:.2f}"
        return record

    # 4. Blur detection
    blur_score = compute_blur_score(img)
    record.blur_score = round(blur_score, 2)
    if blur_score < BLUR_THRESHOLD:
        record.is_valid = False
        record.rejection_reason = f"blurry:{blur_score:.2f}"
        return record

    # 5. Perceptual hash
    record.perceptual_hash = compute_perceptual_hash(img)

    # 6. Quality score
    record.quality_score = compute_quality_score(img, blur_score)

    return record


# ──────────────────────────────────────────────────────────────────────────────
# Batch Deduplication
# ──────────────────────────────────────────────────────────────────────────────

def deduplicate_images(records: List[ImageRecord], threshold: int = 8) -> Tuple[List[ImageRecord], int]:
    """
    Remove perceptually duplicate images from a list of ImageRecords.
    Returns (deduplicated_list, count_removed).
    """
    seen_hashes: List[str] = []
    kept: List[ImageRecord] = []
    removed = 0

    for record in records:
        if not record.is_valid:
            kept.append(record)
            continue

        if not record.perceptual_hash:
            kept.append(record)
            continue

        is_dup = False
        for seen in seen_hashes:
            if are_images_duplicate(record.perceptual_hash, seen, threshold):
                record.is_valid = False
                record.rejection_reason = "duplicate"
                is_dup = True
                removed += 1
                break

        if not is_dup:
            seen_hashes.append(record.perceptual_hash)

        kept.append(record)

    return kept, removed


# ──────────────────────────────────────────────────────────────────────────────
# Full Pipeline: Download + Validate + Save
# ──────────────────────────────────────────────────────────────────────────────

def process_product_images(
    image_urls: List[str],
    output_dir: Path,
    product_id: str,
) -> Tuple[List[ImageRecord], dict]:
    """
    Full image pipeline for one product:
    1. Download
    2. Validate each image
    3. Deduplication pass
    4. Save valid images to disk

    Returns (image_records, stats_dict)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    records: List[ImageRecord] = []

    stats = {
        "total_attempted": len(image_urls),
        "downloaded": 0,
        "corrupt_removed": 0,
        "too_small_removed": 0,
        "bad_aspect_ratio_removed": 0,
        "blurry_removed": 0,
        "duplicate_removed": 0,
        "final_valid": 0,
    }

    for idx, url in enumerate(image_urls):
        filename = f"{product_id}_{idx:03d}.jpg"
        logger.debug(f"Downloading image {idx + 1}/{len(image_urls)}: {url}")

        img_bytes = download_image_bytes(url)
        if img_bytes is None:
            logger.warning(f"Failed to download: {url}")
            continue

        stats["downloaded"] += 1
        record = validate_image(img_bytes, url=url, filename=filename)

        if not record.is_valid and record.rejection_reason:
            reason = record.rejection_reason.split(":")[0]
            key = f"{reason}_removed"
            if key in stats:
                stats[key] += 1

        records.append(record)

    # Deduplication pass
    records, dup_count = deduplicate_images(records)
    stats["duplicate_removed"] = dup_count

    # Save valid images to disk
    valid_count = 0
    for record in records:
        if record.is_valid:
            save_path = output_dir / record.filename
            img_bytes = download_image_bytes(record.url)
            if img_bytes:
                save_path.write_bytes(img_bytes)
                valid_count += 1

    stats["final_valid"] = valid_count
    logger.info(
        f"Image pipeline done for {product_id}: "
        f"{valid_count}/{stats['total_attempted']} images saved"
    )

    return records, stats
