// 자산 유형
export type AssetType =
  | "cash"
  | "domestic_stock"
  | "foreign_stock"
  | "crypto"
  | "real_estate";

// 자산 상태
export type AssetStatus = "active" | "sold" | "delisted";

// 통화
export type Currency = "KRW" | "USD" | "EUR" | "JPY" | "BTC" | "ETH";

// 자산
export interface Asset {
  id: string;
  groupId: string | null;
  type: AssetType;
  status: AssetStatus;
  name: string;
  ticker: string | null;
  quantity: number;
  purchasePrice: number;
  currentPrice: number | null;
  currency: Currency;
  metadata: Record<string, unknown>;
  soldAt: string | null;
  soldPrice: number | null;
  realizedPnl: number | null;
  createdAt: string;
  updatedAt: string;
}

// 포트폴리오 그룹
export interface PortfolioGroup {
  id: string;
  userId?: string;
  name: string;
  description: string | null;
  sortOrder: number;
  createdAt: string;
  assetCount?: number;
}

// ── API 요청/응답 타입 (백엔드 스키마 매칭) ──

// 백엔드 snake_case → 프론트 camelCase 변환 전 원본 타입
export interface AssetApiResponse {
  id: string;
  group_id: string | null;
  type: AssetType;
  status: AssetStatus;
  name: string;
  ticker: string | null;
  currency: Currency;
  quantity: number;
  purchase_price: number;
  current_price: number | null;
  metadata_json: Record<string, unknown> | null;
  sold_at: string | null;
  sold_price: number | null;
  realized_pnl: number | null;
  created_at: string;
  updated_at: string;
}

export interface AssetListApiResponse {
  assets: AssetApiResponse[];
  total: number;
}

export interface GroupApiResponse {
  id: string;
  user_id?: string;
  name: string;
  description: string | null;
  sort_order: number;
  created_at: string;
  asset_count: number;
}

export interface GroupListApiResponse {
  groups: GroupApiResponse[];
  total: number;
}

export interface AssetCreateRequest {
  type: AssetType;
  name: string;
  ticker?: string | null;
  currency: Currency;
  quantity: number;
  purchase_price: number;
  current_price?: number | null;
  group_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface AssetUpdateRequest {
  type?: AssetType;
  name?: string;
  ticker?: string | null;
  currency?: Currency;
  quantity?: number;
  purchase_price?: number;
  current_price?: number | null;
  group_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface SellRequest {
  sold_price: number;
}

// API → 프론트 변환 헬퍼
export function toAsset(api: AssetApiResponse): Asset {
  return {
    id: api.id,
    groupId: api.group_id,
    type: api.type,
    status: api.status,
    name: api.name,
    ticker: api.ticker,
    quantity: api.quantity,
    purchasePrice: api.purchase_price,
    currentPrice: api.current_price,
    currency: api.currency,
    metadata: api.metadata_json ?? {},
    soldAt: api.sold_at,
    soldPrice: api.sold_price,
    realizedPnl: api.realized_pnl,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toGroup(api: GroupApiResponse): PortfolioGroup {
  return {
    id: api.id,
    userId: api.user_id,
    name: api.name,
    description: api.description,
    sortOrder: api.sort_order,
    createdAt: api.created_at,
    assetCount: api.asset_count,
  };
}

// 대시보드 요약
export interface DashboardSummary {
  totalValueKrw: number;
  byType: Record<AssetType, { valueKrw: number; ratio: number }>;
  byGroup: Record<string, { name: string; valueKrw: number; ratio: number }>;
  pnl: {
    total: number;
    realized: number;
    unrealized: number;
    totalRatio: number;
  };
  previousDayChange: {
    amount: number;
    ratio: number;
  };
  updatedAt: string;
}

// 데이터 신뢰도 등급
export type DataFreshness = "realtime" | "delayed" | "batch" | "estimated";

export interface PriceData {
  price: number;
  currency: Currency;
  freshness: DataFreshness;
  fetchedAt: string;
  isStale?: boolean;
}

// ── 시세 갱신 API 타입 ──

export interface RefreshDetailApi {
  ticker: string;
  success: boolean;
  price: number | null;
  currency: string | null;
  error: string | null;
}

export interface ExchangeRateApi {
  from_currency: string;
  to_currency: string;
  rate: number;
  fetched_at: string;
  source: string;
}

export interface RefreshResponseApi {
  success_count: number;
  fail_count: number;
  refreshed_at: string;
  details: RefreshDetailApi[];
  exchange_rates: ExchangeRateApi[];
}

export interface ExchangeRate {
  fromCurrency: string;
  toCurrency: string;
  rate: number;
  fetchedAt: string;
  source: string;
}

export interface PriceModeApi {
  current_mode: DataFreshness;
}

// ── 대시보드 API 타입 ──

export interface TypeBreakdownApi {
  value_krw: number;
  ratio: number;
}

export interface GroupBreakdownApi {
  name: string;
  value_krw: number;
  ratio: number;
}

export interface PnlSummaryApi {
  total: number;
  realized: number;
  unrealized: number;
  total_ratio: number;
}

export interface DailyChangeApi {
  amount: number;
  ratio: number;
}

export interface DashboardSummaryApi {
  total_value_krw: number;
  by_type: Record<string, TypeBreakdownApi>;
  by_group: Record<string, GroupBreakdownApi>;
  pnl: PnlSummaryApi;
  previous_day_change: DailyChangeApi;
  updated_at: string;
}

export interface HistoryDataPointApi {
  date: string;
  total_value_krw: number;
  breakdown: Record<string, unknown> | null;
}

export interface DashboardHistoryApi {
  period: string;
  data_points: HistoryDataPointApi[];
  total_count: number;
}

export interface SnapshotResponseApi {
  id: string;
  snapshot_date: string;
  total_value_krw: number;
  breakdown: Record<string, unknown> | null;
  created_at: string;
}

// API → 프론트 변환
const ASSET_TYPES = new Set<string>([
  "cash",
  "domestic_stock",
  "foreign_stock",
  "crypto",
  "real_estate",
]);

function isAssetType(key: string): key is AssetType {
  return ASSET_TYPES.has(key);
}

export function toDashboardSummary(api: DashboardSummaryApi): DashboardSummary {
  const byType = {} as Partial<DashboardSummary["byType"]>;
  for (const [key, val] of Object.entries(api.by_type)) {
    if (!isAssetType(key)) {
      console.warn(`Unknown asset type from API: ${key}`);
      continue;
    }
    byType[key] = { valueKrw: val.value_krw, ratio: val.ratio };
  }

  const byGroup: DashboardSummary["byGroup"] = {};
  for (const [key, val] of Object.entries(api.by_group)) {
    byGroup[key] = { name: val.name, valueKrw: val.value_krw, ratio: val.ratio };
  }

  return {
    totalValueKrw: api.total_value_krw,
    byType: byType as DashboardSummary["byType"],
    byGroup,
    pnl: {
      total: api.pnl.total,
      realized: api.pnl.realized,
      unrealized: api.pnl.unrealized,
      totalRatio: api.pnl.total_ratio,
    },
    previousDayChange: {
      amount: api.previous_day_change.amount,
      ratio: api.previous_day_change.ratio,
    },
    updatedAt: api.updated_at,
  };
}
