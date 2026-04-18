"""
Batch-generate AI image descriptions for listings that have images.

SRED listings use 2x2 montage images:
  top-left=bathroom, top-right=interior/salon, bottom-left=kitchen, bottom-right=exterior

RobinReal/COMPARIS listings use standard single-view photos.

Usage (PowerShell):
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_image_descriptions.py
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_image_descriptions.py --source SRED
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_image_descriptions.py --workers 8
    $env:UV_LINK_MODE="copy"; uv run python scripts/generate_image_descriptions.py --limit 500 --workers 8

The script is idempotent: only processes rows where image_description IS NULL.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import sqlite3
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

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_MONTAGE = (
    "You are describing a real-estate listing image for a property search engine. "
    "The image is a 2×2 montage: "
    "top-left = bathroom, top-right = living room / interior, "
    "bottom-left = kitchen, bottom-right = building exterior or garden. "
    "Describe each quadrant in one sentence. Be factual and specific: mention lighting "
    "(bright/dark), style (modern/rustic/classic), condition (renovated/dated/new), "
    "and notable features (parquet floor, large windows, open-plan, garden, mountain view). "
    "Format: Bathroom: <sentence>. Interior: <sentence>. Kitchen: <sentence>. Exterior: <sentence>."
)

_SYSTEM_SINGLE = (
    "You are describing a real-estate listing image for a property search engine. "
    "Write 2-3 sentences. Cover: room type, lighting (bright/dark/natural light), "
    "style (modern/rustic/classic/minimalist), condition (renovated/dated/new build), "
    "and notable visible features (parquet floor, large windows, open-plan, garden, etc.). "
    "Be factual and concise — no marketing language."
)


# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------

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


def _load_image(url: str, raw_data_dir: Path) -> tuple[str, str] | None:
    if url.startswith("/raw-data-images/"):
        filename = url.removeprefix("/raw-data-images/")
        local_path = raw_data_dir / "sred_images" / filename
        if not local_path.exists():
            return None
        data = local_path.read_bytes()
        mt = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
        return base64.standard_b64encode(data).decode(), mt

    if url.startswith("http"):
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            return base64.standard_b64encode(resp.content).decode(), ct
        except Exception as exc:
            logger.debug("HTTP fetch failed for %s: %s", url, exc)
            return None

    return None


# ---------------------------------------------------------------------------
# Claude vision
# ---------------------------------------------------------------------------

def _describe(client: anthropic.Anthropic, b64: str, media_type: str, is_montage: bool) -> str:
    system = _SYSTEM_MONTAGE if is_montage else _SYSTEM_SINGLE
    user_text = (
        "Describe each quadrant of this 2×2 montage image."
        if is_montage
        else "Describe this listing image."
    )
    response = client.messages.create(
        model=_MODEL,
        max_tokens=300,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": user_text},
            ],
        }],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Per-listing worker
# ---------------------------------------------------------------------------

def _process_listing(
    listing_id: str,
    scrape_source: str,
    images_json: str,
    raw_data_dir: Path,
    client: anthropic.Anthropic,
) -> str | None:
    """Return description string, or None if image unavailable."""
    urls = _image_urls(images_json)
    if not urls:
        return None

    img = None
    for url in urls:
        img = _load_image(url, raw_data_dir)
        if img is not None:
            break

    if img is None:
        return None

    is_montage = (scrape_source or "").upper() == "SRED"
    return _describe(client, img[0], img[1], is_montage=is_montage)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers (default 5)")
    parser.add_argument("--batch-size", type=int, default=50, help="DB commit interval (default 50)")
    parser.add_argument("--source", choices=["SRED", "COMPARIS", "all"], default="all")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

    settings = get_settings()
    db_path = Path(args.db) if args.db else settings.db_path
    raw_data_dir = settings.raw_data_dir

    if not db_path.exists():
        logger.error("DB not found at %s", db_path)
        sys.exit(1)

    with get_connection(db_path) as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()}
        if "image_description" not in existing:
            conn.execute("ALTER TABLE listings ADD COLUMN image_description TEXT")
            conn.commit()
            logger.info("Added image_description column to existing DB.")

    source_filter = f"AND UPPER(scrape_source) = '{args.source.upper()}'" if args.source != "all" else ""

    with get_connection(db_path) as conn:
        sql = f"""
            SELECT listing_id, scrape_source, images_json
            FROM listings
            WHERE images_json IS NOT NULL
              AND length(images_json) > 5
              AND (image_description IS NULL OR image_description = '')
              {source_filter}
            ORDER BY scrape_source, listing_id
        """
        if args.limit:
            sql += f" LIMIT {args.limit}"
        rows = conn.execute(sql).fetchall()

    total = len(rows)
    logger.info("Listings to describe: %d  (workers: %d)", total, args.workers)
    if total == 0:
        logger.info("Nothing to do.")
        return

    # One Anthropic client per thread
    clients = [anthropic.Anthropic() for _ in range(args.workers)]

    processed = 0
    skipped = 0
    db_lock = Lock()
    start = time.time()

    def write_result(listing_id: str, description: str) -> None:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "UPDATE listings SET image_description = ? WHERE listing_id = ?",
                [description, listing_id],
            )

    def worker(args_tuple: tuple, client: anthropic.Anthropic) -> tuple[str, str | None]:
        lid, source, img_json = args_tuple
        try:
            desc = _process_listing(lid, source, img_json, raw_data_dir, client)
            return lid, desc
        except Exception as exc:
            logger.warning("Error on %s: %s", lid, exc)
            return lid, None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(worker, (row["listing_id"], row["scrape_source"], row["images_json"]), clients[i % args.workers]): row["listing_id"]
            for i, row in enumerate(rows)
        }

        for future in as_completed(futures):
            listing_id, description = future.result()
            if description:
                write_result(listing_id, description)
                processed += 1
            else:
                skipped += 1

            done = processed + skipped
            if done % args.batch_size == 0:
                elapsed = time.time() - start
                rate = done / elapsed
                remaining = (total - done) / rate if rate > 0 else 0
                logger.info(
                    "  %d/%d  described=%d skipped=%d  ~%.0f min remaining",
                    done, total, processed, skipped, remaining / 60,
                )

    logger.info("Done.  Described: %d  Skipped: %d  Total time: %.1f min", processed, skipped, (time.time() - start) / 60)


if __name__ == "__main__":
    main()
