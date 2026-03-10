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
  userId: string;
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
  userId: string;
  name: string;
  description: string | null;
  sortOrder: number;
  createdAt: string;
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
