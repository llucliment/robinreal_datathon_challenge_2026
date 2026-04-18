# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a datathon challenge harness for **RobinReal**, a real-estate listing search and ranking system. Given a natural-language query, the system extracts hard constraints (must-haves) and soft preferences, filters a SQLite database of Swiss property listings, then ranks results by relevance.

The competition objective is search quality and ranking effectiveness. Teams implement logic inside `app/participant/` — everything else is harness infrastructure.

## Commands

**Install dependencies** (Python, uses `uv`):
```bash
UV_LINK_MODE=copy uv sync --dev
```
> The project lives in OneDrive which doesn't support hardlinks; `UV_LINK_MODE=copy` is required. Prefix all `uv run` commands with it too.

**Run the FastAPI backend** (port 8000):
```bash
uv run uvicorn app.main:app --reload
```

**Run the MCP server** (port 8001):
```bash
uv run uvicorn apps_sdk.server.main:app --reload --port 8001
```

**Run all tests**:
```bash
uv run pytest tests -q
```

**Run a single test file**:
```bash
uv run pytest tests/test_hard_filters.py -q
```

**Build the React widget** (from `apps_sdk/web/`):
```bash
npm install && npm run build
```

**Docker (full stack)**:
```bash
docker compose up --build
```

## Architecture

### Search Pipeline

```
POST /listings (NL query)
  → hard_fact_extraction.py   # parse must-have constraints → HardFilters
  → hard_filters.py           # SQL queries against SQLite
  → soft_fact_extraction.py   # parse nice-to-have preferences
  → soft_filtering.py         # optional post-filter candidates
  → ranking.py                # score and sort → RankedListingResult[]
```

`POST /listings/search/filter` takes a pre-built `HardFilters` struct and skips the extraction step.

### Key Directories

- **`app/participant/`** — The five extension points teams implement. All are stubs except `listing_row_parser.py` which is fully implemented.
- **`app/harness/`** — Bootstrap (CSV→SQLite import on startup), search service orchestration, SRED data normalization.
- **`app/core/`** — `hard_filters.py` (SQL filter builder, 80+ filter types) and `s3.py` (AWS image URL resolution).
- **`app/api/routes/listings.py`** — Two endpoints: `POST /listings` and `POST /listings/search/filter`.
- **`apps_sdk/server/`** — FastMCP server bridging Claude/ChatGPT to the FastAPI backend via the `search_listings` tool.
- **`apps_sdk/web/`** — React 19 + Vite widget with ranked list and MapLibre GL map.

### Data Flow on Startup

`bootstrap.py` runs during FastAPI lifespan: scans `raw_data/*.csv`, parses each row via `listing_row_parser.prepare_listing_row()`, and imports into a single `listings` SQLite table (~38 columns). DB path defaults to `./data/listings.db`.

### Participant Extension Points

| File | Input | Output |
|------|-------|--------|
| `hard_fact_extraction.py` | query `str` | `HardFilters` |
| `soft_fact_extraction.py` | query `str` | `dict` (team-defined) |
| `soft_filtering.py` | candidates, soft facts | filtered candidates |
| `ranking.py` | candidates, soft facts | `list[RankedListingResult]` |
| `listing_row_parser.py` | CSV row `dict` | parsed listing row — **already implemented** |

### Environment Variables

```bash
LISTINGS_RAW_DATA_DIR=./raw_data        # CSV source directory
LISTINGS_DB_PATH=./data/listings.db     # SQLite output path

# Optional — AWS S3 image access
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=eu-central-2
LISTINGS_S3_BUCKET=crawl-data-951752554117-eu-central-2-an

# MCP server
APPS_SDK_LISTINGS_API_BASE_URL=http://localhost:8000
APPS_SDK_PUBLIC_BASE_URL=http://localhost:8001
```

## Hard Filters Reference

Supported structured filter fields on `HardFilters`: `city`, `postal_code`, `canton`, `latitude`/`longitude`/`radius_km`, `min_price`/`max_price`, `min_rooms`/`max_rooms`, `offer_type` (RENT/SALE), `object_category`, `object_type`, `sort_by` (price_asc/desc, rooms_asc/desc), `limit` (1–500, default 25), `offset`. Boolean features: `balcony`, `elevator`, `parking`, `garage`, `fireplace`, `child_friendly`, `pets_allowed`, `temporary`, `new_build`, `wheelchair_accessible`, `private_laundry`, `minergie_certified`.
