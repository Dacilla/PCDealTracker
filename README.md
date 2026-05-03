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
python scripts/init_database.py
uvicorn backend.app.main:app --reload
```

Important backend env vars:

- `DATABASE_URL`
- `API_CORS_ORIGINS`
- `SCRAPE_SCHEDULER_ENABLED` to enable periodic scraper execution inside the API process
- `SCRAPE_INTERVAL_HOURS` for the scheduler cadence
- `SCRAPER_USER_DATA_DIR` to reuse a real Chrome profile across scraper runs
- `SCRAPER_BROWSER_EXECUTABLE` if Chrome is installed outside the default discovery path
- `SCRAPER_HEADLESS` to force background scraper execution when desired
- `SCRAPER_CHALLENGE_TIMEOUT_SECONDS` to keep a real browser open while self-clearing challenge pages resolve
- `REVIEW_API_KEY` for protected review mutations

Backend URLs:

- API docs: `http://localhost:8000/docs`
- `v2` API: `http://localhost:8000/api/v2/*`
- Scrape runs: `http://localhost:8000/api/v2/scrape-runs`
- Match decisions: `http://localhost:8000/api/v2/match-decisions`
- Match decision resolution: `PATCH http://localhost:8000/api/v2/match-decisions/{id}`
  Requires header `X-API-Key: <REVIEW_API_KEY>`.

Example review resolution request:

```http
PATCH /api/v2/match-decisions/42 HTTP/1.1
Host: localhost:8000
Content-Type: application/json
X-API-Key: change-me

{
  "decision": "manual_matched",
  "canonical_product_id": "123",
  "rationale": "Confirmed same product after review"
}
```

Example response:

```json
{
  "id": 42,
  "decision": "manual_matched",
  "confidence": 1.0,
  "matcher": "manual_review",
  "rationale": "Confirmed same product after review",
  "fingerprint": "abc123",
  "created_at": "2026-04-09T12:00:00",
  "retailer_listing": {
    "id": 77,
    "title": "ASUS GeForce RTX 5070 PRIME OC 12GB",
    "source_url": "https://example.com/product",
    "status": "available",
    "retailer": {
      "id": 1,
      "name": "Example Retailer",
      "url": "https://example.com",
      "logo_url": null
    },
    "category": {
      "id": 3,
      "name": "Graphics Cards"
    }
  },
  "canonical_product": {
    "id": "123",
    "canonical_name": "ASUS GeForce RTX 5070 PRIME OC 12GB",
    "fingerprint": "abc123"
  },
  "scrape_run_id": 10
}
```

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Production build:

```bash
cd frontend
npm run build
```

Frontend URL:

- `http://localhost:5173`

Important frontend env vars:

- `VITE_API_BASE_URL` defaults to `http://localhost:8000`
- `VITE_REVIEW_API_KEY` must match backend `REVIEW_API_KEY` for review actions

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

Fresh PostgreSQL bootstrap:

```bash
copy .env.example .env
set DATABASE_URL=postgresql://user:password@localhost/pcdealtracker
venv\Scripts\activate
alembic upgrade head
python scripts/init_database.py
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

To run only one retailer while debugging:

```bash
python scripts/run_scraper.py --retailer computeralliance
python scripts/run_scraper.py --retailer centrecom --retailer scorptec
```

Current scrape flow:

1. Run native `v2` retailer scrapers concurrently.
2. Persist listing, offer, observation, and match updates directly into the `v2` catalog.
3. Clear API cache.

Scrape run summaries now include browser-gate signals in `error_summary` when a scraper had to wait for a challenge page,
when the challenge auto-cleared, or when it never cleared.

### Playwright Diagnostics

For live selector validation and fixture capture against the real retailer sites:

```bash
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python scripts/retailer_diagnostics.py --retailer centrecom
```

Useful variants:

- `python scripts/retailer_diagnostics.py --list-retailers`
- `python scripts/retailer_diagnostics.py --retailer all`
- `python scripts/retailer_diagnostics.py --retailer jw --headed`
- `python scripts/retailer_diagnostics.py --retailer centrecom`
- `python scripts/retailer_diagnostics.py --retailer computeralliance --engine selenium --headed`
- `python scripts/retailer_diagnostics.py --retailer computeralliance --headed --browser-channel chrome --user-data-dir .browser-profile --challenge-timeout-ms 60000`

Outputs are written to `logs/playwright-diagnostics/`:

- full-page screenshot
- captured HTML
- JSON summary with selector counts, preview rows, and access-block classification

Possible diagnostic statuses:

- `ok`: target selectors were found and preview extraction succeeded
- `blocked`: the site returned a bot/access challenge such as `403 Forbidden` or a Cloudflare verification page
- `timeout`: the expected selector never appeared and the page did not match a known access-block signature
- `error`: the capture failed for another runtime reason

This is intended as an operations/debugging tool for verifying scraper selectors against live pages before changing the
native Selenium scrapers or refreshing fixtures.

Engine notes:

- `auto` is now the default. It tries Playwright first, then retries with Selenium if the page is blocked or times out behind a challenge.
- `playwright` is useful for fast capture, screenshots, and HTML export across retailers that do not aggressively block automated sessions.
- `selenium` uses the same `undetected_chromedriver` stack as the production scrapers and is the better choice for Cloudflare-protected retailers where simply opening a real Chrome window lets the challenge clear automatically.

### Shared Browser Profile Workflow

Some retailers will block fresh automated sessions but allow a real, interactive browser profile once their challenge
page has rendered and cleared. The project now supports a shared profile path for both diagnostics and Selenium
scrapers, and the Selenium diagnostics mode now uses the same undetected-Chrome path as the production scrapers.

Example flow:

```bash
venv\Scripts\activate
python scripts/retailer_diagnostics.py --retailer computeralliance --engine selenium --headed --user-data-dir .browser-profile --challenge-timeout-ms 60000
```

Then set the same profile for the scrapers:

```bash
set SCRAPER_USER_DATA_DIR=.browser-profile
set SCRAPER_CHALLENGE_TIMEOUT_SECONDS=60
python scripts/run_scraper.py
```

That gives you a less clunky version of the old live-window workflow: open a real browser window, let the site’s
self-clearing challenge render and resolve automatically, then reuse that profile for later automated runs.
If `undetected_chromedriver` ever downloads a driver for the wrong Chrome major version, set
`SCRAPER_BROWSER_MAJOR_VERSION` explicitly to match the installed browser.

## Testing

Run the backend test suite:

```bash
venv\Scripts\activate
pytest backend/tests/
```

Notes:

- API tests use temporary SQLite database files instead of `:memory:`.
- Coverage includes API behavior, parsing helpers, scraper contract fixtures, ingestion paths, scrape-run orchestration, schema/migration behavior, and Playwright diagnostic config extraction.

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
- Playwright diagnostics are a manual operations tool right now; they are not yet part of CI or automated fixture refresh flows.

## Recommended Next Work

1. Improve the operations view with bulk review actions and better canonical candidate ranking.
2. Expand full-page scraper fixtures and pagination coverage for every retailer.
3. Add more operational reporting around scrape health and stale retailers.
4. Start replacing Selenium-heavy flows where stable HTML requests are sufficient.
