import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv; load_dotenv()
from app.db import get_connection
from app.config import get_settings

with get_connection(get_settings().db_path) as c:
    total    = c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    with_img = c.execute("SELECT COUNT(*) FROM listings WHERE images_json IS NOT NULL AND length(images_json) > 5").fetchone()[0]
    described = c.execute("SELECT COUNT(*) FROM listings WHERE image_description IS NOT NULL AND image_description != ''").fetchone()[0]
    by_source = c.execute("SELECT scrape_source, COUNT(*) FROM listings WHERE image_description IS NOT NULL GROUP BY scrape_source").fetchall()

print(f"Total listings:        {total}")
print(f"Listings with images:  {with_img}")
print(f"Already described:     {described}")
print(f"Remaining to process:  {with_img - described}")
print()
print("Described by source:")
for row in by_source:
    print(f"  {row[0] or 'unknown':15s} {row[1]}")
