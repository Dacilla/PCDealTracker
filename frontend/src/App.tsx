import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  bulkApplyTopCandidates,
  fetchDataQuality,
  fetchFilters,
  fetchHealth,
  fetchHistory,
  fetchMatchCandidates,
  fetchMatchDecisions,
  fetchProduct,
  fetchProducts,
  fetchScrapeRuns,
  fetchTrends,
  getApiBase,
  resolveMatchDecision
} from "./api";
import type {
  DataQualityPayload,
  HistoryPayload,
  MatchCandidate,
  MatchDecision,
  MatchDecisionResolutionPayload,
  ProductDetail,
  ProductSummary,
  RetailerHealthSummary,
  ScrapeRun,
  Trend
} from "./types";

type Screen =
  | "catalog"
  | "deals"
  | "watchlist"
  | "alerts"
  | "compare"
  | "products"
  | "review"
  | "dq"
  | "retailers"
  | "scraper"
  | "analytics"
  | "settings";

type CatalogMode = "grid" | "list";

type NavItem = {
  key: Screen;
  label: string;
  count?: number;
  implemented: boolean;
};

type LocalPriceAlert = {
  id: string;
  productId: string;
  targetPrice: number;
  createdAt: string;
};

type ProductCoverageFilter = "all" | "live" | "gaps";

const REVIEW_PAGE_SIZE = 20;
const WATCHLIST_STORAGE_KEY = "pcdt-watchlist";
const COMPARE_STORAGE_KEY = "pcdt-compare";
const ALERTS_STORAGE_KEY = "pcdt-alerts";
const SERIES_COLORS = ["#58d4ff", "#4ec89a", "#f5b745", "#ff7a66", "#b988ff", "#8cd6ff"];

const NAV_SECTIONS: Array<{ title: string; items: Screen[] }> = [
  { title: "Shop", items: ["catalog", "deals", "watchlist", "alerts", "compare"] },
  { title: "Ops", items: ["products", "review", "dq", "retailers", "scraper", "analytics", "settings"] }
];

const SCREEN_META: Record<Screen, { title: string; subtitle: string; implemented: boolean }> = {
  catalog: {
    title: "Catalog",
    subtitle: "Browse canonical products, compare live offers, and inspect retailer price history.",
    implemented: true
  },
  deals: {
    title: "Deals",
    subtitle: "Scan the biggest recent price drops and jump straight into the affected product group.",
    implemented: true
  },
  watchlist: {
    title: "Watchlist",
    subtitle: "Track shortlisted products locally and keep their current best price within reach.",
    implemented: true
  },
  alerts: {
    title: "Price Alerts",
    subtitle: "Create local target-price alerts against tracked products and see which ones have already triggered.",
    implemented: true
  },
  compare: {
    title: "Compare",
    subtitle: "Compare shortlisted canonical products side by side using live prices, retailers, and parsed attributes.",
    implemented: true
  },
  products: {
    title: "Products",
    subtitle: "Audit canonical product coverage, focus on rows without live offers, and inspect the underlying grouped catalog entities.",
    implemented: true
  },
  review: {
    title: "Review Queue",
    subtitle: "Work through ambiguous retailer listings, inspect candidates, and resolve matches without leaving the queue.",
    implemented: true
  },
  dq: {
    title: "Data Quality",
    subtitle: "Track queue pressure, stale coverage, and catalog hygiene issues that need operational attention.",
    implemented: true
  },
  retailers: {
    title: "Retailers",
    subtitle: "Inspect each retailer's scrape freshness, latest run result, and live offer volume.",
    implemented: true
  },
  scraper: {
    title: "Scraper Health",
    subtitle: "Inspect the latest scrape health, listing volumes, and recent run history in one place.",
    implemented: true
  },
  analytics: {
    title: "Analytics",
    subtitle: "The design reserves an analytics surface, but the live app does not provide dedicated analytics endpoints yet.",
    implemented: false
  },
  settings: {
    title: "Settings",
    subtitle: "Settings are not yet implemented in the live product.",
    implemented: false
  }
};

function formatCurrency(value?: number | null) {
  if (value === undefined || value === null) {
    return "—";
  }
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0
  }).format(value);
}

function formatNumber(value?: number | null) {
  return new Intl.NumberFormat("en-AU").format(value ?? 0);
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}

function formatShortDate(value?: string | null) {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleDateString("en-AU", {
    month: "short",
    day: "numeric"
  });
}

function formatStatusLabel(value?: string | null) {
  if (!value) {
    return "none";
  }
  return value.replaceAll("_", " ");
}

function statusTone(value?: string | null) {
  const normalized = (value || "").toLowerCase();
  if (normalized === "failed" || normalized === "blocked") {
    return "tag tag-red";
  }
  if (normalized === "partial" || normalized === "degraded" || normalized === "timeout" || normalized === "stale") {
    return "tag tag-amber";
  }
  if (normalized === "running" || normalized === "started") {
    return "tag tag-cyan";
  }
  if (normalized === "succeeded" || normalized === "ok") {
    return "tag tag-green";
  }
  return "tag tag-muted";
}

function issueTone(value?: string | null) {
  const normalized = (value || "").toLowerCase();
  if (normalized === "critical") {
    return "tag tag-red";
  }
  if (normalized === "warning") {
    return "tag tag-amber";
  }
  if (normalized === "ok") {
    return "tag tag-green";
  }
  return "tag tag-cyan";
}

function buildChartRows(history?: HistoryPayload) {
  if (!history) {
    return [];
  }

  const rows = new Map<string, Record<string, string | number>>();
  for (const series of history.series) {
    for (const point of series.points) {
      const key = point.date;
      const row = rows.get(key) ?? { date: new Date(point.date).toLocaleDateString("en-AU") };
      row[series.retailer.name] = point.price;
      rows.set(key, row);
    }
  }

  return Array.from(rows.values());
}

function readStringList(key: string) {
  if (typeof window === "undefined") {
    return [] as string[];
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
  } catch {
    return [];
  }
}

function readWatchlist() {
  return readStringList(WATCHLIST_STORAGE_KEY);
}

function readCompareList() {
  return readStringList(COMPARE_STORAGE_KEY);
}

function readAlerts() {
  if (typeof window === "undefined") {
    return [] as LocalPriceAlert[];
  }

  try {
    const raw = window.localStorage.getItem(ALERTS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is LocalPriceAlert => {
      return Boolean(
        item &&
          typeof item === "object" &&
          typeof (item as LocalPriceAlert).id === "string" &&
          typeof (item as LocalPriceAlert).productId === "string" &&
          typeof (item as LocalPriceAlert).targetPrice === "number" &&
          typeof (item as LocalPriceAlert).createdAt === "string"
      );
    });
  } catch {
    return [];
  }
}

function Icon({ name }: { name: string }) {
  switch (name) {
    case "catalog":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <rect x="2" y="2" width="5" height="5" rx="1" fill="currentColor" />
          <rect x="9" y="2" width="5" height="5" rx="1" fill="currentColor" />
          <rect x="2" y="9" width="5" height="5" rx="1" fill="currentColor" />
          <rect x="9" y="9" width="5" height="5" rx="1" fill="currentColor" />
        </svg>
      );
    case "deals":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M3 11.5L6.2 8.4l2.2 2.2L13 5.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M10.2 5.8H13v2.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    case "watchlist":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path
            d="M8 2.2l1.7 3.4 3.8.6-2.7 2.6.7 3.7L8 10.8l-3.5 1.7.7-3.7-2.7-2.6 3.8-.6L8 2.2Z"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "alerts":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M8 2.5a3 3 0 0 1 3 3v1.2c0 .8.3 1.5.8 2.1l.9 1H4.3l.9-1c.5-.6.8-1.3.8-2.1V5.5a3 3 0 0 1 3-3Z" stroke="currentColor" strokeWidth="1.4" />
          <path d="M6.5 12.5a1.5 1.5 0 0 0 3 0" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      );
    case "compare":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <rect x="2" y="3" width="4" height="10" rx="1" stroke="currentColor" strokeWidth="1.3" />
          <rect x="10" y="1" width="4" height="12" rx="1" stroke="currentColor" strokeWidth="1.3" />
        </svg>
      );
    case "products":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M3 4.5h10M3 8h10M3 11.5h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    case "review":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M3 3h10v7H7l-3 3V3Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          <path d="M6 6.2h4M6 8.5h2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      );
    case "dq":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M3 3.5h10v9H3z" stroke="currentColor" strokeWidth="1.4" />
          <path d="M5.3 8 7 9.7l3.7-3.7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "retailers":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M2.5 6.5h11v6h-11zM4 6.5V4.2h8v2.3" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
        </svg>
      );
    case "scraper":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M8 2v4m0 4v4M2 8h4m4 0h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4" />
        </svg>
      );
    case "analytics":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M3 12.5V8.5M8 12.5V4.5M13 12.5V6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    case "settings":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.3" />
          <path
            d="M8 2.3v1.5m0 8.4v1.5M13.7 8h-1.5M3.8 8H2.3m9.7-4.2-1 1M5 11l-1 1m0-8 1 1m6 6 1 1"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
      );
    case "search":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <circle cx="6.5" cy="6.5" r="4.7" stroke="currentColor" strokeWidth="1.4" />
          <path d="M10.2 10.2 14 14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      );
    case "external":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path d="M9 3h4v4M7 9l6-6M13 9.5V13H3V3h3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "star":
      return (
        <svg viewBox="0 0 16 16" aria-hidden="true" fill="none">
          <path
            d="M8 2.3 9.8 6l4 .6-2.9 2.8.7 4-3.6-1.9-3.6 1.9.7-4L2.2 6.6l4-.6L8 2.3Z"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
        </svg>
      );
    default:
      return <span />;
  }
}

