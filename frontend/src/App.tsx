import { useDeferredValue, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  fetchFilters,
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
  ProductSummary,
  ScrapeRun,
  Trend
} from "./types";

type View = "products" | "trends" | "operations";

const COLORS = ["#d94f04", "#006d77", "#7b2cbf", "#2a9d8f", "#bc4749", "#1d3557"];

function formatCurrency(value?: number | null) {
  if (value === undefined || value === null) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0
  }).format(value);
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleString();
}

function buildChartRows(history?: HistoryPayload) {
  if (!history) {
    return [];
  }

  const rows = new Map<string, Record<string, string | number>>();
  for (const series of history.series) {
    for (const point of series.points) {
      const key = point.date;
      const row = rows.get(key) ?? { date: new Date(point.date).toLocaleDateString() };
      row[series.retailer.name] = point.price;
      rows.set(key, row);
    }
  }

  return Array.from(rows.values());
}

function ProductCard({
  product,
  isActive,
  onSelect
}: {
  product: ProductSummary;
  isActive: boolean;
  onSelect: (productId: string) => void;
}) {
  return (
    <button
      className={`product-card ${isActive ? "product-card-active" : ""}`}
      onClick={() => onSelect(product.id)}
      type="button"
    >
      <div className="card-meta">
        <span>{product.category.name}</span>
        <span>{product.available_offer_count} live</span>
      </div>
      <h3>{product.canonical_name}</h3>
      <p className="fingerprint">{product.fingerprint || "No fingerprint"}</p>
      <div className="price-row">
        <strong>{formatCurrency(product.best_price)}</strong>
        <span>{product.best_price_retailer ?? "No active offer"}</span>
      </div>
      <div className="retailers">
        {product.retailers.map((retailer) => (
          <span key={retailer}>{retailer}</span>
        ))}
      </div>
    </button>
  );
}

