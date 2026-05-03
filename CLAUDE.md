# CLAUDE.md

This file provides baseline guidance for AI coding agents working in this repository.
Treat it as a quick orientation layer, not a source of truth over the code itself.

## Project Overview

PCDealTracker tracks Australian PC hardware prices across multiple retailers.

Current architecture:
- Backend: FastAPI + SQLAlchemy
- Frontend: React + Vite + TypeScript
- Database: persisted `v2` catalog in SQLite for local dev or PostgreSQL in container/runtime setups
- Scraping: Selenium / `undetected-chromedriver` scrapers that ingest directly into the `v2` schema

Supported retailers in the current codebase:
- Centre Com
- Computer Alliance
- JW Computers
- MSY Technology
- PC Case Gear
- Scorptec
- Shopping Express
- Umart

## Commands

### Backend
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/init_database.py
uvicorn backend.app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

### Docker
```bash
docker-compose up --build
```

### Tests
```bash
venv\Scripts\activate
pytest backend/tests/
```

### Scraping
```bash
venv\Scripts\activate
python scripts/run_scraper.py
```

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

### Backend (`backend/app/`)

Entry point:
- `main.py` registers the single `v2` router and optional scrape scheduler

Main API surface:
- `/api/v2/products`
- `/api/v2/products/{id}`
- `/api/v2/history`
- `/api/v2/filters`
- `/api/v2/trends`
- `/api/v2/scrape-runs`
- `/api/v2/match-decisions`

Key models in `database.py`:
- `CanonicalProduct`
- `RetailerListing`
- `Offer`
- `PriceObservation`
- `ScrapeRun`
- `MatchDecision`

Catalog logic:
- `services/v2_catalog.py` owns ingest, matching, review queue, and catalog maintenance logic

Scrapers:
- Each retailer has its own `*_v2_scraper.py`
- Shared browser/bootstrap logic lives in `scrapers/base_scraper.py`
- Scrapers are executed concurrently from `scripts/run_scraper.py`

### Frontend (`frontend/`)

Current frontend stack:
- React 18
- Vite
- TypeScript
- TanStack Query
- Recharts

Current UI areas:
- Product browsing
- Product detail with price history
- Trend view
- Operations view for scrape runs and match review

## Notes

- `README.md` is the main human-facing project guide and is generally more current than this file.
- The repository no longer contains the old v1 API / merge pipeline described in earlier project iterations.
