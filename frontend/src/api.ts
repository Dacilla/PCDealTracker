import type { FilterPayload, HistoryPayload, ProductDetail, ProductPage, Trend } from "./types";

const DEFAULT_BASE = "http://localhost:8000";
const API_BASE = `${(import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE).replace(/\/$/, "")}/api/v2`;

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
