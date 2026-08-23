# Architecture

## Data Flow

```text
Retailer scraper (Selenium / undetected-chromedriver)
  -> parse_<retailer>_listing  ->  V2ListingSnapshot
  -> upsert_v2_listing_snapshot
       -> RetailerListing        (raw retailer record)
       -> CanonicalProduct       (persisted grouped product identity)
       -> Offer                  (retailer offer attached to a canonical product)
       -> PriceObservation       (time-series price and stock observation)
       -> MatchDecision          (how the listing attached, incl. review state)
            -> MatchDecisionEvent (audit trail of every transition)
  -> ScrapeRun                  (execution metadata and error summary)
  -> /api/v2/*                  (FastAPI read surface + React frontend)
```

## Core Models

| Model | Table | Purpose |
|---|---|---|
| `CanonicalProduct` | `canonical_products` | Grouped product identity with fingerprint, brand, parsed attributes |
| `RetailerListing` | `retailer_listings` | Raw listing as seen at a retailer, keyed by `source_url` |
| `Offer` | `offers` | Retailer offer attached to a canonical product; denormalised category/previous price for fast UI access |
| `PriceObservation` | `price_observations` | Append-only price/stock observations per offer |
| `ScrapeRun` | `scrape_runs` | Per-scraper execution metadata, counts, error summaries |
| `MatchDecision` | `match_decisions` | Latest matching state per retailer listing |
| `MatchDecisionEvent` | `match_decision_events` | Immutable audit trail: created / ingest_transition / resolved |

Catalog foreign keys carry `ON DELETE CASCADE`, so deleting canonical products or retailer listings cleans up their
dependent rows. SQLite engines created by the app register a `foreign_keys` pragma listener so cascades behave the same
as on PostgreSQL.

## Matching Pipeline

When a snapshot is ingested (`backend/app/services/v2_catalog.py`):

1. **Identity**: the listing title is parsed into brand/model, normalised strictly and loosely, and combined with
   category-specific attributes into an identity tuple whose SHA-1 prefix is the deterministic fingerprint.
2. **Exact match**: a canonical product with the same fingerprint in the same category wins immediately.
3. **Candidate ranking**: otherwise all active canonical products in the category are scored using fuzzy token ratios
   over model and name, brand agreement, shared attribute matches, and a fingerprint bonus.
   - Score >= 96 → auto-match.
   - Score >= 75 → `needs_review` queue entry with the top candidate surfaced to reviewers.
   - Otherwise a new canonical product is created.
4. **Manual state preservation**: listings with a `manual_matched` or `manual_rejected` decision keep that state across
   subsequent scrapes; only a reviewer can change it.
5. **Audit trail**: every created or changed decision writes a `MatchDecisionEvent`; manual resolutions are recorded
   with their source (`manual_review` or `bulk_review`).

## Scraping Stack

- Each retailer implements `BaseScraper.run()` using Selenium with undetected Chrome; page loads wait for expected
  selectors and detect "browser gate" challenge pages (Cloudflare etc.), waiting for them to self-clear when possible.
- Transient page load failures retry up to `SCRAPER_PAGE_LOAD_RETRIES` times with backoff; selector timeouts still
  parse partially rendered content rather than refetching.
- Shared parsing helpers live in `backend/app/utils/parsing.py`, including `extract_listing_image_url()` which handles
  `img[src]`, `img[content]`, lazy `data-src`, and CSS background-image conventions used by different retailers.
- Scrapers run concurrently under a thread pool driven by `scripts/run_scraper.py` or the optional APScheduler job
  inside the API process.

## Frontend

Single-page React app (`frontend/src/App.tsx`) organised by screen:

- Shop surfaces: Catalog, Deals, Watchlist, Alerts, Compare
- Ops surfaces: Products audit, Review Queue, Data Quality, Retailers, Scraper Health, Analytics, Settings

Data access uses TanStack Query against `/api/v2/*`. Watchlist, compare tray, and price alerts persist in
`localStorage`; everything else is server-backed.

## Repository Layout

```text
backend/
  app/
    api/          # FastAPI routers (v2)
    scrapers/     # Base scraper + one native scraper per retailer
    services/     # v2 catalog ingestion, matching, resolution logic
    utils/        # Parsing helpers, browser gate detection
    database.py   # SQLAlchemy models
    config.py     # Pydantic settings
  tests/
frontend/
  src/
alembic/versions/ # Migrations (0001 schema, 0002 cascades, 0003 audit trail)
scripts/          # init_database, run_scraper, scheduler, diagnostics, backup
```
