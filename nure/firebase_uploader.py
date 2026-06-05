"""
NURE Firebase Uploader
========================
Uploads the scraped dataset to Firebase Firestore.
Requires FIREBASE_SERVICE_ACCOUNT_PATH in .env

Usage:
  python -m nure.firebase_uploader
  python -m nure.firebase_uploader --batch-size 100 --dry-run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

import click
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from nure.config import FIREBASE_SA_PATH, FIREBASE_PROJECT_ID, FIRESTORE_DIR, DATASET_ROOT
from nure.models import Product
from nure.storage import DatasetStorage

console = Console()


def get_firestore_client():
    """Initialize Firebase Admin SDK and return Firestore client."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if FIREBASE_SA_PATH and Path(FIREBASE_SA_PATH).exists():
                cred = credentials.Certificate(FIREBASE_SA_PATH)
            else:
                # Try application default credentials
                cred = credentials.ApplicationDefault()

            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})

        return firestore.client()
    except Exception as e:
        logger.error(f"Firebase init failed: {e}")
        raise


def upload_products_to_firestore(
    products: List[Product],
    batch_size: int = 100,
    dry_run: bool = False,
    collection: str = "products",
) -> Dict[str, int]:
    """Upload products to Firestore in batches."""
    if dry_run:
        console.print("[yellow]DRY RUN - no data will be uploaded[/yellow]")

    db = None if dry_run else get_firestore_client()

    stats = {"uploaded": 0, "skipped": 0, "errors": 0}
    total = len(products)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Uploading to Firestore/{collection}",
            total=total
        )

        # Process in batches
        for i in range(0, total, batch_size):
            batch_products = products[i:i + batch_size]

            if not dry_run:
                batch = db.batch()

            for product in batch_products:
                doc_id = product.metadata.barcode or product.metadata.product_id
                doc_data = product.to_firestore_doc()

                if dry_run:
                    stats["uploaded"] += 1
                else:
                    try:
                        ref = db.collection(collection).document(doc_id)
                        batch.set(ref, doc_data, merge=True)
                        stats["uploaded"] += 1
                    except Exception as e:
                        logger.error(f"Error preparing doc {doc_id}: {e}")
                        stats["errors"] += 1

                progress.advance(task)

            if not dry_run:
                try:
                    batch.commit()
                    logger.debug(f"Committed batch of {len(batch_products)} documents")
                except Exception as e:
                    logger.error(f"Batch commit failed: {e}")
                    stats["errors"] += len(batch_products)
                    stats["uploaded"] -= len(batch_products)

    return stats


@click.command()
@click.option("--batch-size", default=100, type=int, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--collection", default="products", show_default=True)
def upload(batch_size, dry_run, collection):
    """Upload dataset to Firebase Firestore."""
    storage = DatasetStorage()
    products = storage.load_all_products()

    if not products:
        console.print("[red]No products found in dataset.[/red]")
        return

    console.print(f"[cyan]Products to upload: {len(products)}[/cyan]")
    console.print(f"[cyan]Collection: {collection}[/cyan]")
    console.print(f"[cyan]Batch size: {batch_size}[/cyan]")

    stats = upload_products_to_firestore(
        products,
        batch_size=batch_size,
        dry_run=dry_run,
        collection=collection,
    )

    console.print(f"\n[bold green]Upload complete![/bold green]")
    console.print(f"  Uploaded: [green]{stats['uploaded']}[/green]")
    console.print(f"  Errors:   [red]{stats['errors']}[/red]")


if __name__ == "__main__":
    upload()
