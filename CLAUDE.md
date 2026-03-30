# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PCDealTracker is a price tracking application for Australian PC hardware retailers. It scrapes product prices from 8+ retailers, merges equivalent products across retailers using fuzzy matching, and exposes a REST API consumed by a single-page frontend.

## Commands

### Running the Backend (Development)
```bash
cd backend
python -m venv venv
venv/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env
python app/main.py  # http://localhost:8000
```

### Running the Frontend
```bash
cd frontend
python -m http.server 3000  # http://localhost:3000
```

### Docker (Full Stack)
```bash
docker-compose up -d
```

### Running Tests
```bash
pytest backend/tests/                        # All tests
pytest backend/tests/test_api.py            # API tests only
pytest backend/tests/test_parsing.py        # Parsing utility tests
pytest backend/tests/ --cov=backend/app     # With coverage
pytest backend/tests/test_api.py::test_name # Single test
```

### Scraping
```bash
python scripts/run_scraper.py               # Run all scrapers + rebuild merged products
python scripts/rebuild_merged_products.py   # Rebuild merged products from existing data
python scripts/merge_products.py            # Re-run merge/fuzzy matching only
```

## Architecture

### Data Pipeline
```
Scraper (Selenium/undetected-chromedriver)
  → Parse HTML (BeautifulSoup4)
  → Upsert Product + PriceHistory (SQLAlchemy)
  → Two-pass Merge (normalized model → fuzzy token_set_ratio ≥ 96)
  → Redis Cache invalidation
  → API responds with merged view
```

### Backend (`backend/app/`)

**Entry point**: `main.py` — registers 7 API routers under `/api/v1`.

**Database** (`database.py`): SQLAlchemy ORM with these key models:
- `Product` — individual retailer listing with price, status, normalized model fields
- `MergedProduct` — canonical product aggregating same item across retailers, with JSON `attributes` field
- `merged_product_association` — many-to-many junction between Product and MergedProduct
- `PriceHistory` — time-series prices per product
- Supports SQLite (dev/test) and PostgreSQL (production); enum handling differs between them

**API Routers** (`api/`): `merged_products`, `deals`, `price_history`, `categories`, `retailers`, `filters`, `trends`
- Most endpoints cache responses in Redis (15 min for products, 24h for categories/filters)
- `merged_products` supports rich query params: `search`, `search_mode` (loose/strict), `category_id`, `sort_by`, `min_price`, `max_price`, plus dynamic `min_*`/`max_*` attribute filters

**Scrapers** (`scrapers/`): Each retailer has its own scraper inheriting from `base_scraper.py`, which provides undetected-chromedriver setup. Scrapers run concurrently via `ThreadPoolExecutor` in `scripts/run_scraper.py`.

**Parsing** (`utils/parsing.py`): Core logic for product normalization:
- `normalize_model_strict()` — removes brand names and marketing terms, preserves model identifiers
- `normalize_model_loose()` — aggressive normalization for core model matching (used for merging)
- `parse_product_attributes()` — extracts structured specs (VRAM, RAM, socket, storage) from product names

### Frontend (`frontend/`)

Single `index.html` — vanilla JS, Tailwind CSS, Chart.js, noUiSlider. No build step required.
- Sidebar: category navigation, sort/filter controls, dynamic per-category attribute filters
- Main grid: product cards with retailer price comparison
- Modals: product detail with price history chart (Chart.js)
- Retailer SVG logos in `assets/logos/`

### Testing

Tests use SQLite in-memory DB via dependency injection override (`app/dependencies.py`). Fixtures in `conftest.py` populate sample data. CI runs against PostgreSQL.

### Environment Variables

Key variables (see `.env.example`):
- `DATABASE_URL` — SQLite for dev, PostgreSQL for prod
- `REDIS_URL` — defaults to `redis://localhost:6379`
- `SCRAPE_INTERVAL_HOURS` — scheduler interval
- `MAX_CONCURRENT_SCRAPERS` — thread pool size
