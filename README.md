# PCDealTracker

PCDealTracker tracks Australian PC hardware prices across multiple retailers and exposes a persisted `v2` catalog for browsing, filtering, history, and trend analysis.

## Overview

- Backend: FastAPI + SQLAlchemy
- Frontend: React + Vite + TypeScript
- Databases: SQLite for local development, PostgreSQL for containerized/runtime use
- Scraping: Selenium / undetected-chromedriver feeding the persisted `v2` catalog directly

## Current Status

### Done

- Rebuilt the project around a persisted `v2` catalog.
- Added Alembic migrations for the `v2` schema.
- Added `v2` API endpoints for products, offers, history, filters, trends, scrape runs, and match decisions.
- Replaced the old single-file frontend with a React/Vite/TypeScript frontend.
- Added a frontend operations view for scrape runs and manual review of `needs_review` match decisions.
- Migrated all active retailers to direct `v2` ingestion:
  - Centre Com
  - Computer Alliance
  - JW Computers
  - MSY
  - PC Case Gear
  - Scorptec
  - Shopping Express
  - Umart
- Added fixture-based scraper contract tests and direct ingestion tests for the native scrapers.
- Removed the legacy v1 API, merge pipeline, backfill bridge, and deprecated legacy scraper modules.

### Still To Do

- Add stronger reviewer workflows such as bulk actions, audit history, and better candidate ranking for manual matches.
- Keep expanding fixture coverage to broader crawl and pagination edge cases.
- Reduce Selenium dependence over time where retailer markup allows lighter adapters.

## Architecture

### Data Flow

```text
Retailer scraper
  -> RetailerListing
  -> CanonicalProduct
  -> Offer
  -> PriceObservation
  -> MatchDecision / ScrapeRun
  -> /api/v2/*
```

### Core Models

- `CanonicalProduct`: persisted grouped product identity
- `RetailerListing`: raw retailer listing record
- `Offer`: retailer offer attached to a canonical product
- `PriceObservation`: time-series price and stock observation
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
- Chrome or Chromium compatible with the Selenium setup if running scrapers

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
- `v2` API: `http://localhost:8000/api/v2/*`
- Scrape runs: `http://localhost:8000/api/v2/scrape-runs`
- Match decisions: `http://localhost:8000/api/v2/match-decisions`
- Match decision resolution: `PATCH http://localhost:8000/api/v2/match-decisions/{id}`

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

## Scraping Workflow

Run the scraper pipeline:

```bash
venv\Scripts\activate
python scripts/run_scraper.py
```

Current scrape flow:

1. Run native `v2` retailer scrapers concurrently.
2. Persist listing, offer, observation, and match updates directly into the `v2` catalog.
3. Clear API cache.

## Testing

Run the backend test suite:

```bash
venv\Scripts\activate
pytest backend/tests/
```

Notes:

- API tests use temporary SQLite database files instead of `:memory:`.
- Coverage includes API behavior, parsing helpers, scraper contract fixtures, ingestion paths, scrape-run orchestration, and schema/migration behavior.

## Supported Retailers

- Centre Com
- Computer Alliance
- JW Computers
- MSY
- PC Case Gear
- Scorptec
- Shopping Express
- Umart

## Known Limits

- Scraping still depends on Selenium, which is slower and more fragile than lighter HTML-first adapters.
- Manual review exists now, but it is still a lightweight workflow rather than a full moderation tool.
- Fixture coverage is much better than before, but not every retailer-specific crawl edge case is locked down yet.

## Recommended Next Work

1. Improve the operations view with bulk review actions and better canonical candidate ranking.
2. Expand full-page scraper fixtures and pagination coverage for every retailer.
3. Add more operational reporting around scrape health and stale retailers.
4. Start replacing Selenium-heavy flows where stable HTML requests are sufficient.
