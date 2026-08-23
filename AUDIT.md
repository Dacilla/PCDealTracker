# PCDealTracker — Open Audit Items

This file tracks unresolved findings only. Resolved or obsolete transition notes should be removed.

---

## 1. Scraper / Ingestion Quality

### 1.1 Expand Playwright diagnostics into a fuller scraper workflow

**Files:** `scripts/retailer_diagnostics.py`, `backend/tests/test_scraper_contracts.py`

There is now a Playwright-based live diagnostics tool, but it is still a manual operator workflow rather than an
integrated scraper-debug pipeline.

Potential improvements:
- add first-class fixture refresh helpers from captured Playwright HTML
- probe deeper flows such as pagination, subcategory traversal, and retailer-specific interactions
- surface per-retailer diagnostic health in the app or CI

Current observed limitation:
- some retailers may block Playwright entirely with `403` or Cloudflare challenge pages, so live browser diagnostics are
  useful but not universally available without additional mitigation

---

## 2. API / Code Quality

### 2.1 Unused backend endpoint

**File:** `backend/app/api/v2.py`

`GET /api/v2/offers` still exists in the backend, but the frontend does not consume it directly.
It may still be useful for debugging or future clients, but right now it expands API surface area without a clear
current consumer.

---

## 3. Suggestions / Nice-to-Haves

- Reduce Selenium dependence where retailer markup allows lighter HTTP-first adapters.
- Server-side price alert evaluation with notifications (alerts are currently local-only in the browser).
- Fixture refresh automation driven by captured Playwright diagnostics output.
