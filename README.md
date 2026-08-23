# PCDealTracker

[![CI/CD Pipeline](https://github.com/Dacilla/PCDealTracker/actions/workflows/ci.yml/badge.svg)](https://github.com/Dacilla/PCDealTracker/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.13+-blue)
![Node](https://img.shields.io/badge/node-20%2B-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

PCDealTracker tracks Australian PC hardware prices across multiple retailers and exposes a persisted `v2` catalog for
browsing, filtering, price history, trend analysis, and catalog quality operations.

## Overview

- **Backend**: FastAPI + SQLAlchemy with Alembic migrations
- **Frontend**: React + Vite + TypeScript
- **Databases**: SQLite for local development, PostgreSQL for containerized/runtime use
- **Scraping**: Selenium / undetected-chromedriver feeding the persisted `v2` catalog directly
- **License**: MIT

## Features

- Canonical product catalog deduplicated across 8 Australian retailers
- Per-retailer price history and all-time-low tracking
- Deal/trend detection over configurable time windows
- Automated matching pipeline with fuzzy candidate ranking, deterministic fingerprints, and a manual review queue
- Match decision audit trail recording every automated or human transition
- Operations surfaces: scrape health with staleness detection, data quality reports, bulk review actions
- Catalog analytics across categories, brands, and retailer coverage
- Local watchlist, compare tray, and target-price alerts in the browser

## Current Status

### Done

- Persisted `v2` catalog backed by Alembic migrations with database-level cascade deletes.
- Native direct-to-catalog ingestion for all active retailers:
  - Centre Com
  - Computer Alliance
  - JW Computers
  - MSY
  - PC Case Gear
  - Scorptec
  - Shopping Express
  - Umart
- Shared scraper utilities for image extraction and retrying transient page loads.
- Full `v2` API: products, offers, history, filters, trends, scrape runs, health, data quality, analytics,
  match decisions with candidates, audit history, single and bulk resolution.
- React/Vite/TypeScript frontend covering shopping surfaces (catalog, deals, watchlist, alerts, compare) and
  operations surfaces (products, review queue, data quality, retailers, scraper health, analytics, settings).
- Fixture-based scraper contract tests plus ingestion, schema/migration, and API test coverage.

### Still To Do

- Expand full-page fixture coverage to pagination edge cases for every retailer.
- Reduce Selenium dependence where retailer markup allows lighter HTTP-first adapters.
- Automate fixture refresh from Playwright diagnostics captures.

See [AUDIT.md](AUDIT.md) for the live list of unresolved findings.

## Documentation

- [Architecture](docs/architecture.md) — data flow, core models, matching pipeline, scraping stack
- [API reference](docs/api.md) — every `/api/v2` endpoint with parameters and examples
- [Contributing](CONTRIBUTING.md) — development setup, conventions, and PR checklist

## Architecture

```text
Retailer scraper
  -> RetailerListing
  -> CanonicalProduct
  -> Offer
  -> PriceObservation
  -> MatchDecision (+ MatchDecisionEvent audit trail) / ScrapeRun
  -> /api/v2/*
```

Core models: `CanonicalProduct`, `RetailerListing`, `Offer`, `PriceObservation`, `ScrapeRun`, `MatchDecision`,
and `MatchDecisionEvent`. Details in [docs/architecture.md](docs/architecture.md).

## Requirements

- Python 3.13+
- Node.js 20+
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

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite (default) or PostgreSQL connection string |
| `API_CORS_ORIGINS` | Allowed browser origins |
| `SCRAPE_SCHEDULER_ENABLED` | Run periodic scrapers inside the API process |
| `SCRAPE_INTERVAL_HOURS` | Scheduler cadence |
| `SCRAPER_USER_DATA_DIR` | Reuse a real Chrome profile across scraper runs |
| `SCRAPER_BROWSER_EXECUTABLE` | Chrome binary outside default discovery paths |
| `SCRAPER_HEADLESS` | Force background scraper execution |
| `SCRAPER_CHALLENGE_TIMEOUT_SECONDS` | Keep browser open while challenge pages self-clear |
| `SCRAPER_PAGE_LOAD_RETRIES` | Extra attempts for transient page load failures (default 2) |
| `SCRAPER_RETRY_BACKOFF_SECONDS` | Pause between page load retries (default 3) |
| `REVIEW_API_KEY` | Protects review mutations |

Backend URLs:

- API docs: `http://localhost:8000/docs`
- `v2` API: `http://localhost:8000/api/v2/*`
- Endpoint reference: [docs/api.md](docs/api.md)

Example review resolution request (see [docs/api.md](docs/api.md) for more):

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

Every manual or automated decision transition is recorded in the match decision audit trail, available at
`GET /api/v2/match-decisions/{id}/history`.

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend URL: `http://localhost:5173`

Important frontend env vars:

- `VITE_API_BASE_URL` defaults to `http://localhost:8000`
- `VITE_REVIEW_API_KEY` must match backend `REVIEW_API_KEY` for review actions

Production build:

```bash
cd frontend
npm run build
```

## Docker

```bash
docker-compose up --build
```

Services: frontend `http://localhost:5173`, backend `http://localhost:8000`, Postgres `localhost:5432`,
Redis `localhost:6379`.

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

Current tables: `canonical_products`, `retailer_listings`, `offers`, `price_observations`, `scrape_runs`,
`match_decisions`, `match_decision_events`. Catalog foreign keys carry `ON DELETE CASCADE`; SQLite engines created by
the app enable the `foreign_keys` pragma so cascades apply on both backends.

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

Scrape flow:

1. Run native `v2` retailer scrapers concurrently.
2. Persist listing, offer, observation, and match updates directly into the `v2` catalog.
3. Clear API cache.

Transient page load failures are retried automatically; gate waits/challenge clears and retry counts appear in
scrape-run error summaries.

### Playwright Diagnostics

For live selector validation and fixture capture against real retailer sites:

```bash
venv\Scripts\activate
playwright install chromium
python scripts/retailer_diagnostics.py --retailer centrecom
```

Useful variants:

- `--list-retailers`
- `--retailer all`
- `--retailer jw --headed`
- `--engine selenium --headed --user-data-dir .browser-profile --challenge-timeout-ms 60000`

Outputs land in `logs/playwright-diagnostics/`: screenshot, captured HTML, and a JSON summary with selector counts and
access-block classification (`ok` / `blocked` / `timeout` / `error`). The `auto` engine tries Playwright first and
falls back to the undetected-Chrome Selenium stack when blocked.

### Shared Browser Profile Workflow

Some retailers block fresh automated sessions but allow a real interactive browser profile once their challenge page
clears. Capture a profile with diagnostics, then reuse it for scrapers:

```bash
set SCRAPER_USER_DATA_DIR=.browser-profile
set SCRAPER_CHALLENGE_TIMEOUT_SECONDS=60
python scripts/run_scraper.py
```

If `undetected_chromedriver` ever downloads a driver for the wrong Chrome major version, set
`SCRAPER_BROWSER_MAJOR_VERSION` explicitly to match the installed browser.

## Testing

```bash
venv\Scripts\activate
pytest backend/tests/
```

Coverage includes API behavior, parsing helpers (including shared image extraction), scraper contract fixtures,
ingestion paths, match decision auditing, scrape-run orchestration, schema/migration behavior including cascade
deletes, and diagnostic config extraction.

## Supported Retailers

Centre Com · Computer Alliance · JW Computers · MSY · PC Case Gear · Scorptec · Shopping Express · Umart

## Known Limits

- Scraping still depends on Selenium, which is slower and more fragile than lighter HTML-first adapters.
- Price alerts evaluate locally in the browser only while the tab is open.
- Not every retailer-specific crawl edge case is locked down with fixtures yet.
