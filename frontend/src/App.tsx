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
  HistoryPayload,
  MatchCandidate,
  MatchDecision,
  MatchDecisionResolutionPayload,
  ProductDetail,
  ProductSummary,
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

const REVIEW_PAGE_SIZE = 20;
const WATCHLIST_STORAGE_KEY = "pcdt-watchlist";
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
    subtitle: "The design includes alert management, but the live app does not have persisted alerts yet.",
    implemented: false
  },
  compare: {
    title: "Compare",
    subtitle: "Comparison workflows are planned in the design, but the live app does not expose a dedicated compare flow yet.",
    implemented: false
  },
  products: {
    title: "Products",
    subtitle: "Canonical product administration is not exposed as a separate live workflow yet.",
    implemented: false
  },
  review: {
    title: "Review Queue",
    subtitle: "Work through ambiguous retailer listings, inspect candidates, and resolve matches without leaving the queue.",
    implemented: true
  },
  dq: {
    title: "Data Quality",
    subtitle: "The data quality screen from the design is not yet backed by dedicated API surfaces.",
    implemented: false
  },
  retailers: {
    title: "Retailers",
    subtitle: "Retailer-by-retailer operational views are planned, but not yet wired into the frontend.",
    implemented: false
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
  if (normalized === "partial" || normalized === "degraded" || normalized === "timeout") {
    return "tag tag-amber";
  }
  if (normalized === "succeeded" || normalized === "ok") {
    return "tag tag-green";
  }
  return "tag tag-muted";
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

function readWatchlist() {
  if (typeof window === "undefined") {
    return [] as string[];
  }

  try {
    const raw = window.localStorage.getItem(WATCHLIST_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
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
  onSelect,
  onToggleWatchlist
}: {
  product: ProductSummary;
  active: boolean;
  watched: boolean;
  onSelect: (productId: string) => void;
  onToggleWatchlist: (productId: string) => void;
}) {
  return (
    <article className={`product-card ${active ? "active" : ""}`} onClick={() => onSelect(product.id)}>
      <div className="product-card-top">
        <span className="tag tag-muted">{product.category.name}</span>
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
  onSelect,
  onToggleWatchlist
}: {
  products: ProductSummary[];
  selectedProductId: string | null;
  watchlistIds: string[];
  onSelect: (productId: string) => void;
  onToggleWatchlist: (productId: string) => void;
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
  const [reviewQueueOffset, setReviewQueueOffset] = useState(0);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null);
  const [watchlistIds, setWatchlistIds] = useState<string[]>(() => readWatchlist());
  const deferredSearch = useDeferredValue(searchInput.trim());
  const deferredReviewSearch = useDeferredValue(reviewSearchInput.trim());

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlistIds));
    }
  }, [watchlistIds]);

  const filtersQuery = useQuery({
    queryKey: ["v2-filters", selectedCategoryId],
    queryFn: () => fetchFilters(selectedCategoryId)
  });

  const healthQuery = useQuery({
    queryKey: ["v2-health"],
    queryFn: fetchHealth
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

  const trendsQuery = useQuery({
    queryKey: ["v2-trends"],
    queryFn: fetchTrends
  });

  const reviewQueueQuery = useQuery({
    queryKey: ["v2-match-decisions", "needs_review", deferredReviewSearch, reviewCategoryId, reviewQueueOffset],
    queryFn: () =>
      fetchMatchDecisions({
        decision: "needs_review",
        search: deferredReviewSearch || undefined,
        category_id: reviewCategoryId,
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
        queryClient.invalidateQueries({ queryKey: ["v2-product"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-history"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-filters"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-trends"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-scrape-runs"] })
      ]);
    }
  });

  const visibleProducts = productsQuery.data?.products ?? [];
  const visibleTrends = trendsQuery.data ?? [];
  const reviewQueuePage = reviewQueueQuery.data;
  const reviewQueue = reviewQueuePage?.decisions ?? [];
  const scrapeRuns = scrapeRunsQuery.data ?? [];
  const health = healthQuery.data;
  const selectedDetail = detailQuery.data;
  const selectedDecision = reviewQueue.find((decision) => decision.id === selectedReviewId);
  const pendingDecisionId = resolveDecisionMutation.isPending ? resolveDecisionMutation.variables?.decisionId : undefined;
  const reviewQueueTotal = reviewQueuePage?.total ?? health?.review_queue_count ?? reviewQueue.length;

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
    return visibleProducts.filter((product) => watchlistIds.includes(product.id));
  }, [visibleProducts, watchlistIds]);

  const navItems = useMemo<Record<Screen, NavItem>>(
    () => ({
      catalog: { key: "catalog", label: "Catalog", implemented: true },
      deals: { key: "deals", label: "Deals", implemented: true },
      watchlist: { key: "watchlist", label: "Watchlist", count: filteredWatchlist.length, implemented: true },
      alerts: { key: "alerts", label: "Price Alerts", implemented: false },
      compare: { key: "compare", label: "Compare", implemented: false },
      products: { key: "products", label: "Products", implemented: false },
      review: { key: "review", label: "Review Queue", count: reviewQueueTotal, implemented: true },
      dq: { key: "dq", label: "Data Quality", implemented: false },
      retailers: { key: "retailers", label: "Retailers", implemented: false },
      scraper: { key: "scraper", label: "Scraper Health", implemented: true },
      analytics: { key: "analytics", label: "Analytics", implemented: false },
      settings: { key: "settings", label: "Settings", implemented: false }
    }),
    [filteredWatchlist.length, reviewQueueTotal]
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

  function renderTopbarControls() {
    if (screen === "catalog" || screen === "deals" || screen === "watchlist") {
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
                    onSelect={handleSelectProduct}
                    onToggleWatchlist={handleToggleWatchlist}
                  />
                ))}
              </div>
            ) : (
              <ProductTable
                products={visibleProducts}
                selectedProductId={selectedProductId}
                watchlistIds={watchlistIds}
                onSelect={handleSelectProduct}
                onToggleWatchlist={handleToggleWatchlist}
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
                onSelect={handleSelectProduct}
                onToggleWatchlist={handleToggleWatchlist}
              />
            )}
          </div>
          <ProductDetailPanel detail={selectedDetail} history={historyQuery.data} loading={detailQuery.isLoading || historyQuery.isLoading} />
        </section>
      );
    }

    if (screen === "review") {
      return (
        <section className="workspace review-workspace">
          <div className="review-queue-panel panel">
            <div className="panel-head">
              <span>Pending queue</span>
              <span className="mono">
                {reviewQueueOffset + 1}-{reviewQueueOffset + reviewQueue.length} / {formatNumber(reviewQueueTotal)}
              </span>
            </div>
            {resolveDecisionMutation.error ? (
              <div className="inline-error">{resolveDecisionMutation.error.message}</div>
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
