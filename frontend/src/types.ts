export type Category = {
  id: number;
  name: string;
};

export type Retailer = {
  id: number;
  name: string;
  url: string;
  logo_url?: string | null;
};

export type Offer = {
  id: number;
  name: string;
  url: string;
  image_url?: string | null;
  current_price?: number | null;
  previous_price?: number | null;
  status: string;
  on_sale: boolean;
  retailer: Retailer;
};

export type ProductSummary = {
  id: string;
  canonical_name: string;
  category: Category;
  brand?: string | null;
  fingerprint: string;
  attributes: Record<string, string | number>;
  offer_count: number;
  available_offer_count: number;
  best_price?: number | null;
  best_price_retailer?: string | null;
  price_range_min?: number | null;
  price_range_max?: number | null;
  retailers: string[];
};

export type ProductDetail = ProductSummary & {
  listings: Offer[];
};

export type ProductPage = {
  total: number;
  products: ProductSummary[];
};

export type FilterPayload = {
  categories: Category[];
  brands: string[];
  min_price?: number | null;
  max_price?: number | null;
};

export type HealthPayload = {
  status: string;
  database_ok: boolean;
  catalog_ready: boolean;
  retailer_count: number;
  category_count: number;
  canonical_product_count: number;
  active_offer_count: number;
  review_queue_count: number;
  latest_scrape_run_status?: string | null;
  latest_scrape_run_scraper_name?: string | null;
  latest_scrape_run_retailer_name?: string | null;
  latest_scrape_run_started_at?: string | null;
  latest_scrape_run_finished_at?: string | null;
  latest_scrape_run_error_summary?: string | null;
  latest_scrape_run_listings_seen?: number | null;
  latest_scrape_run_listings_created?: number | null;
  latest_scrape_run_listings_updated?: number | null;
  latest_successful_scrape_finished_at?: string | null;
  retailer_summaries: RetailerHealthSummary[];
};

export type DataQualityIssue = {
  key: string;
  label: string;
  count: number;
  severity: string;
  detail: string;
};

export type DataQualityRetailerRow = {
  retailer: Retailer;
  pending_review_count: number;
  high_confidence_review_count: number;
  low_confidence_review_count: number;
  active_offer_count: number;
};

export type DataQualityCategoryRow = {
  category?: Category | null;
  pending_review_count: number;
  high_confidence_review_count: number;
  active_offer_count: number;
  canonical_product_count: number;
};

export type DataQualityPayload = {
  review_queue_count: number;
  high_confidence_review_count: number;
  medium_confidence_review_count: number;
  low_confidence_review_count: number;
  stale_offer_count: number;
  stale_offer_threshold_days: number;
  unpriced_active_offer_count: number;
  uncategorized_listing_count: number;
  products_without_active_offers_count: number;
  stale_retailer_count: number;
  retailer_queue: DataQualityRetailerRow[];
  category_queue: DataQualityCategoryRow[];
  issues: DataQualityIssue[];
};

export type RetailerHealthSummary = {
  retailer: Retailer;
  status: string;
  is_stale: boolean;
  stale_after_hours: number;
  active_offer_count: number;
  latest_scrape_run_status?: string | null;
  latest_scrape_run_scraper_name?: string | null;
  latest_scrape_run_started_at?: string | null;
  latest_scrape_run_finished_at?: string | null;
  latest_scrape_run_error_summary?: string | null;
  latest_scrape_run_listings_seen?: number | null;
  latest_scrape_run_listings_created?: number | null;
  latest_scrape_run_listings_updated?: number | null;
  latest_successful_scrape_finished_at?: string | null;
  successful_scrape_age_hours?: number | null;
};

export type HistorySeries = {
  retailer: Retailer;
  points: Array<{
    date: string;
    price: number;
    listing_id: number;
  }>;
};

export type HistoryPayload = {
  product_id: string;
  series: HistorySeries[];
};

export type Trend = {
  product: ProductSummary;
  initial_price: number;
  latest_price: number;
  price_drop_amount: number;
  price_drop_percentage: number;
};

export type ListingReference = {
  id: number;
  title: string;
  source_url: string;
  status: string;
  retailer: Retailer;
  category?: Category | null;
};

export type CanonicalReference = {
  id: string;
  canonical_name: string;
  fingerprint: string;
};

export type MatchDecision = {
  id: number;
  decision: string;
  confidence?: number | null;
  matcher?: string | null;
  rationale?: string | null;
  fingerprint?: string | null;
  created_at: string;
  retailer_listing: ListingReference;
  canonical_product?: CanonicalReference | null;
  scrape_run_id?: number | null;
  top_candidate?: MatchCandidate | null;
};

export type MatchDecisionPage = {
  total: number;
  decisions: MatchDecision[];
};

export type ScrapeRun = {
  id: number;
  retailer?: Retailer | null;
  started_at: string;
  finished_at?: string | null;
  status: string;
  trigger_source?: string | null;
  scraper_name?: string | null;
  listings_seen: number;
  listings_created: number;
  listings_updated: number;
  error_summary?: string | null;
  meta?: Record<string, unknown> | null;
};

export type MatchDecisionResolutionPayload = {
  decision: "manual_matched" | "manual_rejected";
  canonical_product_id?: string;
  rationale?: string;
};

export type BulkTopCandidatePayload = {
  decision_ids: number[];
  min_score: number;
};

export type BulkTopCandidateResult = {
  resolved_ids: number[];
  skipped: Array<{
    decision_id: number;
    reason: string;
  }>;
};

export type MatchCandidate = {
  canonical_product: CanonicalReference;
  category: Category;
  brand?: string | null;
  best_price?: number | null;
  retailer_count: number;
  score: number;
  reasons: string[];
};
