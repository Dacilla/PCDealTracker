# Contributing

Thanks for your interest in improving PCDealTracker!

## Development Setup

### Backend

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
python scripts/init_database.py
uvicorn backend.app.main:app --reload
```

The API is now available at `http://localhost:8000` with interactive docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` and `VITE_REVIEW_API_KEY` in `frontend/.env` to point at the backend.

## Running Tests

Backend tests use temporary SQLite databases and do not require network access:

```bash
venv\Scripts\activate
pytest backend/tests/
```

Frontend type checking and production build:

```bash
cd frontend
npm run build
```

Please add tests for behavioural changes:

- API changes → `backend/tests/test_api.py`
- Ingestion/matching logic → `backend/tests/test_v2_ingestion.py`
- Schema/migrations → `backend/tests/test_v2_schema.py`
- Scraper parsing changes → update fixtures under `backend/tests/fixtures/` and the contract tests

## Project Conventions

- Python 3.13+, no default parameter values outside dataclasses/config.
- Backend code keeps to the existing layering: routers (`app/api`) stay thin, business rules live in
  `app/services/v2_catalog.py`, parsing helpers in `app/utils/parsing.py`.
- New catalog tables must declare `ON DELETE CASCADE` on foreign keys so `clear_v2_catalog()` keeps working, and need
  an Alembic migration (`alembic upgrade head` must always work against both SQLite and PostgreSQL).
- Match decision changes should append `MatchDecisionEvent` rows rather than mutating history away.
- Retailer scrapers implement `parse_<retailer>_listing` plus a `BaseScraper` subclass; reuse shared helpers such as
  `extract_listing_image_url()` instead of duplicating extraction logic.
- The frontend is a single React app with TanStack Query; keep screens self-contained components and share formatting
  helpers already defined at the top of `App.tsx`.

## Commit Messages

Use imperative subject lines and include a body explaining what changed and why. Scope prefixes such as
`feat(api):`, `fix(frontend):`, `refactor(scrapers):` are welcome.

## Pull Requests

1. Branch from `master`.
2. Ensure `pytest backend/tests/` and `npm run build` pass.
3. Update documentation (README, `docs/`, `AUDIT.md`) when behaviour or endpoints change.
4. Describe user-visible changes in the PR description.
