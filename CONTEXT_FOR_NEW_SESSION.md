# Context for New Claude Session — RobinReal Datathon 2026

## What this project is

A datathon challenge submission. We are building **RobinReal**: a Swiss real-estate search and ranking system. Given a natural-language query like "cheap 3-room apartment near ETH Zurich", the system extracts hard constraints (city, rooms, price), filters a SQLite database of ~22,000 Swiss listings, then ranks results by soft preferences (quietness, brightness, affordability relative to filtered pool, transit proximity).

**The backend is fully implemented and deployed.** The current session task is building the frontend.

---

## Current deployment state

- **Public API URL:** `https://summary-lawrence-essays-stock.trycloudflare.com`  
  ⚠️ This URL changes every time the Cloudflare tunnel restarts. It is running on a colleague's laptop via Docker + cloudflared tunnel. When you start a new session, ask the user for the current URL.

- **Docker image:** `juanlobl/robinreal:latest` on Docker Hub (public)
- **To restart the server on colleague's laptop:**
  ```bash
  # Terminal 1
  docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... juanlobl/robinreal:latest
  # Terminal 2 (after "Application startup complete")
  npx cloudflared tunnel --url http://localhost:8000
  ```

---

## Backend API — what the frontend calls

**Base URL:** the tunnel URL above (store in a config constant, not hardcoded everywhere)

### `POST /listings` — main search endpoint
```json
// Request
{ "query": "cheap 3-room apartment in Zurich", "limit": 25, "offset": 0 }

// Response
{
  "listings": [
    {
      "listing_id": "10001",
      "score": 0.74,
      "reason": "+ quiet, bright | ~ transport | below-average price",
      "listing": {
        "id": "10001",
        "title": "Wohnung an ruhiger Lage",
        "description": "...",
        "city": "Zürich",
        "canton": "ZH",
        "latitude": 47.37,
        "longitude": 8.54,
        "price_chf": 2200,
        "rooms": 3.0,
        "living_area_sqm": 75,
        "available_from": "2025-06-01",
        "image_urls": ["https://..."],
        "hero_image_url": "https://...",
        "features": ["balcony", "elevator"],
        "offer_type": "RENT",
        "object_category": "APARTMENT"
      }
    }
  ],
  "meta": { "user_id": null, "profile_applied": false }
}
```

### `POST /listings/search/filter` — structured filter endpoint
```json
// Request
{
  "hard_filters": {
    "city": ["Zurich"],
    "min_rooms": 2.0,
    "max_price": 3000,
    "offer_type": "RENT",
    "limit": 25,
    "offset": 0
  }
}
```

### `GET /health` — health check → `{"status": "ok"}`
### `GET /health/detailed` — shows if API key is set

### `POST /interactions` — log user interaction (for personalization bonus)
```json
{ "user_id": "user123", "listing_id": "10001", "event_type": "click", "query": "cheap flat" }
```

---

## Frontend task — what needs to be built

**Goal:** A standalone React search UI that anyone can open in a browser, type a query, and see ranked results with a map.

**What already exists** in `apps_sdk/web/src/`:
- `App.tsx` — layout shell (sidebar + map panel), currently wired to MCP/ChatGPT events only
- `components/RankedList.tsx` — listing cards with image carousel, score, reason, features — fully built
- `components/ListingsMap.tsx` — MapLibre GL map with pins — fully built
- `styles.css` — complete styling

**What needs to be added:**
1. A search bar (text input + submit button) at the top of the sidebar
2. A `fetch` call to `POST /listings` on submit
3. Loading state while waiting for results
4. Error state if the API fails
5. The API base URL as a config constant (not hardcoded in every component)

**Key constraint:** the existing `RankedList` and `ListingsMap` components must not be broken — they already work perfectly for the MCP use case and for our new use case.

**Tech stack:** React 19 + TypeScript + Vite (already set up in `apps_sdk/web/`)

**To run locally:**
```bash
cd apps_sdk/web
npm install
npm run dev   # dev server at http://localhost:5173
```

**To build for production:**
```bash
npm run build  # outputs to apps_sdk/web/dist/
```

---

## Backend architecture (for reference)