function TrendsPanel({ trends, onSelect }: { trends: Trend[]; onSelect: (productId: string) => void }) {
  return (
    <div className="trend-list">
      {trends.map((trend) => (
        <button key={trend.product.id} className="trend-card" type="button" onClick={() => onSelect(trend.product.id)}>
          <div className="card-meta">
            <span>{trend.product.category.name}</span>
            <span>{trend.product.retailers.join(", ")}</span>
          </div>
          <h3>{trend.product.canonical_name}</h3>
          <div className="trend-metrics">
            <strong>{trend.price_drop_percentage.toFixed(1)}%</strong>
            <span>
              {formatCurrency(trend.initial_price)} {"->"} {formatCurrency(trend.latest_price)}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

function ReviewCard({
  decision,
  onResolve,
  isResolving
}: {
  decision: MatchDecision;
  onResolve: (decisionId: number, payload: MatchDecisionResolutionPayload) => void;
  isResolving: boolean;
}) {
  const [candidateSearch, setCandidateSearch] = useState(decision.retailer_listing.title);
  const [resolutionNote, setResolutionNote] = useState("");
  const deferredCandidateSearch = useDeferredValue(candidateSearch.trim());

  const candidatesQuery = useQuery({
    queryKey: ["review-candidates", decision.id, deferredCandidateSearch, decision.retailer_listing.category?.id],
    queryFn: () => fetchMatchCandidates(decision.id, { search: deferredCandidateSearch || undefined, limit: 6 })
  });

  return (
    <article className="review-card">
      <div className="card-meta">
        <span>{decision.retailer_listing.category?.name ?? "Uncategorised"}</span>
        <span>{decision.retailer_listing.retailer.name}</span>
      </div>
      <h3>{decision.retailer_listing.title}</h3>
      <p className="fingerprint">{decision.fingerprint ?? "No fingerprint captured"}</p>
      <a href={decision.retailer_listing.source_url} target="_blank" rel="noreferrer" className="review-link">
        Open retailer listing
      </a>

      <div className="review-controls">
        <label htmlFor={`candidate-search-${decision.id}`}>Candidate search</label>
        <input
          id={`candidate-search-${decision.id}`}
          value={candidateSearch}
          onChange={(event) => setCandidateSearch(event.target.value)}
          placeholder="Search canonical products..."
        />
      </div>

      <div className="review-controls">
        <label htmlFor={`resolution-note-${decision.id}`}>Resolution note</label>
        <input
          id={`resolution-note-${decision.id}`}
          value={resolutionNote}
          onChange={(event) => setResolutionNote(event.target.value)}
          placeholder="Optional reviewer rationale"
        />
      </div>

      <div className="candidate-list">
        {candidatesQuery.isLoading ? <p className="panel-message">Loading candidate products...</p> : null}
        {!candidatesQuery.isLoading && (candidatesQuery.data?.length ?? 0) === 0 ? (
          <p className="panel-message">No candidate products matched the current search.</p>
        ) : null}
        {candidatesQuery.data?.map((candidate: MatchCandidate) => (
          <button
            key={candidate.canonical_product.id}
            type="button"
            className="candidate-chip"
            disabled={isResolving}
            onClick={() =>
              onResolve(decision.id, {
                decision: "manual_matched",
                canonical_product_id: candidate.canonical_product.id,
                rationale: resolutionNote || `Matched to ${candidate.canonical_product.canonical_name}`
              })
            }
          >
            <div className="candidate-copy">
              <strong>{candidate.canonical_product.canonical_name}</strong>
              <span>{candidate.reasons.join(" | ")}</span>
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
          className="review-action-primary"
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
    </article>
  );
}

function OperationsPanel({
  reviewQueue,
  scrapeRuns,
  onResolve,
  pendingDecisionId,
  mutationError
}: {
  reviewQueue: MatchDecision[];
  scrapeRuns: ScrapeRun[];
  onResolve: (decisionId: number, payload: MatchDecisionResolutionPayload) => void;
  pendingDecisionId?: number;
  mutationError?: string;
}) {
  return (
    <section className="ops-grid">
      <div className="ops-column">
        <div className="ops-header">
          <div>
            <p className="eyebrow">Review Queue</p>
            <h3>Needs review</h3>
          </div>
          <strong>{reviewQueue.length}</strong>
        </div>
        {mutationError ? <p className="panel-message">{mutationError}</p> : null}
        <div className="review-list">
          {reviewQueue.length === 0 ? (
            <div className="empty-state">
              <h3>No review items</h3>
              <p>The current queue is empty.</p>
            </div>
          ) : (
            reviewQueue.map((decision) => (
              <ReviewCard
                key={decision.id}
                decision={decision}
                onResolve={onResolve}
                isResolving={pendingDecisionId === decision.id}
              />
            ))
          )}
        </div>
      </div>

      <div className="ops-column">
        <div className="ops-header">
          <div>
            <p className="eyebrow">Operations</p>
            <h3>Recent scrape runs</h3>
          </div>
          <strong>{scrapeRuns.length}</strong>
        </div>
        <div className="run-list">
          {scrapeRuns.map((run) => (
            <article key={run.id} className="run-card">
              <div className="card-meta">
                <span>{run.scraper_name ?? "Unknown scraper"}</span>
                <span>{run.status}</span>
              </div>
              <strong>{run.retailer?.name ?? "All retailers"}</strong>
              <div className="run-metrics">
                <span>Seen: {run.listings_seen}</span>
                <span>Created: {run.listings_created}</span>
                <span>Updated: {run.listings_updated}</span>
              </div>
              <p className="panel-message">Started {formatTimestamp(run.started_at)}</p>
              {run.error_summary ? <p className="panel-message">{run.error_summary}</p> : null}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>("products");
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | undefined>(undefined);
  const [searchInput, setSearchInput] = useState("");
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(searchInput.trim());

  const filtersQuery = useQuery({
    queryKey: ["v2-filters", selectedCategoryId],
    queryFn: () => fetchFilters(selectedCategoryId)
  });

  const productsQuery = useQuery({
    queryKey: ["v2-products", deferredSearch, selectedCategoryId],
    queryFn: () =>
      fetchProducts({
        search: deferredSearch || undefined,
        category_id: selectedCategoryId,
        hide_unavailable: true,
        page: 1,
        page_size: 60
      })
  });

  const trendsQuery = useQuery({
    queryKey: ["v2-trends"],
    queryFn: fetchTrends
  });

  const reviewQueueQuery = useQuery({
    queryKey: ["v2-match-decisions", "needs_review"],
    queryFn: () => fetchMatchDecisions({ decision: "needs_review", limit: 20 })
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
        queryClient.invalidateQueries({ queryKey: ["v2-products"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-product"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-history"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-filters"] }),
        queryClient.invalidateQueries({ queryKey: ["v2-trends"] })
      ]);
    }
  });

  const selectedDetail = detailQuery.data;
  const chartRows = useMemo(() => buildChartRows(historyQuery.data), [historyQuery.data]);
  const visibleProducts = productsQuery.data?.products ?? [];
  const visibleTrends = trendsQuery.data ?? [];
  const reviewQueue = reviewQueueQuery.data ?? [];
  const scrapeRuns = scrapeRunsQuery.data ?? [];
  const pendingDecisionId = resolveDecisionMutation.isPending ? resolveDecisionMutation.variables?.decisionId : undefined;

  function handleSelectProduct(productId: string) {
    setSelectedProductId(productId);
    setView("products");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">V2 Runtime</p>
          <h1>PCDealTracker</h1>
          <p className="lede">
            Persisted retailer listings, canonical products, price observations, and a manual review queue for ambiguous
            matches.
          </p>
        </div>

        <div className="sidebar-block">
          <label htmlFor="search">Search</label>
          <input
            id="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="RTX 5070, AM5, 4K OLED..."
          />
        </div>

        <div className="sidebar-block">
          <label>View</label>
          <div className="segmented">
            <button type="button" className={view === "products" ? "active" : ""} onClick={() => setView("products")}>
              Products
            </button>
            <button type="button" className={view === "trends" ? "active" : ""} onClick={() => setView("trends")}>
              Trends
            </button>
            <button type="button" className={view === "operations" ? "active" : ""} onClick={() => setView("operations")}>
              Operations
            </button>
          </div>
        </div>

        <div className="sidebar-block">
          <label>Categories</label>
          <div className="category-list">
            <button
              type="button"
              className={selectedCategoryId === undefined ? "category-active" : ""}
              onClick={() => setSelectedCategoryId(undefined)}
            >
              All categories
            </button>
            {filtersQuery.data?.categories.map((category) => (
              <button
                key={category.id}
                type="button"
                className={selectedCategoryId === category.id ? "category-active" : ""}
                onClick={() => setSelectedCategoryId(category.id)}
              >
                {category.name}
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-block sidebar-stats">
          <div>
            <span>API</span>
            <strong>{getApiBase()}</strong>
          </div>
          <div>
            <span>Visible products</span>
            <strong>{productsQuery.data?.total ?? 0}</strong>
          </div>
          <div>
            <span>Review queue</span>
            <strong>{reviewQueue.length}</strong>
          </div>
          <div>
            <span>Price floor</span>
            <strong>{formatCurrency(filtersQuery.data?.min_price)}</strong>
          </div>
        </div>
      </aside>

      <main className="content">
        <header className="content-header">
          <div>
            <p className="eyebrow">Australian Retailer Tracking</p>
            <h2>
              {view === "products"
                ? "Canonical product view"
                : view === "trends"
                  ? "Biggest recent drops"
                  : "Operations and review"}
            </h2>
          </div>
          <p className="header-copy">
            {view === "products"
              ? "Browse the persisted canonical catalog and compare active retailer offers."
              : view === "trends"
                ? "Trends are computed from retailer price history over the last 30 days."
                : "Resolve ambiguous matches and inspect recent scrape runs without leaving the v2 app."}
          </p>
        </header>

        {view === "products" ? (
          <section className="grid-shell">
            <div className="product-grid">
              {productsQuery.isLoading ? <p className="panel-message">Loading products...</p> : null}
              {!productsQuery.isLoading && visibleProducts.length === 0 ? (
                <p className="panel-message">No products matched the current filters.</p>
              ) : null}
              {visibleProducts.map((product) => (
                <ProductCard
                  key={product.id}
                  product={product}
                  isActive={selectedProductId === product.id}
                  onSelect={handleSelectProduct}
                />
              ))}
            </div>

            <aside className="detail-panel">
              {!selectedProductId ? (
                <div className="empty-state">
                  <p className="eyebrow">Detail Panel</p>
                  <h3>Select a grouped product</h3>
                  <p>Pick any card to inspect listings, compare retailers, and view combined price history.</p>
                </div>
              ) : null}

              {selectedProductId && detailQuery.isLoading ? <p className="panel-message">Loading detail...</p> : null}

              {selectedDetail ? (
                <>
                  <div className="detail-header">
                    <p className="eyebrow">{selectedDetail.category.name}</p>
                    <h3>{selectedDetail.canonical_name}</h3>
                    <div className="detail-price-row">
                      <strong>{formatCurrency(selectedDetail.best_price)}</strong>
                      <span>{selectedDetail.best_price_retailer ?? "No current best offer"}</span>
                    </div>
                  </div>

                  <div className="detail-metadata">
                    {Object.entries(selectedDetail.attributes).length === 0 ? (
                      <span>No parsed attributes yet</span>
                    ) : (
                      Object.entries(selectedDetail.attributes).map(([key, value]) => (
                        <span key={key}>
                          {key.replace(/_/g, " ")}: {String(value)}
                        </span>
                      ))
                    )}
                  </div>

                  <div className="chart-panel">
                    <div className="panel-heading">
                      <span>Price history</span>
                      <strong>{historyQuery.data?.series.length ?? 0} retailers</strong>
                    </div>
                    {chartRows.length === 0 ? (
                      <p className="panel-message">No history loaded for this product group.</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={260}>
                        <LineChart data={chartRows}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                          <XAxis dataKey="date" tick={{ fill: "#d7d5c8", fontSize: 12 }} />
                          <YAxis tick={{ fill: "#d7d5c8", fontSize: 12 }} />
                          <Tooltip />
                          <Legend />
                          {historyQuery.data?.series.map((series, index) => (
                            <Line
                              key={series.retailer.id}
                              type="monotone"
                              dataKey={series.retailer.name}
                              stroke={COLORS[index % COLORS.length]}
                              strokeWidth={2}
                              dot={false}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>

                  <div className="offers-panel">
                    <div className="panel-heading">
                      <span>Offers</span>
                      <strong>{selectedDetail.listings.length}</strong>
                    </div>
                    <div className="offer-list">
                      {selectedDetail.listings.map((listing) => (
                        <a key={listing.id} href={listing.url} target="_blank" rel="noreferrer" className="offer-row">
                          <div>
                            <strong>{listing.retailer.name}</strong>
                            <span>{listing.status.toLowerCase()}</span>
                          </div>
                          <div className="offer-price">
                            <strong>{formatCurrency(listing.current_price)}</strong>
                            {listing.previous_price ? <span>was {formatCurrency(listing.previous_price)}</span> : null}
                          </div>
                        </a>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </aside>
          </section>
        ) : null}

        {view === "trends" ? (
          <section className="trend-shell">
            {trendsQuery.isLoading ? <p className="panel-message">Loading trends...</p> : null}
            {!trendsQuery.isLoading ? <TrendsPanel trends={visibleTrends} onSelect={handleSelectProduct} /> : null}
          </section>
        ) : null}

        {view === "operations" ? (
          <OperationsPanel
            reviewQueue={reviewQueue}
            scrapeRuns={scrapeRuns}
            onResolve={(decisionId, payload) => resolveDecisionMutation.mutate({ decisionId, payload })}
            pendingDecisionId={pendingDecisionId}
            mutationError={resolveDecisionMutation.error instanceof Error ? resolveDecisionMutation.error.message : undefined}
          />
        ) : null}
      </main>
    </div>
  );
}
