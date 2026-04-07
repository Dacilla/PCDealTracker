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