function NavButton({
  label,
  count,
  active,
  implemented,
  icon,
  onClick
}: {
  label: string;
  count?: number;
  active: boolean;
  implemented: boolean;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`nav-item ${active ? "active" : ""}`} onClick={onClick}>
      <span className="nav-icon">
        <Icon name={icon} />
      </span>
      <span className="nav-label">{label}</span>
      {!implemented ? <span className="tag tag-muted nav-tag">Planned</span> : null}
      {count !== undefined && count > 0 ? <span className="badge nav-badge">{count}</span> : null}
    </button>
  );
}

function StatCard({ label, value, sublabel }: { label: string; value: string; sublabel: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      <span className="stat-sublabel">{sublabel}</span>
    </div>
  );
}

function ProductCard({
  product,
  active,
  watched,
  compared,
  onSelect,
  onToggleWatchlist,
  onToggleCompare
}: {
  product: ProductSummary;
  active: boolean;
  watched: boolean;
  compared: boolean;
  onSelect: (productId: string) => void;
  onToggleWatchlist: (productId: string) => void;
  onToggleCompare: (productId: string) => void;
}) {
  return (
    <article className={`product-card ${active ? "active" : ""}`} onClick={() => onSelect(product.id)}>
      <div className="product-card-top">
        <span className="tag tag-muted">{product.category.name}</span>
        <div className="product-action-group">
          <button
            type="button"
            className={`watch-toggle ${compared ? "active" : ""}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggleCompare(product.id);
            }}
            aria-label={compared ? "Remove from compare" : "Add to compare"}
          >
            <Icon name="compare" />
          </button>
          <button
            type="button"
            className={`watch-toggle ${watched ? "active" : ""}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggleWatchlist(product.id);
            }}
            aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
          >
            <Icon name="star" />
          </button>
        </div>
      </div>
      <div className="product-visual">
        <span className="mono">
          {product.category.name} · {product.best_price_retailer ?? "Tracked"}
        </span>
      </div>
      <h3>{product.canonical_name}</h3>
      <p className="product-fingerprint">{product.fingerprint || "No fingerprint captured"}</p>
      <div className="product-card-bottom">
        <div>
          <strong className="price-strong">{formatCurrency(product.best_price)}</strong>
          <div className="muted-row">{product.best_price_retailer ?? "No active offer"}</div>
        </div>
        <div className="product-meta-stack">
          <span>{product.available_offer_count} live</span>
          <span>{product.retailers.length} retailers</span>
        </div>
      </div>
    </article>
  );
}

