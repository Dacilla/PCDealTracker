# PCDealTracker

PCDealTracker tracks Australian PC hardware pricing across multiple retailers.
The project is currently in transition from a legacy scraper-plus-merge system to a persisted `v2` catalog built around retailer listings, canonical products, offers, and price observations.

## Overview

- Backend: FastAPI + SQLAlchemy
- Frontend: React + Vite + TypeScript
- Databases: SQLite for local development, PostgreSQL for containerized/runtime use
- Scraping: Selenium / undetected-chromedriver in the legacy layer, with native `v2` ingestion being rolled out retailer by retailer

## Current Status

### Done

- Repaired major legacy blockers that previously made the repo unreliable:
  - broken merged-product endpoint file
  - broken merged-product rebuild path
  - config crash on invalid `DEBUG` values
  - import-time schema creation and Redis flush side effects
  - inconsistent local frontend/backend host assumptions
  - flaky API tests caused by in-memory SQLite lifecycle issues
- Added a persisted `v2` schema with Alembic migrations.
- Added `v2` API endpoints for products, offers, history, filters, and trends.
- Replaced the old single-file frontend with a React/Vite/TypeScript frontend.
- Added native `v2` ingestion paths for:
  - Centre Com
  - Computer Alliance
  - Shopping Express
  - Scorptec
  - JW Computers
- Updated the legacy backfill so those native-`v2` retailers are excluded by default.

### Still To Do

- Port the remaining retailers off the legacy `Product` bridge and into native `v2` ingestion.
- Add fixture-based scraper contract tests so parser changes do not depend on live sites.
- Reduce dependence on the old Selenium-heavy scraper layer.
- Add clearer operational tooling around scrape runs, ambiguous matches, and manual review.
- Keep evolving the persisted catalog and matching pipeline so more logic moves out of read-time derivation.

## Architecture

### Legacy Flow

```text
Retailer scraper
  -> Product
  -> PriceHistory
  -> merged product rebuild
  -> legacy API
```

### `v2` Flow

```text
Retailer scraper
  -> RetailerListing
  -> CanonicalProduct
  -> Offer
  -> PriceObservation
  -> MatchDecision / ScrapeRun
  -> /api/v2/*
```

### Key `v2` Models

- `CanonicalProduct`: persisted grouped product identity
- `RetailerListing`: raw retailer listing record
- `Offer`: retailer offer attached to a canonical product
- `PriceObservation`: time-series price/in-stock observation
- `ScrapeRun`: scrape execution metadata
- `MatchDecision`: record of how a listing was attached to a canonical product

## Repository Layout

```text
backend/
  app/
    api/
    scrapers/
    services/
    utils/
    database.py
  tests/
frontend/
scripts/
alembic/
```

## Requirements

- Python 3.13+ recommended
- Node.js 20+ recommended
- A local virtual environment for backend dependencies
- Chrome/Chromium compatible with the Selenium setup if running scrapers

## Local Development

### Backend

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn backend.app.main:app --reload
```

Backend URLs:

- API docs: `http://localhost:8000/docs`
- Legacy API: `http://localhost:8000/api/v1/*`
- `v2` API: `http://localhost:8000/api/v2/*`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- `http://localhost:5173`

## Docker

```bash
docker-compose up --build
```

Services:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

## Database Migrations

Alembic manages the persisted `v2` schema.

```bash
venv\Scripts\activate
alembic upgrade head
```

Current `v2` tables created by migration:

- `canonical_products`
- `retailer_listings`
- `offers`
- `price_observations`
- `scrape_runs`
- `match_decisions`

## Backfill

To populate the persisted `v2` catalog from legacy `products` and `price_history` data:

```bash
venv\Scripts\activate
python scripts/backfill_v2_catalog.py
```

By default, this excludes retailers that already have native `v2` ingestion.

If you explicitly want to include those retailers through the old bridge:

```bash
python scripts/backfill_v2_catalog.py --include-native-v2
```

## Scraping Workflow

Run the full scraper pipeline:

```bash
venv\Scripts\activate
python scripts/run_scraper.py
```

Current scrape flow:

1. Run the legacy retailer scrapers.
2. Rebuild legacy merged products.
3. Backfill the persisted `v2` catalog from the remaining legacy retailers.
4. Refresh native-`v2` retailers directly through their persisted ingestion paths.
5. Clear API cache.

## Testing

Run the backend test suite:

```bash
venv\Scripts\activate
pytest backend/tests/
```

Notes:

- API tests use temporary SQLite database files instead of `:memory:`.
- Current coverage includes API behavior, parsing helpers, `v2` ingestion paths, and schema/backfill behavior.

## Native `v2` Coverage

Retailers currently on native `v2` ingestion:

- Centre Com
- Computer Alliance
- Shopping Express
- Scorptec
- JW Computers

Retailers still relying on the legacy scrape + backfill bridge:

- PCCG
- MSY
- Umart
- Any temporarily disabled retailer paths such as Austin

## Known Limits

- The repo still contains a large amount of legacy code and scraper logic.
- Several retailers still depend on the old `Product`/`PriceHistory` path.
- Scraper testing is not yet fixture-driven for all retailers.
- Selenium remains the dominant scraping mechanism, which is slower and more fragile than a more modern adapter approach.

## Recommended Next Work

1. Port `Umart` or `MSY` to native `v2` ingestion.
2. Add saved HTML fixtures and contract tests for the migrated retailers.
3. Keep shrinking the legacy bridge until the old `Product` path is no longer the source of truth.
4. Add better operational visibility for scrape runs and reviewable matching decisions.
