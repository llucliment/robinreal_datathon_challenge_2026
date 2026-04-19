"""
Generate AI image descriptions for ROBINREAL listings and save to CSV.

Images are fetched from S3 via the URLs stored in images_json.
Claude Haiku vision describes each listing's first available image.

The script is idempotent: listing_ids already present in the CSV are skipped.
Run this once; teammates then use import_robinreal_descriptions.py to load
the resulting CSV into their local listings.db.

Usage (PowerShell):
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_robinreal_descriptions.py
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_robinreal_descriptions.py --workers 8
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_robinreal_descriptions.py --limit 100
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_robinreal_descriptions.py --out data/robinreal_image_descriptions.csv

Requires: ANTHROPIC_API_KEY in environment (or .env file).
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

import anthropic
import httpx

from app.config import get_settings
from app.db import get_connection

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "robinreal_image_descriptions.csv"

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are describing a real-estate listing image for a property search engine. "
    "Write 2-3 sentences. Cover: room type, lighting (bright/dark/natural light), "
    "style (modern/rustic/classic/minimalist), condition (renovated/dated/new build), "
    "and notable visible features (parquet floor, large windows, open-plan, garden, etc.). "
    "Be factual and concise — no marketing language."
)


def _image_urls(images_json: str | None) -> list[str]:
    if not images_json:
        return []
    try:
        parsed = json.loads(images_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    urls: list[str] = []
    for item in parsed.get("images") or []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
        elif isinstance(item, str) and item:
            urls.append(item)
    return urls


def _fetch_image(url: str) -> tuple[str, str] | None:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
        ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return base64.standard_b64encode(resp.content).decode(), ct
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None


def _describe(client: anthropic.Anthropic, b64: str, media_type: str) -> str:
    response = client.messages.create(
        model=_MODEL,
        max_tokens=300,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": "Describe this listing image."},
            ],
        }],
    )
    return response.content[0].text.strip()


def _process_listing(
    listing_id: str,
    images_json: str,
    client: anthropic.Anthropic,
) -> str | None:
    urls = _image_urls(images_json)
    if not urls:
        return None
    for url in urls:
        img = _fetch_image(url)
        if img is not None:
            try:
                return _describe(client, img[0], img[1])
            except Exception as exc:
                logger.warning("Claude error on %s: %s", listing_id, exc)
                return None
    return None


def _load_existing(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["listing_id"] for row in csv.DictReader(f)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="Path to listings.db (default: from settings)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output CSV path")
    parser.add_argument("--limit", type=int, default=None, help="Max listings to process")
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers (default 5)")
    parser.add_argument("--batch-size", type=int, default=50, help="Log progress every N listings")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

    settings = get_settings()
    db_path = Path(args.db) if args.db else settings.db_path
    out_path = Path(args.out)

    if not db_path.exists():
        logger.error("DB not found: %s", db_path)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    already_done = _load_existing(out_path)
    logger.info("Already described in CSV: %d", len(already_done))

    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT listing_id, images_json
            FROM listings
            WHERE UPPER(scrape_source) = 'ROBINREAL'
              AND images_json IS NOT NULL
              AND length(images_json) > 5
            ORDER BY listing_id
            """
        ).fetchall()

    rows = [r for r in rows if r["listing_id"] not in already_done]
    if args.limit:
        rows = rows[: args.limit]

    total = len(rows)
    logger.info("Listings to describe: %d  (workers: %d)", total, args.workers)
    if total == 0:
        logger.info("Nothing to do.")
        return

    clients = [anthropic.Anthropic() for _ in range(args.workers)]

    write_lock = Lock()
    csv_file = open(out_path, "a", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)
    if len(already_done) == 0:
        writer.writerow(["listing_id", "image_description"])

    processed = skipped = 0
    start = time.time()

    def worker(row: dict, client: anthropic.Anthropic) -> tuple[str, str | None]:
        lid = row["listing_id"]
        try:
            desc = _process_listing(lid, row["images_json"], client)
            return lid, desc
        except Exception as exc:
            logger.warning("Error on %s: %s", lid, exc)
            return lid, None

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(worker, rows[i], clients[i % args.workers]): rows[i]["listing_id"]
                for i in range(len(rows))
            }
            for future in as_completed(futures):
                listing_id, description = future.result()
                if description:
                    with write_lock:
                        writer.writerow([listing_id, description])
                        csv_file.flush()
                    processed += 1
                else:
                    skipped += 1

                done = processed + skipped
                if done % args.batch_size == 0:
                    elapsed = time.time() - start
                    rate = done / elapsed
                    remaining = (total - done) / rate if rate > 0 else 0
                    logger.info(
                        "  %d/%d  described=%d  skipped=%d  ~%.0f min remaining",
                        done, total, processed, skipped, remaining / 60,
                    )
    finally:
        csv_file.close()

    logger.info(
        "Done.  Described: %d  Skipped: %d  Total: %.1f min  CSV: %s",
        processed, skipped, (time.time() - start) / 60, out_path,
    )


if __name__ == "__main__":
    main()