function ProductTable({
  products,
  selectedProductId,
  watchlistIds,
  compareIds,
  onSelect,
  onToggleWatchlist,
  onToggleCompare
}: {
  products: ProductSummary[];
  selectedProductId: string | null;
  watchlistIds: string[];
  compareIds: string[];
  onSelect: (productId: string) => void;
  onToggleWatchlist: (productId: string) => void;
  onToggleCompare: (productId: string) => void;
}) {
  return (
    <div className="panel table-panel">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Category</th>
              <th>Best Price</th>
              <th>Live</th>
              <th>Retailers</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <tr
                key={product.id}
                className={selectedProductId === product.id ? "row-active" : ""}
                onClick={() => onSelect(product.id)}
              >
                <td>
                  <div className="table-product-name">{product.canonical_name}</div>
                  <div className="table-subcopy mono">{product.fingerprint || "No fingerprint"}</div>
                </td>
                <td>
                  <span className="tag tag-muted">{product.category.name}</span>
                </td>
                <td className="mono">{formatCurrency(product.best_price)}</td>
                <td className="mono">{formatNumber(product.available_offer_count)}</td>
                <td>{product.retailers.join(", ")}</td>
                <td className="table-end">
                  <div className="table-action-group">
                    <button
                      type="button"
                      className={`watch-toggle compact ${compareIds.includes(product.id) ? "active" : ""}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggleCompare(product.id);
                      }}
                      aria-label="Toggle compare"
                    >
                      <Icon name="compare" />
                    </button>
                    <button
                      type="button"
                      className={`watch-toggle compact ${watchlistIds.includes(product.id) ? "active" : ""}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggleWatchlist(product.id);
                      }}
                      aria-label="Toggle watchlist"
                    >
                      <Icon name="star" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProductDetailPanel({
  detail,
  history,
  loading
}: {
  detail?: ProductDetail;
  history?: HistoryPayload;
  loading: boolean;
}) {
  const chartRows = useMemo(() => buildChartRows(history), [history]);

  if (loading) {
    return (
      <aside className="detail-panel">
        <div className="empty-state">
          <span className="eyebrow">Loading</span>
          <h3>Fetching product detail</h3>
          <p>Loading listings and price history for the selected canonical product.</p>
        </div>
      </aside>
    );
  }

  if (!detail) {
    return (
      <aside className="detail-panel">
        <div className="empty-state">
          <span className="eyebrow">Product Detail</span>
          <h3>Select a product</h3>
          <p>Use any row or card to inspect active offers, attributes, and price history.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="detail-panel">
      <div className="detail-header">
        <div>
          <span className="tag tag-cyan">{detail.category.name}</span>
          <h3>{detail.canonical_name}</h3>
        </div>
        <div className="detail-price-block">
          <strong>{formatCurrency(detail.best_price)}</strong>
          <span>{detail.best_price_retailer ?? "No active best offer"}</span>
        </div>
      </div>

      <div className="detail-attribute-list">
        {Object.entries(detail.attributes).length === 0 ? (
          <span className="tag tag-muted">No parsed attributes</span>
        ) : (
          Object.entries(detail.attributes).map(([key, value]) => (
            <span key={key} className="tag tag-muted">
              {key.replaceAll("_", " ")}: {String(value)}
            </span>
          ))
        )}
      </div>

      <div className="panel inner-panel">
        <div className="panel-head">
          <span>Price History</span>
          <span className="mono">{history?.series.length ?? 0} retailers</span>
        </div>
        {chartRows.length === 0 ? (
          <div className="panel-empty">No recorded history for this product yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartRows}>
              <CartesianGrid stroke="rgba(111, 125, 148, 0.16)" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#93a1b5", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: "#93a1b5", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `$${value}`}
              />
              <Tooltip
                contentStyle={{
                  background: "#171c24",
                  border: "1px solid rgba(111, 125, 148, 0.22)",
                  color: "#ecf2ff",
                  borderRadius: 6,
                  fontSize: 12
                }}
              />
              {history?.series.map((series, index) => (
                <Line
                  key={series.retailer.id}
                  type="monotone"
                  dataKey={series.retailer.name}
                  stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="panel inner-panel">
        <div className="panel-head">
          <span>Active Offers</span>
          <span className="mono">{detail.listings.length}</span>
        </div>
        <div className="offer-list">
          {detail.listings.map((listing) => (
            <a key={listing.id} href={listing.url} target="_blank" rel="noreferrer" className="offer-row">
              <div>
                <strong>{listing.retailer.name}</strong>
                <span>{formatStatusLabel(listing.status)}</span>
              </div>
              <div className="offer-price">
                <strong>{formatCurrency(listing.current_price)}</strong>
                {listing.previous_price ? <span>was {formatCurrency(listing.previous_price)}</span> : null}
              </div>
            </a>
          ))}
        </div>
      </div>
    </aside>
  );
}

function ReviewDetail({
  decision,
  pendingDecisionId,
  onResolve
}: {
  decision?: MatchDecision;
  pendingDecisionId?: number;
  onResolve: (decisionId: number, payload: MatchDecisionResolutionPayload) => void;
}) {
  const [candidateSearch, setCandidateSearch] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const deferredCandidateSearch = useDeferredValue(candidateSearch.trim());

  useEffect(() => {
    setCandidateSearch(decision?.retailer_listing.title ?? "");
    setResolutionNote("");
  }, [decision?.id, decision?.retailer_listing.title]);

  const candidatesQuery = useQuery({
    queryKey: ["review-candidates", decision?.id, deferredCandidateSearch],
    queryFn: () => fetchMatchCandidates(decision!.id, { search: deferredCandidateSearch || undefined, limit: 6 }),
    enabled: Boolean(decision)
  });

  if (!decision) {
    return (
      <div className="panel review-detail">
        <div className="empty-state">
          <span className="eyebrow">Review Detail</span>
          <h3>Select a queue item</h3>
          <p>Choose a listing from the queue to inspect candidate matches and resolve it.</p>
        </div>
      </div>
    );
  }

  const isResolving = pendingDecisionId === decision.id;

  return (
    <div className="panel review-detail">
      <div className="review-detail-head">
        <div>
          <div className="inline-tags">
            <span className="tag tag-cyan">{decision.retailer_listing.retailer.name}</span>
            <span className="tag tag-muted">{decision.retailer_listing.category?.name ?? "Uncategorised"}</span>
          </div>
          <h3>{decision.retailer_listing.title}</h3>
          <p className="detail-subcopy mono">{decision.fingerprint ?? "No fingerprint captured"}</p>
        </div>
        <a href={decision.retailer_listing.source_url} target="_blank" rel="noreferrer" className="ghost-link">
          <Icon name="external" />
          Open listing
        </a>
      </div>

      <div className="form-grid">
        <label className="field">
          <span>Candidate search</span>
          <input
            value={candidateSearch}
            onChange={(event) => setCandidateSearch(event.target.value)}
            placeholder="Search canonical products..."
          />
        </label>
        <label className="field">
          <span>Resolution note</span>
          <input
            value={resolutionNote}
            onChange={(event) => setResolutionNote(event.target.value)}
            placeholder="Optional reviewer rationale"
          />
        </label>
      </div>

      {decision.top_candidate ? (
        <div className="panel quick-match-panel">
          <div className="panel-head">
            <span>Top candidate</span>
            <span className="mono">{decision.top_candidate.score.toFixed(1)}</span>
          </div>
          <div className="quick-match-row">
            <div>
              <strong>{decision.top_candidate.canonical_product.canonical_name}</strong>
              <p className="detail-subcopy">{decision.top_candidate.reasons.join(" · ")}</p>
            </div>
            <button
              type="button"
              className="btn"
              disabled={isResolving}
              onClick={() =>
                onResolve(decision.id, {
                  decision: "manual_matched",
                  canonical_product_id: decision.top_candidate!.canonical_product.id,
                  rationale: resolutionNote || `Accepted top candidate ${decision.top_candidate!.canonical_product.canonical_name}`
                })
              }
            >
              Apply top candidate
            </button>
          </div>
        </div>
      ) : null}

      <div className="candidate-stack">
        <div className="panel-head">
          <span>Candidate matches</span>
          <span className="mono">{candidatesQuery.data?.length ?? 0}</span>
        </div>
        {candidatesQuery.isLoading ? <div className="panel-empty">Loading candidate products...</div> : null}
        {!candidatesQuery.isLoading && (candidatesQuery.data?.length ?? 0) === 0 ? (
          <div className="panel-empty">No candidate products matched the current search.</div>
        ) : null}
        {candidatesQuery.data?.map((candidate: MatchCandidate) => (
          <button
            key={candidate.canonical_product.id}
            type="button"
            className="candidate-row"
            disabled={isResolving}
            onClick={() =>
              onResolve(decision.id, {
                decision: "manual_matched",
                canonical_product_id: candidate.canonical_product.id,
                rationale: resolutionNote || `Matched to ${candidate.canonical_product.canonical_name}`
              })
            }
          >
            <div>
              <strong>{candidate.canonical_product.canonical_name}</strong>
              <span>{candidate.reasons.join(" · ")}</span>
            </div>
            <div className="candidate-metrics">
              <strong>{candidate.score.toFixed(1)}</strong>
              <span>{formatCurrency(candidate.best_price)}</span>
            </div>
          </button>
        ))}
      </div>

      <div className="review-actions">
        <button
          type="button"
          className="btn danger"
          disabled={isResolving}
          onClick={() =>
            onResolve(decision.id, {
              decision: "manual_rejected",
              rationale: resolutionNote || "Rejected during manual review"
            })
          }
        >
          Reject listing
        </button>
      </div>
    </div>
  );
}

function CompareScreen({
  products,
  compareIds,
  onRemove,
  onSelectProduct
}: {
  products: ProductSummary[];
  compareIds: string[];
  onRemove: (productId: string) => void;
  onSelectProduct: (productId: string) => void;
}) {
  const comparedProducts = products.filter((product) => compareIds.includes(product.id));
  const attributeKeys = Array.from(
    new Set(comparedProducts.flatMap((product) => Object.keys(product.attributes ?? {})))
  ).sort((left, right) => left.localeCompare(right));

  if (compareIds.length === 0) {
    return (
      <section className="workspace">
        <div className="panel-empty">
          No products are selected for comparison yet. Use the compare toggle from Catalog, Deals, or Watchlist.
        </div>
      </section>
    );
  }

  if (products.length === 0) {
    return (
      <section className="workspace">
        <div className="panel-empty">Loading product data for the compare workspace...</div>
      </section>
    );
  }

  return (
    <section className="workspace">
      <div className="compare-grid">
        {comparedProducts.map((product) => (
          <article key={product.id} className="panel compare-card">
            <div className="compare-card-head">
              <span className="tag tag-muted">{product.category.name}</span>
              <button type="button" className="watch-toggle compact" onClick={() => onRemove(product.id)}>
                <Icon name="compare" />
              </button>
            </div>
            <h3>{product.canonical_name}</h3>
            <p className="product-fingerprint">{product.fingerprint || "No fingerprint captured"}</p>
            <strong className="price-strong">{formatCurrency(product.best_price)}</strong>
            <div className="compare-stat-list">
              <span>{product.best_price_retailer ?? "No active best offer"}</span>
              <span>{product.available_offer_count} live offers</span>
              <span>{product.retailers.length} retailers</span>
              <span>
                Range {formatCurrency(product.price_range_min)} to {formatCurrency(product.price_range_max)}
              </span>
            </div>
            <button type="button" className="btn" onClick={() => onSelectProduct(product.id)}>
              Inspect product
            </button>
          </article>
        ))}
      </div>

      <div className="panel table-panel">
        <div className="panel-head">
          <span>Attribute comparison</span>
          <span className="mono">{comparedProducts.length} products</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Field</th>
                {comparedProducts.map((product) => (
                  <th key={product.id}>{product.canonical_name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Best price</td>
                {comparedProducts.map((product) => (
                  <td key={product.id} className="mono">
                    {formatCurrency(product.best_price)}
                  </td>
                ))}
              </tr>
              <tr>
                <td>Best retailer</td>
                {comparedProducts.map((product) => (
                  <td key={product.id}>{product.best_price_retailer ?? "—"}</td>
                ))}
              </tr>
              <tr>
                <td>Live offers</td>
                {comparedProducts.map((product) => (
                  <td key={product.id} className="mono">
                    {formatNumber(product.available_offer_count)}
                  </td>
                ))}
              </tr>
              <tr>
                <td>Retailers</td>
                {comparedProducts.map((product) => (
                  <td key={product.id}>{product.retailers.join(", ") || "—"}</td>
                ))}
              </tr>
              {attributeKeys.map((key) => (
                <tr key={key}>
                  <td>{key.replaceAll("_", " ")}</td>
                  {comparedProducts.map((product) => (
                    <td key={product.id}>{product.attributes[key] !== undefined ? String(product.attributes[key]) : "—"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function AlertsScreen({
  alerts,
  products,
  watchlistIds,
  onAddAlert,
  onDeleteAlert,
  onSelectProduct
}: {
  alerts: LocalPriceAlert[];
  products: ProductSummary[];
  watchlistIds: string[];
  onAddAlert: (productId: string, targetPrice: number) => void;
  onDeleteAlert: (alertId: string) => void;
  onSelectProduct: (productId: string) => void;
}) {
  const [newProductId, setNewProductId] = useState("");
  const [targetPriceInput, setTargetPriceInput] = useState("");
  const productMap = useMemo(() => new Map(products.map((product) => [product.id, product])), [products]);
  const watchlistProducts = products.filter((product) => watchlistIds.includes(product.id));
  const alertRows = alerts
    .map((alert) => {
      const product = productMap.get(alert.productId);
      return product ? { alert, product } : null;
    })
    .filter((row): row is { alert: LocalPriceAlert; product: ProductSummary } => Boolean(row));
  const triggeredCount = alertRows.filter(({ alert, product }) => (product.best_price ?? Number.POSITIVE_INFINITY) <= alert.targetPrice).length;
  const activeCount = alertRows.length - triggeredCount;

  function handleSubmit() {
    const parsedTarget = Number(targetPriceInput);
    if (!newProductId || !Number.isFinite(parsedTarget) || parsedTarget <= 0) {
      return;
    }
    onAddAlert(newProductId, parsedTarget);
    setTargetPriceInput("");
  }

  return (
    <section className="workspace">
      <div className="stats-grid">
        <StatCard label="Active" value={formatNumber(activeCount)} sublabel="still above target" />
        <StatCard label="Triggered" value={formatNumber(triggeredCount)} sublabel="target price reached" />
        <StatCard label="Total alerts" value={formatNumber(alertRows.length)} sublabel="stored in this browser" />
      </div>

      <div className="panel alert-form-panel">
        <div className="panel-head">
          <span>Create alert</span>
          <span className="mono">Local only</span>
        </div>
        <div className="alert-form-grid">
          <label className="field">
            <span>Product</span>
            <select value={newProductId} onChange={(event) => setNewProductId(event.target.value)} className="toolbar-select">
              <option value="">Select product</option>
              {(watchlistProducts.length > 0 ? watchlistProducts : products.slice(0, 200)).map((product) => (
                <option key={product.id} value={product.id}>
                  {product.canonical_name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Target price</span>
            <input
              value={targetPriceInput}
              onChange={(event) => setTargetPriceInput(event.target.value)}
              placeholder="e.g. 899"
              inputMode="numeric"
            />
          </label>
          <div className="alert-form-actions">
            <button type="button" className="btn" onClick={handleSubmit}>
              Add alert
            </button>
          </div>
        </div>
      </div>

      <div className="panel table-panel">
        <div className="panel-head">
          <span>Tracked alerts</span>
          <span className="mono">{alertRows.length}</span>
        </div>
        {alertRows.length === 0 ? (
          <div className="panel-empty">No price alerts yet. Add one above to track a target price locally.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Current</th>
                  <th>Target</th>
                  <th>Gap</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {alertRows.map(({ alert, product }) => {
                  const currentPrice = product.best_price ?? Number.POSITIVE_INFINITY;
                  const triggered = currentPrice <= alert.targetPrice;
                  const gap = Number.isFinite(currentPrice) ? currentPrice - alert.targetPrice : null;
                  return (
                    <tr key={alert.id} onClick={() => onSelectProduct(product.id)}>
                      <td>
                        <div className="table-product-name">{product.canonical_name}</div>
                        <div className="table-subcopy mono">{product.category.name}</div>
                      </td>
                      <td className="mono">{formatCurrency(product.best_price)}</td>
                      <td className="mono">{formatCurrency(alert.targetPrice)}</td>
                      <td className="mono">{gap === null ? "—" : formatCurrency(gap)}</td>
                      <td>
                        <span className={triggered ? "tag tag-green" : "tag tag-amber"}>
                          {triggered ? "Triggered" : "Watching"}
                        </span>
                      </td>
                      <td className="mono">{alert.createdAt}</td>
                      <td className="table-end">
                        <button
                          type="button"
                          className="btn btn-inline"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteAlert(alert.id);
                          }}
                          aria-label="Delete alert"
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function RetailerHealthTable({
  retailerSummaries,
  onOpenRetailers
}: {
  retailerSummaries: RetailerHealthSummary[];
  onOpenRetailers?: () => void;
}) {
  return (
    <div className="panel table-panel">
      <div className="panel-head">
        <span>Retailer health</span>
        {onOpenRetailers ? (
          <button type="button" className="btn btn-inline" onClick={onOpenRetailers}>
            Open retailers
          </button>
        ) : (
          <span className="mono">{retailerSummaries.length}</span>
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Retailer</th>
              <th>Health</th>
              <th>Latest run</th>
              <th>Last success</th>
              <th>Age</th>
              <th>Offers</th>
              <th>Seen</th>
            </tr>
          </thead>
          <tbody>
            {retailerSummaries.map((summary) => (
              <tr key={summary.retailer.id}>
                <td>
                  <div className="table-product-name">{summary.retailer.name}</div>
                  <div className="table-subcopy mono">{summary.latest_scrape_run_scraper_name ?? "No scraper run"}</div>
                </td>
                <td>
                  <span className={statusTone(summary.status)}>{formatStatusLabel(summary.status)}</span>
                </td>
                <td className="mono">{formatShortDate(summary.latest_scrape_run_started_at)}</td>
                <td className="mono">{formatShortDate(summary.latest_successful_scrape_finished_at)}</td>
                <td className="mono">
                  {summary.successful_scrape_age_hours === undefined || summary.successful_scrape_age_hours === null
                    ? "—"
                    : `${summary.successful_scrape_age_hours}h`}
                </td>
                <td className="mono">{formatNumber(summary.active_offer_count)}</td>
                <td className="mono">{formatNumber(summary.latest_scrape_run_listings_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DataQualityScreen({
  dataQuality,
  loading,
  onOpenReview,
  onOpenRetailers
}: {
  dataQuality?: DataQualityPayload;
  loading: boolean;
  onOpenReview: () => void;
  onOpenRetailers: () => void;
}) {
  if (loading && !dataQuality) {
    return <div className="panel-empty">Loading data quality metrics...</div>;
  }

  if (!dataQuality) {
    return <div className="panel-empty">Data quality metrics are unavailable right now.</div>;
  }

  return (
    <section className="workspace">
      <div className="stats-grid">
        <StatCard
          label="Review Queue"
          value={formatNumber(dataQuality.review_queue_count)}
          sublabel="pending decisions"
        />
        <StatCard
          label="High Confidence"
          value={formatNumber(dataQuality.high_confidence_review_count)}
          sublabel="90%+ matcher confidence"
        />
        <StatCard
          label="Stale Offers"
          value={formatNumber(dataQuality.stale_offer_count)}
          sublabel={`${dataQuality.stale_offer_threshold_days}+ days old`}
        />
        <StatCard
          label="Unpriced Offers"
          value={formatNumber(dataQuality.unpriced_active_offer_count)}
          sublabel="available without current price"
        />
        <StatCard
          label="Uncategorised"
          value={formatNumber(dataQuality.uncategorized_listing_count)}
          sublabel="available retailer listings"
        />
        <StatCard
          label="Stale Retailers"
          value={formatNumber(dataQuality.stale_retailer_count)}
          sublabel="failed, stale, or never run"
        />
      </div>

      <div className="panel table-panel issue-panel">
        <div className="panel-head">
          <span>Operational issues</span>
          <div className="panel-head-actions">
            <button type="button" className="btn btn-inline" onClick={onOpenReview}>
              Open review queue
            </button>
            <button type="button" className="btn btn-inline" onClick={onOpenRetailers}>
              Open retailers
            </button>
          </div>
        </div>
        <div className="issue-grid">
          {dataQuality.issues.map((issue) => (
            <article key={issue.key} className="panel issue-card">
              <div className="compare-card-head">
                <strong className="table-product-name">{issue.label}</strong>
                <span className={issueTone(issue.severity)}>{formatStatusLabel(issue.severity)}</span>
              </div>
              <div className="issue-count mono">{formatNumber(issue.count)}</div>
              <p className="detail-subcopy">{issue.detail}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="dq-grid">
        <div className="panel table-panel">
          <div className="panel-head">
            <span>Queue by retailer</span>
            <span className="mono">{dataQuality.retailer_queue.length}</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Retailer</th>
                  <th>Pending</th>
                  <th>High confidence</th>
                  <th>Low confidence</th>
                  <th>Live offers</th>
                </tr>
              </thead>
              <tbody>
                {dataQuality.retailer_queue.map((row) => (
                  <tr key={row.retailer.id}>
                    <td>
                      <div className="table-product-name">{row.retailer.name}</div>
                      <div className="table-subcopy mono">{row.retailer.url}</div>
                    </td>
                    <td className="mono">{formatNumber(row.pending_review_count)}</td>
                    <td className="mono">{formatNumber(row.high_confidence_review_count)}</td>
                    <td className="mono">{formatNumber(row.low_confidence_review_count)}</td>
                    <td className="mono">{formatNumber(row.active_offer_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel table-panel">
          <div className="panel-head">
            <span>Queue by category</span>
            <span className="mono">{dataQuality.category_queue.length}</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Pending</th>
                  <th>High confidence</th>
                  <th>Live offers</th>
                  <th>Canonical</th>
                </tr>
              </thead>
              <tbody>
                {dataQuality.category_queue.map((row) => (
                  <tr key={row.category?.id ?? "uncategorised"}>
                    <td>
                      <div className="table-product-name">{row.category?.name ?? "Uncategorised"}</div>
                    </td>
                    <td className="mono">{formatNumber(row.pending_review_count)}</td>
                    <td className="mono">{formatNumber(row.high_confidence_review_count)}</td>
                    <td className="mono">{formatNumber(row.active_offer_count)}</td>
                    <td className="mono">{formatNumber(row.canonical_product_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}

function ProductsScreen({
  products,
  loading,
  selectedProductId,
  onSelectProduct,
  detail,
  history,
  detailLoading
}: {
  products: ProductSummary[];
  loading: boolean;
  selectedProductId: string | null;
  onSelectProduct: (productId: string) => void;
  detail?: ProductDetail;
  history?: HistoryPayload;
  detailLoading: boolean;
}) {
  const liveCoverageCount = products.filter((product) => product.available_offer_count > 0).length;
  const gapCount = products.filter((product) => product.available_offer_count === 0).length;
  const singleRetailerCount = products.filter((product) => product.retailers.length <= 1).length;

  return (
    <section className="workspace workspace-split">
      <div className="workspace-primary">
        <div className="stats-grid">
          <StatCard
            label="Canonical Products"
            value={formatNumber(products.length)}
            sublabel="rows in current admin view"
          />
          <StatCard
            label="Live Coverage"
            value={formatNumber(liveCoverageCount)}
            sublabel="products with active offers"
          />
          <StatCard
            label="Coverage Gaps"
            value={formatNumber(gapCount)}
            sublabel="products without live offers"
          />
          <StatCard
            label="Single Retailer"
            value={formatNumber(singleRetailerCount)}
            sublabel="canonical rows with 1 source"
          />
        </div>

        <div className="panel table-panel">
          <div className="panel-head">
            <span>Canonical coverage</span>
            <span className="mono">{formatNumber(products.length)}</span>
          </div>
          {loading ? <div className="panel-empty">Loading canonical products...</div> : null}
          {!loading && products.length === 0 ? (
            <div className="panel-empty">No canonical products matched the current admin filters.</div>
          ) : null}
          {!loading && products.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Canonical product</th>
                    <th>Status</th>
                    <th>Category</th>
                    <th>Best price</th>
                    <th>Live offers</th>
                    <th>Total offers</th>
                    <th>Retailers</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => {
                    const status =
                      product.available_offer_count === 0
                        ? "gap"
                        : product.retailers.length <= 1
                          ? "thin"
                          : "covered";
                    return (
                      <tr
                        key={product.id}
                        className={selectedProductId === product.id ? "row-active" : ""}
                        onClick={() => onSelectProduct(product.id)}
                      >
                        <td>
                          <div className="table-product-name">{product.canonical_name}</div>
                          <div className="table-subcopy mono">{product.fingerprint || "No fingerprint"}</div>
                        </td>
                        <td>
                          <span
                            className={
                              status === "gap"
                                ? "tag tag-red"
                                : status === "thin"
                                  ? "tag tag-amber"
                                  : "tag tag-green"
                            }
                          >
                            {status === "gap" ? "No live offers" : status === "thin" ? "Thin coverage" : "Covered"}
                          </span>
                        </td>
                        <td>
                          <span className="tag tag-muted">{product.category.name}</span>
                        </td>
                        <td className="mono">{formatCurrency(product.best_price)}</td>
                        <td className="mono">{formatNumber(product.available_offer_count)}</td>
                        <td className="mono">{formatNumber(product.offer_count)}</td>
                        <td>{product.retailers.length > 0 ? product.retailers.join(", ") : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>

      <ProductDetailPanel detail={detail} history={history} loading={detailLoading} />
    </section>
  );
}

function PlaceholderScreen({ screen }: { screen: Screen }) {
  return (
    <section className="placeholder-screen">
      <div className="panel placeholder-panel">
        <span className="tag tag-muted">Planned Surface</span>
        <h2>{SCREEN_META[screen].title}</h2>
        <p>{SCREEN_META[screen].subtitle}</p>
        <p>
          This screen is present in the imported design, but the current backend/frontend feature set does not yet provide
          a real implementation path for it.
        </p>
      </div>
    </section>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [screen, setScreen] = useState<Screen>("catalog");
  const [catalogMode, setCatalogMode] = useState<CatalogMode>("grid");
  const [searchInput, setSearchInput] = useState("");
  const [reviewSearchInput, setReviewSearchInput] = useState("");
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | undefined>(undefined);
  const [reviewCategoryId, setReviewCategoryId] = useState<number | undefined>(undefined);
  const [productCoverageFilter, setProductCoverageFilter] = useState<ProductCoverageFilter>("all");
  const [reviewSortBy, setReviewSortBy] = useState("confidence_desc");
  const [reviewQueueOffset, setReviewQueueOffset] = useState(0);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null);
  const [watchlistIds, setWatchlistIds] = useState<string[]>(() => readWatchlist());
  const [compareIds, setCompareIds] = useState<string[]>(() => readCompareList());
  const [alerts, setAlerts] = useState<LocalPriceAlert[]>(() => readAlerts());
  const deferredSearch = useDeferredValue(searchInput.trim());
  const deferredReviewSearch = useDeferredValue(reviewSearchInput.trim());

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlistIds));
    }
  }, [watchlistIds]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(compareIds));
    }
  }, [compareIds]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALERTS_STORAGE_KEY, JSON.stringify(alerts));
    }
  }, [alerts]);

  const filtersQuery = useQuery({
    queryKey: ["v2-filters", selectedCategoryId],
    queryFn: () => fetchFilters(selectedCategoryId)
  });

  const healthQuery = useQuery({
    queryKey: ["v2-health"],
    queryFn: fetchHealth
  });

  const dataQualityQuery = useQuery({
    queryKey: ["v2-data-quality"],
    queryFn: fetchDataQuality,
    enabled: screen === "dq"
  });

  const productsQuery = useQuery({
    queryKey: ["v2-products", deferredSearch, selectedCategoryId],
    queryFn: () =>
      fetchProducts({
        search: deferredSearch || undefined,
        category_id: selectedCategoryId,
        hide_unavailable: true,
        page: 1,
        page_size: 80
      })
  });

  const allProductsQuery = useQuery({
    queryKey: ["v2-products-all"],
    queryFn: () =>
      fetchProducts({
        hide_unavailable: true,
        page: 1,
        page_size: 2500
      }),
    enabled: screen === "watchlist" || screen === "compare" || screen === "alerts" || compareIds.length > 0 || alerts.length > 0
  });

  const productsAdminQuery = useQuery({
    queryKey: ["v2-products-admin", deferredSearch, selectedCategoryId],
    queryFn: () =>
      fetchProducts({
        search: deferredSearch || undefined,
        category_id: selectedCategoryId,
        hide_unavailable: false,
        sort_by: "name",
        sort_order: "asc",
        page: 1,
        page_size: 2500
      }),
    enabled: screen === "products"
  });

  const trendsQuery = useQuery({
    queryKey: ["v2-trends"],
    queryFn: fetchTrends
  });

  const reviewQueueQuery = useQuery({
    queryKey: ["v2-match-decisions", "needs_review", deferredReviewSearch, reviewCategoryId, reviewSortBy, reviewQueueOffset],
    queryFn: () =>
      fetchMatchDecisions({
        decision: "needs_review",
        search: deferredReviewSearch || undefined,
        category_id: reviewCategoryId,
        sort_by: reviewSortBy,
        limit: REVIEW_PAGE_SIZE,
        offset: reviewQueueOffset
      })
  });

  const scrapeRunsQuery = useQuery({
    queryKey: ["v2-scrape-runs"],
    queryFn: () => fetchScrapeRuns({ limit: 12 })
  });

  const detailQuery = useQuery({
    queryKey: ["v2-product", selectedProductId],
    queryFn: () => fetchProduct(selectedProductId!),
    enabled: Boolean(selectedProductId)
  });

  const historyQuery = useQuery({
    queryKey: ["v2-history", selectedProductId],
    queryFn: () => fetchHistory(selectedProductId!),
    enabled: Boolean(selectedProductId)
  });

  const resolveDecisionMutation = useMutation({
    mutationFn: ({ decisionId, payload }: { decisionId: number; payload: MatchDecisionResolutionPayload }) =>
      resolveMatchDecision(decisionId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["v2-match-decisions"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-health"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-products"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-products-admin"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-product"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-history"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-filters"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-trends"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-scrape-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-data-quality"] })
      ]);
    }
  });

  const bulkTopCandidateMutation = useMutation({
    mutationFn: (decisionIds: number[]) =>
      bulkApplyTopCandidates({
        decision_ids: decisionIds,
        min_score: 95.0,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["v2-match-decisions"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-health"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-products"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-products-admin"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-product"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-history"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-filters"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-trends"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-scrape-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-data-quality"] })
      ]);
    }
  });

  const visibleProducts = productsQuery.data?.products ?? [];
  const adminProducts = productsAdminQuery.data?.products ?? [];
  const allProducts = allProductsQuery.data?.products ?? [];
  const visibleTrends = trendsQuery.data ?? [];
  const reviewQueuePage = reviewQueueQuery.data;
  const reviewQueue = reviewQueuePage?.decisions ?? [];
  const scrapeRuns = scrapeRunsQuery.data ?? [];
  const health = healthQuery.data;
  const dataQuality = dataQualityQuery.data;
  const retailerSummaries = health?.retailer_summaries ?? [];
  const selectedDetail = detailQuery.data;
  const selectedDecision = reviewQueue.find((decision) => decision.id === selectedReviewId);
  const pendingDecisionId = resolveDecisionMutation.isPending ? resolveDecisionMutation.variables?.decisionId : undefined;
  const reviewQueueTotal = reviewQueuePage?.total ?? health?.review_queue_count ?? reviewQueue.length;
  const bulkEligibleDecisionIds = reviewQueue
    .filter((decision) => (decision.top_candidate?.score ?? 0) >= 95)
    .map((decision) => decision.id);

  useEffect(() => {
    if (reviewQueue.length === 0) {
      setSelectedReviewId(null);
      return;
    }
    if (!selectedReviewId || !reviewQueue.some((decision) => decision.id === selectedReviewId)) {
      setSelectedReviewId(reviewQueue[0].id);
    }
  }, [reviewQueue, selectedReviewId]);

  const filteredWatchlist = useMemo(() => {
    const source = allProducts.length > 0 ? allProducts : visibleProducts;
    return source.filter((product) => {
      if (!watchlistIds.includes(product.id)) {
        return false;
      }
      if (selectedCategoryId !== undefined && product.category.id !== selectedCategoryId) {
        return false;
      }
      if (!deferredSearch) {
        return true;
      }
      const haystack = `${product.canonical_name} ${product.fingerprint} ${product.best_price_retailer ?? ""}`.toLowerCase();
      return haystack.includes(deferredSearch.toLowerCase());
    });
  }, [allProducts, visibleProducts, watchlistIds, selectedCategoryId, deferredSearch]);

  const filteredAdminProducts = useMemo(() => {
    return adminProducts.filter((product) => {
      if (productCoverageFilter === "live" && product.available_offer_count <= 0) {
        return false;
      }
      if (productCoverageFilter === "gaps" && product.available_offer_count > 0) {
        return false;
      }
      return true;
    });
  }, [adminProducts, productCoverageFilter]);

  const navItems = useMemo<Record<Screen, NavItem>>(
    () => ({
      catalog: { key: "catalog", label: "Catalog", implemented: true },
      deals: { key: "deals", label: "Deals", implemented: true },
      watchlist: { key: "watchlist", label: "Watchlist", count: filteredWatchlist.length, implemented: true },
      alerts: { key: "alerts", label: "Price Alerts", count: alerts.length, implemented: true },
      compare: { key: "compare", label: "Compare", count: compareIds.length, implemented: true },
      products: { key: "products", label: "Products", implemented: true },
      review: { key: "review", label: "Review Queue", count: reviewQueueTotal, implemented: true },
      dq: { key: "dq", label: "Data Quality", implemented: true },
      retailers: { key: "retailers", label: "Retailers", implemented: true },
      scraper: { key: "scraper", label: "Scraper Health", implemented: true },
      analytics: { key: "analytics", label: "Analytics", implemented: false },
      settings: { key: "settings", label: "Settings", implemented: false }
    }),
    [alerts.length, compareIds.length, filteredWatchlist.length, reviewQueueTotal]
  );

  const hasNextReviewPage = reviewQueueOffset + reviewQueue.length < reviewQueueTotal;
  const screenMeta = SCREEN_META[screen];

  function handleSelectProduct(productId: string) {
    setSelectedProductId(productId);
  }

  function handleSelectTrend(productId: string) {
    setSelectedProductId(productId);
    setScreen("deals");
  }

  function handleToggleWatchlist(productId: string) {
    setWatchlistIds((current) =>
      current.includes(productId) ? current.filter((id) => id !== productId) : [...current, productId]
    );
  }

  function handleToggleCompare(productId: string) {
    setCompareIds((current) =>
      current.includes(productId) ? current.filter((id) => id !== productId) : [...current, productId].slice(-4)
    );
  }

  function handleAddAlert(productId: string, targetPrice: number) {
    setAlerts((current) => {
      const existing = current.find((alert) => alert.productId === productId && alert.targetPrice === targetPrice);
      if (existing) {
        return current;
      }
      return [
        {
          id: `alert-${Date.now()}-${productId}`,
          productId,
          targetPrice,
          createdAt: new Date().toLocaleDateString("en-AU")
        },
        ...current
      ];
    });
  }

  function handleReviewSearchChange(value: string) {
    startTransition(() => {
      setReviewSearchInput(value);
      setReviewQueueOffset(0);
    });
  }

  function handleReviewCategoryChange(value?: number) {
    startTransition(() => {
      setReviewCategoryId(value);
      setReviewQueueOffset(0);
    });
  }

  function handleReviewSortChange(value: string) {
    startTransition(() => {
      setReviewSortBy(value);
      setReviewQueueOffset(0);
    });
  }

  function renderTopbarControls() {
    if (screen === "catalog" || screen === "deals" || screen === "watchlist" || screen === "products") {
      return (
        <>
          <label className="search-wrap">
            <span className="search-icon">
              <Icon name="search" />
            </span>
            <input
              className="search-input"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search products, models, fingerprints..."
            />
          </label>
          <select
            className="toolbar-select"
            value={selectedCategoryId ?? ""}
            onChange={(event) => setSelectedCategoryId(event.target.value ? Number(event.target.value) : undefined)}
          >
            <option value="">All categories</option>
            {filtersQuery.data?.categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
          {screen === "products" ? (
            <select
              className="toolbar-select"
              value={productCoverageFilter}
              onChange={(event) => setProductCoverageFilter(event.target.value as ProductCoverageFilter)}
            >
              <option value="all">All coverage</option>
              <option value="live">Has live offers</option>
              <option value="gaps">No live offers</option>
            </select>
          ) : null}
          {screen === "catalog" ? (
            <div className="toolbar-toggle">
              <button
                type="button"
                className={catalogMode === "list" ? "active" : ""}
                onClick={() => setCatalogMode("list")}
              >
                List
              </button>
              <button
                type="button"
                className={catalogMode === "grid" ? "active" : ""}
                onClick={() => setCatalogMode("grid")}
              >
                Grid
              </button>
            </div>
          ) : null}
        </>
      );
    }

    if (screen === "review") {
      return (
        <>
          <label className="search-wrap">
            <span className="search-icon">
              <Icon name="search" />
            </span>
            <input
              className="search-input"
              value={reviewSearchInput}
              onChange={(event) => handleReviewSearchChange(event.target.value)}
              placeholder="Search listing title or fingerprint..."
            />
          </label>
          <select
            className="toolbar-select"
            value={reviewCategoryId ?? ""}
            onChange={(event) => handleReviewCategoryChange(event.target.value ? Number(event.target.value) : undefined)}
          >
            <option value="">All categories</option>
            {filtersQuery.data?.categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
              ))}
          </select>
          <select className="toolbar-select" value={reviewSortBy} onChange={(event) => handleReviewSortChange(event.target.value)}>
            <option value="confidence_desc">High confidence first</option>
            <option value="created_desc">Newest first</option>
          </select>
          <div className="toolbar-toggle">
            <button type="button" onClick={() => setReviewQueueOffset((current) => Math.max(0, current - REVIEW_PAGE_SIZE))}>
              Prev
            </button>
            <button
              type="button"
              onClick={() => setReviewQueueOffset((current) => current + REVIEW_PAGE_SIZE)}
              disabled={!hasNextReviewPage}
            >
              Next
            </button>
          </div>
        </>
      );
    }

    return null;
  }

  function renderContent() {
    if (!screenMeta.implemented) {
      return <PlaceholderScreen screen={screen} />;
    }

    if (screen === "catalog") {
      return (
        <section className="workspace workspace-split">
          <div className="workspace-primary">
            <div className="section-strip">
              <span className="section-title">Canonical catalog</span>
              <span className="section-count">{formatNumber(productsQuery.data?.total)} total products</span>
            </div>
            {productsQuery.isLoading ? <div className="panel-empty">Loading products...</div> : null}
            {!productsQuery.isLoading && visibleProducts.length === 0 ? (
              <div className="panel-empty">No products matched the current search and category filters.</div>
            ) : null}
            {catalogMode === "grid" ? (
              <div className="product-grid">
                {visibleProducts.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    active={selectedProductId === product.id}
                    watched={watchlistIds.includes(product.id)}
                    compared={compareIds.includes(product.id)}
                    onSelect={handleSelectProduct}
                    onToggleWatchlist={handleToggleWatchlist}
                    onToggleCompare={handleToggleCompare}
                  />
                ))}
              </div>
            ) : (
              <ProductTable
                products={visibleProducts}
                selectedProductId={selectedProductId}
                watchlistIds={watchlistIds}
                compareIds={compareIds}
                onSelect={handleSelectProduct}
                onToggleWatchlist={handleToggleWatchlist}
                onToggleCompare={handleToggleCompare}
              />
            )}
          </div>
          <ProductDetailPanel detail={selectedDetail} history={historyQuery.data} loading={detailQuery.isLoading || historyQuery.isLoading} />
        </section>
      );
    }

    if (screen === "deals") {
      return (
        <section className="workspace workspace-split">
          <div className="workspace-primary">
            <div className="section-strip">
              <span className="section-title">Recent price drops</span>
              <span className="section-count">{visibleTrends.length} tracked movements</span>
            </div>
            <div className="panel table-panel">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Category</th>
                      <th>From</th>
                      <th>To</th>
                      <th>Drop</th>
                      <th>Retailers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleTrends.map((trend: Trend) => (
                      <tr key={trend.product.id} onClick={() => handleSelectTrend(trend.product.id)}>
                        <td>
                          <div className="table-product-name">{trend.product.canonical_name}</div>
                          <div className="table-subcopy mono">{trend.product.best_price_retailer ?? "Best offer tracked"}</div>
                        </td>
                        <td>
                          <span className="tag tag-muted">{trend.product.category.name}</span>
                        </td>
                        <td className="mono">{formatCurrency(trend.initial_price)}</td>
                        <td className="mono">{formatCurrency(trend.latest_price)}</td>
                        <td>
                          <span className="tag tag-green">
                            {trend.price_drop_percentage.toFixed(1)}% / {formatCurrency(trend.price_drop_amount)}
                          </span>
                        </td>
                        <td>{trend.product.retailers.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <ProductDetailPanel detail={selectedDetail} history={historyQuery.data} loading={detailQuery.isLoading || historyQuery.isLoading} />
        </section>
      );
    }

    if (screen === "watchlist") {
      return (
        <section className="workspace workspace-split">
          <div className="workspace-primary">
            <div className="section-strip">
              <span className="section-title">Watched products</span>
              <span className="section-count">{filteredWatchlist.length} local watch items</span>
            </div>
            {filteredWatchlist.length === 0 ? (
              <div className="panel-empty">
                No products are in the local watchlist yet. Use the star control from Catalog to add products here.
              </div>
            ) : (
              <ProductTable
                products={filteredWatchlist}
                selectedProductId={selectedProductId}
                watchlistIds={watchlistIds}
                compareIds={compareIds}
                onSelect={handleSelectProduct}
                onToggleWatchlist={handleToggleWatchlist}
                onToggleCompare={handleToggleCompare}
              />
            )}
          </div>
          <ProductDetailPanel detail={selectedDetail} history={historyQuery.data} loading={detailQuery.isLoading || historyQuery.isLoading} />
        </section>
      );
    }

    if (screen === "compare") {
      return (
        <CompareScreen
          products={allProducts}
          compareIds={compareIds}
          onRemove={handleToggleCompare}
          onSelectProduct={(productId) => {
            handleSelectProduct(productId);
            setScreen("catalog");
          }}
        />
      );
    }

    if (screen === "alerts") {
      return (
        <AlertsScreen
          alerts={alerts}
          products={allProducts}
          watchlistIds={watchlistIds}
          onAddAlert={handleAddAlert}
          onDeleteAlert={(alertId) => setAlerts((current) => current.filter((alert) => alert.id !== alertId))}
          onSelectProduct={(productId) => {
            handleSelectProduct(productId);
            setScreen("catalog");
          }}
        />
      );
    }

    if (screen === "products") {
      return (
        <ProductsScreen
          products={filteredAdminProducts}
          loading={productsAdminQuery.isLoading}
          selectedProductId={selectedProductId}
          onSelectProduct={handleSelectProduct}
          detail={selectedDetail}
          history={historyQuery.data}
          detailLoading={detailQuery.isLoading || historyQuery.isLoading}
        />
      );
    }

    if (screen === "review") {
      return (
        <section className="workspace review-workspace">
          <div className="review-queue-panel panel">
            <div className="panel-head">
              <span>Pending queue</span>
              <div className="panel-head-actions">
                <span className="mono">
                  {reviewQueueOffset + 1}-{reviewQueueOffset + reviewQueue.length} / {formatNumber(reviewQueueTotal)}
                </span>
                <button
                  type="button"
                  className="btn btn-inline"
                  disabled={bulkEligibleDecisionIds.length === 0 || bulkTopCandidateMutation.isPending}
                  onClick={() => bulkTopCandidateMutation.mutate(bulkEligibleDecisionIds)}
                >
                  Apply visible top matches ({bulkEligibleDecisionIds.length})
                </button>
              </div>
            </div>
            {resolveDecisionMutation.error ? (
              <div className="inline-error">{resolveDecisionMutation.error.message}</div>
            ) : null}
            {bulkTopCandidateMutation.error ? (
              <div className="inline-error">{bulkTopCandidateMutation.error.message}</div>
            ) : null}
            {bulkTopCandidateMutation.data ? (
              <div className="panel-note">
                Applied {bulkTopCandidateMutation.data.resolved_ids.length} matches
                {bulkTopCandidateMutation.data.skipped.length > 0
                  ? `, skipped ${bulkTopCandidateMutation.data.skipped.length}.`
                  : "."}
              </div>
            ) : null}
            <div className="queue-list">
              {reviewQueueQuery.isLoading ? <div className="panel-empty">Loading review queue...</div> : null}
              {!reviewQueueQuery.isLoading && reviewQueue.length === 0 ? (
                <div className="panel-empty">No review items matched the current queue filters.</div>
              ) : null}
              {reviewQueue.map((decision) => (
                <button
                  key={decision.id}
                  type="button"
                  className={`queue-item ${selectedReviewId === decision.id ? "active" : ""}`}
                  onClick={() => setSelectedReviewId(decision.id)}
                >
                  <div className="queue-item-top">
                    <span className="tag tag-cyan">{decision.retailer_listing.retailer.name}</span>
                    <span className="tag tag-muted">{decision.retailer_listing.category?.name ?? "Uncategorised"}</span>
                  </div>
                  <strong>{decision.retailer_listing.title}</strong>
                  <span className="queue-fingerprint mono">{decision.fingerprint ?? "No fingerprint"}</span>
                  <div className="queue-item-metrics">
                    <span className="tag tag-muted">
                      confidence {decision.confidence !== null && decision.confidence !== undefined ? `${Math.round(decision.confidence * 100)}%` : "—"}
                    </span>
                    {decision.top_candidate ? <span className="tag tag-green">top {decision.top_candidate.score.toFixed(1)}</span> : null}
                  </div>
                  {decision.top_candidate ? (
                    <span className="queue-top-candidate">
                      {decision.top_candidate.canonical_product.canonical_name}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          </div>
          <ReviewDetail
            decision={selectedDecision}
            pendingDecisionId={pendingDecisionId}
            onResolve={(decisionId, payload) => resolveDecisionMutation.mutate({ decisionId, payload })}
          />
        </section>
      );
    }

    if (screen === "dq") {
      return (
        <DataQualityScreen
          dataQuality={dataQuality}
          loading={dataQualityQuery.isLoading}
          onOpenReview={() => setScreen("review")}
          onOpenRetailers={() => setScreen("retailers")}
        />
      );
    }

    if (screen === "retailers") {
      return (
        <section className="workspace">
          <div className="stats-grid">
            <StatCard
              label="Healthy"
              value={formatNumber(retailerSummaries.filter((summary) => summary.status === "ok").length)}
              sublabel="fresh successful coverage"
            />
            <StatCard
              label="Attention"
              value={formatNumber(retailerSummaries.filter((summary) => summary.status === "failed" || summary.status === "stale").length)}
              sublabel="failed or stale retailers"
            />
            <StatCard
              label="Running"
              value={formatNumber(retailerSummaries.filter((summary) => summary.status === "running").length)}
              sublabel="currently active scrapers"
            />
            <StatCard
              label="Never Run"
              value={formatNumber(retailerSummaries.filter((summary) => summary.status === "never_run").length)}
              sublabel="no successful scrape recorded"
            />
          </div>

          <RetailerHealthTable retailerSummaries={retailerSummaries} />

          <div className="retailer-card-grid">
            {retailerSummaries.map((summary) => (
              <article key={summary.retailer.id} className="panel retailer-card">
                <div className="compare-card-head">
                  <strong className="table-product-name">{summary.retailer.name}</strong>
                  <span className={statusTone(summary.status)}>{formatStatusLabel(summary.status)}</span>
                </div>
                <div className="compare-stat-list">
                  <span>{summary.active_offer_count} live offers</span>
                  <span>Latest run: {formatTimestamp(summary.latest_scrape_run_started_at)}</span>
                  <span>Last success: {formatTimestamp(summary.latest_successful_scrape_finished_at)}</span>
                  <span>
                    Stale after {summary.stale_after_hours}h
                    {summary.successful_scrape_age_hours !== undefined && summary.successful_scrape_age_hours !== null
                      ? ` · now ${summary.successful_scrape_age_hours}h old`
                      : ""}
                  </span>
                </div>
                {summary.latest_scrape_run_error_summary ? (
                  <div className="inline-error retailer-inline-error">{summary.latest_scrape_run_error_summary}</div>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      );
    }

    return (
      <section className="workspace">
        <div className="workspace-primary">
          <div className="stats-grid">
            <StatCard label="System" value={health?.status ?? "loading"} sublabel="health endpoint status" />
            <StatCard label="Retailers" value={formatNumber(health?.retailer_count)} sublabel="configured sources" />
            <StatCard label="Categories" value={formatNumber(health?.category_count)} sublabel="catalog groups" />
            <StatCard label="Active Offers" value={formatNumber(health?.active_offer_count)} sublabel="current live offers" />
            <StatCard label="Review Queue" value={formatNumber(reviewQueueTotal)} sublabel="pending decisions" />
            <StatCard label="Canonical Products" value={formatNumber(health?.canonical_product_count)} sublabel="grouped catalog rows" />
          </div>

          <div className="panel latest-run-panel">
            <div className="panel-head">
              <span>Latest scrape run</span>
              <span className={statusTone(health?.latest_scrape_run_status)}>
                {formatStatusLabel(health?.latest_scrape_run_status)}
              </span>
            </div>
            <div className="latest-run-grid">
              <div>
                <strong className="latest-run-title">
                  {health?.latest_scrape_run_retailer_name ?? health?.latest_scrape_run_scraper_name ?? "No scrape runs"}
                </strong>
                <p className="detail-subcopy">
                  Started {formatTimestamp(health?.latest_scrape_run_started_at)}.
                  {health?.latest_scrape_run_finished_at
                    ? ` Finished ${formatTimestamp(health.latest_scrape_run_finished_at)}.`
                    : " Run still in progress."}
                </p>
              </div>
              <div className="latest-run-metrics">
                <span>Seen {formatNumber(health?.latest_scrape_run_listings_seen)}</span>
                <span>Created {formatNumber(health?.latest_scrape_run_listings_created)}</span>
                <span>Updated {formatNumber(health?.latest_scrape_run_listings_updated)}</span>
              </div>
            </div>
            {health?.latest_scrape_run_error_summary ? (
              <div className="inline-error">{health.latest_scrape_run_error_summary}</div>
            ) : null}
          </div>

          <RetailerHealthTable retailerSummaries={retailerSummaries} onOpenRetailers={() => setScreen("retailers")} />

          <div className="panel table-panel">
            <div className="panel-head">
              <span>Recent runs</span>
              <span className="mono">{scrapeRuns.length}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Retailer</th>
                    <th>Status</th>
                    <th>Started</th>
                    <th>Seen</th>
                    <th>Created</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {scrapeRuns.map((run: ScrapeRun) => (
                    <tr key={run.id}>
                      <td>
                        <div className="table-product-name">{run.retailer?.name ?? run.scraper_name ?? "Unknown"}</div>
                        <div className="table-subcopy mono">{run.scraper_name ?? "retailer scraper"}</div>
                      </td>
                      <td>
                        <span className={statusTone(run.status)}>{formatStatusLabel(run.status)}</span>
                      </td>
                      <td className="mono">{formatShortDate(run.started_at)}</td>
                      <td className="mono">{formatNumber(run.listings_seen)}</td>
                      <td className="mono">{formatNumber(run.listings_created)}</td>
                      <td className="mono">{formatNumber(run.listings_updated)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-mark">PC</div>
          <div className="logo-text">
            PCDeal<span>Tracker</span>
          </div>
        </div>

        <div className="sidebar-scroll">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title}>
              <div className="sidebar-section">{section.title}</div>
              {section.items.map((item) => (
                <NavButton
                  key={item}
                  label={navItems[item].label}
                  count={navItems[item].count}
                  active={screen === item}
                  implemented={navItems[item].implemented}
                  icon={item}
                  onClick={() => setScreen(item)}
                />
              ))}
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-foot-card">
            <div className="panel-head">
              <span>Runtime</span>
              <span className={statusTone(health?.status)}>{formatStatusLabel(health?.status)}</span>
            </div>
            <div className="foot-stats">
              <div>
                <span>API</span>
                <strong className="mono">{getApiBase()}</strong>
              </div>
              <div>
                <span>Offers</span>
                <strong className="mono">{formatNumber(health?.active_offer_count)}</strong>
              </div>
              <div>
                <span>Queue</span>
                <strong className="mono">{formatNumber(reviewQueueTotal)}</strong>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="topbar-title">{screenMeta.title}</div>
            <div className="topbar-sub">{screenMeta.subtitle}</div>
          </div>
          <div className="topbar-actions">{renderTopbarControls()}</div>
        </header>

        <div className="content">{renderContent()}</div>
      </main>
    </div>
  );
}
