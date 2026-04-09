import type {
  FilterPayload,
  HistoryPayload,
  MatchCandidate,
  MatchDecision,
  MatchDecisionResolutionPayload,
  ProductDetail,
  ProductPage,
  ScrapeRun,
  Trend
} from "./types";

const DEFAULT_BASE = "http://localhost:8000";
const API_BASE = `${(import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE).replace(/\/$/, "")}/api/v2`;
const REVIEW_API_KEY = `${import.meta.env.VITE_REVIEW_API_KEY || ""}`.trim();

async function fetchJson<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function sendJson<T>(method: "PATCH", path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };
  if (REVIEW_API_KEY) {
    headers["X-API-Key"] = REVIEW_API_KEY;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Ignore non-JSON error bodies.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function getApiBase() {
  return API_BASE;
}

export function fetchProducts(params: Record<string, string | number | boolean | undefined>) {
  return fetchJson<ProductPage>("/products", params);
}

export function fetchProduct(productId: string) {
  return fetchJson<ProductDetail>(`/products/${productId}`);
}

export function fetchFilters(categoryId?: number) {
  return fetchJson<FilterPayload>("/filters", { category_id: categoryId });
}

export function fetchHistory(productId: string) {
  return fetchJson<HistoryPayload>("/history", { product_id: productId });
}

export function fetchTrends() {
  return fetchJson<Trend[]>("/trends", { days: 30, limit: 12 });
}

export function fetchScrapeRuns(params?: Record<string, string | number | boolean | undefined>) {
  return fetchJson<ScrapeRun[]>("/scrape-runs", params);
}

export function fetchMatchDecisions(params?: Record<string, string | number | boolean | undefined>) {
  return fetchJson<MatchDecision[]>("/match-decisions", params);
}

export function fetchMatchCandidates(decisionId: number, params?: Record<string, string | number | boolean | undefined>) {
  return fetchJson<MatchCandidate[]>(`/match-decisions/${decisionId}/candidates`, params);
}

export function resolveMatchDecision(decisionId: number, payload: MatchDecisionResolutionPayload) {
  return sendJson<MatchDecision>("PATCH", `/match-decisions/${decisionId}`, payload);
}