```
POST /listings
  → hard_fact_extraction.py   # Claude haiku extracts city/rooms/price/area/date → HardFilters
  → hard_filters.py           # SQL query on SQLite, fetches 200 candidates (pool for price stats)
  → soft_fact_extraction.py   # Claude haiku extracts preferences/landmark/ideal_description
  → soft_filtering.py         # scores each candidate on preferences, Nominatim geocoding,
                              #   transport.opendata.ch transit times, price relative to pool
  → ranking.py                # sentence-transformers embedding score + weighted sum → sorted
  → slice [offset:offset+limit]  # return top N to user
```

**Important design decision:** We fetch 200 candidates from SQL (not just 25) so that price statistics are representative of the full filtered market. "Cheap 3-room" means cheap among all 3-room apartments, not just the first 20 returned.

---

## Reason text format

Each result has a `reason` string like:
```
+ quiet, bright | ~ transport | - garden | below-average price | ~12 min by transit
```
- `+` = strong match (score ≥ 0.65)
- `~` = moderate match (0.35–0.65)  
- `-` = missing/weak (< 0.35)
- `below-average price` / `above-average price` = price relative to filtered pool
- `~N min by transit` = transit time to landmark via transport.opendata.ch

---

## User personalization (bonus feature — already implemented)

Pass `user_id` in the request body to enable personalization:
```json
{ "query": "...", "limit": 25, "user_id": "user123" }
```
The system:
1. Saves query history with time-decay (halflife 7 days)
2. Merges historical preferences into current soft criteria
3. Generates an LLM user profile after enough interactions
4. Applies profile boost to ranking (city affinity, feature affinity, budget match)

---

## Key files

| File | Purpose |
|------|---------|
| `app/participant/hard_fact_extraction.py` | LLM + regex fallback for hard constraints |
| `app/participant/soft_fact_extraction.py` | LLM extraction of soft preferences |
| `app/participant/soft_filtering.py` | Score candidates against soft criteria |
| `app/participant/ranking.py` | Weighted scoring + embedding + reason building |
| `app/harness/search_service.py` | Pipeline orchestration, 200-candidate pool |
| `app/models/schemas.py` | All Pydantic models (HardFilters, ListingData, etc.) |
| `apps_sdk/web/src/App.tsx` | React app shell — needs search bar added here |
| `apps_sdk/web/src/components/RankedList.tsx` | Listing cards — already complete |
| `apps_sdk/web/src/components/ListingsMap.tsx` | Map — already complete |

---

## What's done / what's next

### Done ✓
- Full search pipeline (hard extraction → SQL filter → soft scoring → embedding rerank)
- User history with time-decay preference aggregation
- LLM user profile boost (colleague's contribution, merged)
- Price scoring relative to filtered candidate pool (not all 22K listings)
- Transit-time scoring via transport.opendata.ch
- Nominatim geocoding with Switzerland retry fallback
- Sentence-transformers semantic similarity (all-MiniLM-L6-v2, pre-warmed)
- CORS enabled on API (any origin allowed)
- Docker image built and pushed to Docker Hub
- Public API running via Cloudflare tunnel
- 43/43 tests passing

### Next: Frontend
- Add search bar to `App.tsx`
- Wire fetch call to `POST /listings`
- Deploy frontend to Vercel or Netlify (free, instant)
- Build presentation slides

---

## Datathon submission requirements

1. ✅ Working prototype at public HTTPS API route — done (tunnel URL)
2. ⬜ Demo/app showing full result flow — **this is the frontend task**
3. ⬜ Final presentation slides

**Jury evaluates:** correctness, relevance quality, originality, practical usefulness, demo quality.  
**Peer reviewers test:** perceived usefulness, search experience.

---

## Environment / setup notes

- Python project managed with `uv` (not pip directly)
- **Must prefix all uv commands with `UV_LINK_MODE=copy`** on Windows/OneDrive
- SQLite DB is at `data/listings.db` (331MB, gitignored)
- Raw CSV data is in `raw_data/` (gitignored)
- `.env` file holds `ANTHROPIC_API_KEY` locally
- Docker image embeds the pre-built DB — no CSV import on startup
