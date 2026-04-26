"use client";

import { useState, useEffect, useCallback } from "react";
import type {
  Asset,
  DashboardSummary,
  PortfolioGroup,
  DataFreshness,
} from "@/types";

// ── Mock 데이터 (백엔드 API 완성 전까지 사용) ──

const MOCK_GROUPS: PortfolioGroup[] = [
  {
    id: "g1",
    name: "장기투자",
    description: "장기 보유 종목",
    sortOrder: 0,
    createdAt: "2025-01-01T00:00:00Z",
  },
  {
    id: "g2",
    name: "단기트레이딩",
    description: "단기 매매",
    sortOrder: 1,
    createdAt: "2025-01-01T00:00:00Z",
  },
];

const MOCK_ASSETS: Asset[] = [
  {
    id: "a1",
    groupId: "g1",
    type: "domestic_stock",
    status: "active",
    name: "삼성전자",
    ticker: "005930",
    quantity: 100,
    purchasePrice: 65000,
    currentPrice: 72000,
    currency: "KRW",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-15T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a2",
    groupId: "g1",
    type: "domestic_stock",
    status: "active",
    name: "SK하이닉스",
    ticker: "000660",
    quantity: 50,
    purchasePrice: 130000,
    currentPrice: 155000,
    currency: "KRW",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-02-01T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a3",
    groupId: "g1",
    type: "domestic_stock",
    status: "active",
    name: "네이버",
    ticker: "035420",
    quantity: 30,
    purchasePrice: 210000,
    currentPrice: 195000,
    currency: "KRW",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-02-10T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a4",
    groupId: "g1",
    type: "foreign_stock",
    status: "active",
    name: "Apple Inc.",
    ticker: "AAPL",
    quantity: 20,
    purchasePrice: 175,
    currentPrice: 198.5,
    currency: "USD",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-20T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a5",
    groupId: "g1",
    type: "foreign_stock",
    status: "active",
    name: "Tesla Inc.",
    ticker: "TSLA",
    quantity: 10,
    purchasePrice: 245,
    currentPrice: 268.3,
    currency: "USD",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-02-05T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a6",
    groupId: "g2",
    type: "crypto",
    status: "active",
    name: "Bitcoin",
    ticker: "BTC",
    quantity: 0.5,
    purchasePrice: 62000,
    currentPrice: 84200,
    currency: "USD",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-10T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a7",
    groupId: "g2",
    type: "crypto",
    status: "active",
    name: "Ethereum",
    ticker: "ETH",
    quantity: 5,
    purchasePrice: 3200,
    currentPrice: 3450,
    currency: "USD",
    metadata: {},
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-12T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a8",
    groupId: null,
    type: "cash",
    status: "active",
    name: "국민은행 예금",
    ticker: null,
    quantity: 1,
    purchasePrice: 25000000,
    currentPrice: 25000000,
    currency: "KRW",
    metadata: { bank: "국민은행", rate: 3.5 },
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-01T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a9",
    groupId: null,
    type: "cash",
    status: "active",
    name: "토스뱅크 적금",
    ticker: null,
    quantity: 1,
    purchasePrice: 10000000,
    currentPrice: 10000000,
    currency: "KRW",
    metadata: { bank: "토스뱅크", rate: 4.0 },
    soldAt: null,
    soldPrice: null,
    realizedPnl: null,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-05T00:00:00Z",
    updatedAt: "2025-03-20T09:00:00Z",
  },
  {
    id: "a10",
    groupId: "g1",
    type: "domestic_stock",
    status: "sold",
    name: "카카오",
    ticker: "035720",
    quantity: 40,
    purchasePrice: 55000,
    currentPrice: null,
    currency: "KRW",
    metadata: {},
    soldAt: "2025-03-01T10:00:00Z",
    soldPrice: 48000,
    realizedPnl: -280000,
    source: "manual",
    tradingAccountId: null,
    externalTicker: null,
    lastSyncedAt: null,
    createdAt: "2025-01-20T00:00:00Z",
    updatedAt: "2025-03-01T10:00:00Z",
  },
];

// 통화별 KRW 환율 (mock)
const exchangeRatesKrw: Record<string, number> = {
  KRW: 1,
  USD: 1380,
  EUR: 1500,
  JPY: 9.2,
};

function toKrwRate(currency: string): number {
  return exchangeRatesKrw[currency] ?? 1;
}

// ── 계산 유틸 ──

function getKrwValue(asset: Asset): number {
  const price = asset.currentPrice ?? asset.purchasePrice;
  if (asset.type === "cash") {
    return asset.purchasePrice * asset.quantity;
  }
  const rate = toKrwRate(asset.currency);
  return price * asset.quantity * rate;
}

function getPurchaseKrw(asset: Asset): number {
  if (asset.type === "cash") {
    return asset.purchasePrice * asset.quantity;
  }
  const rate = toKrwRate(asset.currency);
  return asset.purchasePrice * asset.quantity * rate;
}

