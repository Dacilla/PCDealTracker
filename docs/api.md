# API Reference

All endpoints live under `/api/v2`. Interactive docs are served at `/docs` when the API is running.

Review mutations require the `X-API-Key` header matching the backend `REVIEW_API_KEY`.

## Catalog

| Endpoint | Description |
|---|---|
| `GET /products` | Paginated canonical products with best-price and retailer aggregates |
| `GET /products/{product_id}` | Single product with all listings |
| `GET /offers` | Flat offer list, filterable by `product_id` |
| `GET /history?product_id=` | Per-retailer price history series for a product |
| `GET /filters` | Categories, brands, and price bounds for the current filter set |
| `GET /trends` | Biggest percentage price drops over a window |

### `GET /products`

Query parameters:

- `page` (default 1), `page_size` (default 24)
- `search` — substring match on canonical name
- `category_id`
- `sort_by` — `name` (default) | `price` | `offers`
- `sort_order` — `asc` | `desc`
- `hide_unavailable` (default true) — when true only products with priced available offers return

## Operations

| Endpoint | Description |
|---|---|
| `GET /health` | Catalog counts, latest scrape run, per-retailer freshness summaries |
| `GET /data-quality` | Review queue pressure, stale offers/retailers, catalog hygiene issues |
| `GET /analytics/summary` | Category breakdown, top brands, retailer coverage aggregates |
| `GET /scrape-runs` | Recent scrape runs, filterable by `retailer_id` and `status` |

### `GET /analytics/summary`

Returns:

```json
{
  "canonical_product_count": 1842,
  "active_offer_count": 2389,
  "tracked_retailer_count": 1,
  "tracked_category_count": 10,
  "category_breakdown": [
    {
      "category": {"id": 1, "name": "Graphics Cards"},
      "product_count": 412,
      "active_offer_count": 655,
      "avg_best_price": 812.4,
      "min_best_price": 189.0,
      "max_best_price": 5299.0
    }
  ],
  "brand_breakdown": [{"brand": "Thermaltake", "product_count": 162, "avg_best_price": 124.77}],
  "retailer_coverage": [
    {
      "retailer": {"id": 1, "name": "Computer Alliance", "url": "...", "logo_url": "..."},
      "active_offer_count": 2389,
      "distinct_product_count": 1842,
      "avg_offer_price": 331.9,
      "min_offer_price": 3.0
    }
  ]
}
```

Price statistics consider active offers that carry a price; retailers and categories still appear with zeroed counts.

## Match Review

| Endpoint | Auth | Description |
|---|---|---|
| `GET /match-decisions` | — | Filterable queue/history (`decision`, `retailer_id`, `category_id`, `search`, `sort_by=created_desc\|confidence_desc`) |
| `GET /match-decisions/{id}/candidates` | — | Ranked canonical candidates for the listing behind a decision |
| `GET /match-decisions/{id}/history` | — | Audit trail of every transition for the decision |
| `PATCH /match-decisions/{id}` | key | Resolve as `manual_matched` (+`canonical_product_id`) or `manual_rejected`, optional `rationale` |
| `POST /match-decisions/bulk-apply-top-candidates` | key | Bulk accept top candidates scoring at least `min_score` (default 95) |

Decision lifecycle values: `auto_matched`, `auto_rejected`, `needs_review`, `manual_matched`, `manual_rejected`.
Manual states survive re-ingestion until changed by a reviewer.

### Audit trail events

Each event records `event_type` (`created`, `ingest_transition`, `resolved`), previous/new decision and canonical
product, confidence, matcher, rationale, `source` (`ingestion`, `manual_review`, `bulk_review`), scrape run reference,
and timestamp. Events are append-only and cascade-delete with their decision.

Example response:

```json
{
  "decision_id": 42,
  "events": [
    {
      "id": 1,
      "event_type": "created",
      "new_decision": "needs_review",
      "source": "ingestion",
      "matcher": "candidate_rank",
      "confidence": 0.81,
      "created_at": "2026-08-01T04:12:55"
    },
    {
      "id": 2,
      "event_type": "resolved",
      "previous_decision": "needs_review",
      "new_decision": "manual_matched",
      "previous_canonical_product_id": null,
      "new_canonical_product_id": 123,
      "confidence": 1.0,
      "matcher": "manual_review",
      "rationale": "Confirmed same product after review",
      "source": "manual_review",
      "created_at": "2026-08-02T09:30:10"
    }
  ]
}
```

## Misc

- `GET /` — welcome payload with docs pointers.

## Errors

- `401` — missing/wrong `X-API-Key` on protected routes.
- `400` — invalid transitions (e.g. manual match without target, category mismatch).
- `404` — unknown product or decision id.
- `503` — persisted catalog is empty; run `scripts/run_scraper.py` first.