function buildSummary(assets: Asset[], updatedAt: string): DashboardSummary {
  const active = assets.filter((a) => a.status === "active");

  const totalValueKrw = active.reduce((sum, a) => sum + getKrwValue(a), 0);
  const totalPurchaseKrw = active.reduce((sum, a) => sum + getPurchaseKrw(a), 0);
  const unrealized = totalValueKrw - totalPurchaseKrw;
  const realized = assets
    .filter((a) => a.status === "sold" && a.realizedPnl !== null)
    .reduce((sum, a) => sum + (a.realizedPnl! * toKrwRate(a.currency)), 0);

  const byType: DashboardSummary["byType"] = {} as DashboardSummary["byType"];
  for (const a of active) {
    const krw = getKrwValue(a);
    const key = a.type;
    if (!byType[key]) byType[key] = { valueKrw: 0, ratio: 0 };
    byType[key].valueKrw += krw;
  }
  for (const key of Object.keys(byType) as Array<keyof typeof byType>) {
    byType[key].ratio = totalValueKrw > 0 ? (byType[key].valueKrw / totalValueKrw) * 100 : 0;
  }

  return {
    totalValueKrw,
    byType,
    pnl: {
      total: realized + unrealized,
      realized,
      unrealized,
      totalRatio: totalPurchaseKrw > 0 ? ((realized + unrealized) / totalPurchaseKrw) * 100 : 0,
    },
    previousDayChange: {
      amount: totalValueKrw * 0.0082, // mock: +0.82%
      ratio: 0.82,
    },
    updatedAt,
  };
}

export interface HistoryPoint {
  date: string;
  totalKrw: number;
  stock: number;
  crypto: number;
  cash: number;
}

function generateHistory(period: string): HistoryPoint[] {
  const days = period === "1M" ? 30 : period === "3M" ? 90 : period === "6M" ? 180 : 365;
  const now = Date.now();
  const base = 95_000_000;
  const points: HistoryPoint[] = [];
  for (let i = days; i >= 0; i--) {
    const d = new Date(now - i * 86400000);
    const progress = (days - i) / days;
    const noise = Math.sin(i * 0.3) * 2_000_000 + Math.cos(i * 0.7) * 1_500_000;
    const total = base + progress * 15_000_000 + noise;
    points.push({
      date: d.toISOString().slice(0, 10),
      totalKrw: Math.round(total),
      stock: Math.round(total * 0.55),
      crypto: Math.round(total * 0.25),
      cash: Math.round(total * 0.2),
    });
  }
  return points;
}

export interface ActivityItem {
  id: string;
  type: "buy" | "sell" | "priceUpdate";
  assetName: string;
  description: string;
  amount: number | null;
  timestamp: string;
}

const MOCK_ACTIVITY: ActivityItem[] = [
  { id: "act1", type: "sell", assetName: "카카오", description: "매도 완료 (40주)", amount: 1920000, timestamp: "2025-03-01T10:00:00Z" },
  { id: "act2", type: "buy", assetName: "SK하이닉스", description: "매수 (50주)", amount: 6500000, timestamp: "2025-02-01T09:30:00Z" },
  { id: "act3", type: "priceUpdate", assetName: "Bitcoin", description: "시세 갱신 ($84,200)", amount: null, timestamp: "2025-03-20T09:00:00Z" },
  { id: "act4", type: "buy", assetName: "네이버", description: "매수 (30주)", amount: 6300000, timestamp: "2025-02-10T10:15:00Z" },
  { id: "act5", type: "priceUpdate", assetName: "삼성전자", description: "시세 갱신 (72,000원)", amount: null, timestamp: "2025-03-20T09:00:00Z" },
];

// ── Hook ──

export interface DashboardData {
  summary: DashboardSummary;
  assets: Asset[];
  groups: PortfolioGroup[];
  history: HistoryPoint[];
  activity: ActivityItem[];
  freshness: DataFreshness;
  isLoading: boolean;
  isRefreshing: boolean;
  refresh: () => Promise<void>;
  historyPeriod: string;
  setHistoryPeriod: (p: string) => void;
}

export function useDashboardData(): DashboardData {
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [historyPeriod, setHistoryPeriod] = useState("3M");
  const [updatedAt, setUpdatedAt] = useState(() => new Date().toISOString());

  useEffect(() => {
    // 초기 로드 시뮬레이션
    const t = setTimeout(() => {
      setUpdatedAt(new Date().toISOString());
      setIsLoading(false);
    }, 500);
    return () => clearTimeout(t);
  }, []);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      // TODO: apiFetch("/api/prices/refresh", { method: "POST" })
      await new Promise((r) => setTimeout(r, 1000));
      setUpdatedAt(new Date().toISOString());
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  return {
    summary: buildSummary(MOCK_ASSETS, updatedAt),
    assets: MOCK_ASSETS,
    groups: MOCK_GROUPS,
    history: generateHistory(historyPeriod),
    activity: MOCK_ACTIVITY,
    freshness: "delayed" as DataFreshness,
    isLoading,
    isRefreshing,
    refresh,
    historyPeriod,
    setHistoryPeriod,
  };
}

export { exchangeRatesKrw, toKrwRate, getKrwValue, getPurchaseKrw };
