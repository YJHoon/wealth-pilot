"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";
import {
  type TradingAccount,
  type TradingStrategy,
  type TradingOrder,
  type TradingPosition,
  type TradingPerformance,
  type ScheduleStatus,
  type KisBalance,
  type TradingAccountApi,
  type TradingStrategyApi,
  type TradingOrderApi,
  type TradingPositionApi,
  type TradingPerformanceApi,
  type ScheduleStatusApi,
  type KisBalanceApi,
  type TradingAccountCreateRequest,
  type TradingAccountUpdateRequest,
  type TradingStrategyCreateRequest,
  type TradingStrategyUpdateRequest,
  type AccountRebalanceRequest,
  type AccountDepositRequest,
  type OrderSide,
  type OrderStatus,
  type AutoTickerPreviewResponse,
  type AutoTickerPreviewResponseApi,
  type AutoTickerSelectionHistory,
  type AutoTickerSelectionHistoryApi,
  type AccountCapitalSummary,
  type AccountCapitalSummaryApi,
  toAccountCapitalSummary,
  toTradingAccount,
  toTradingStrategy,
  toTradingOrder,
  toTradingPosition,
  toTradingPerformance,
  toScheduleStatus,
  toKisBalance,
  toAutoTickerHistory,
  toAutoTickerPreview,
} from "@/types/trading";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

export interface OrderFilters {
  side?: OrderSide;
  status?: OrderStatus;
  limit?: number;
  offset?: number;
}

export interface BalanceRefreshResult {
  total: number;
  succeeded: number;
  failed: number;
  errors: string[];
}

interface LoadingState {
  accounts: boolean;
  strategies: boolean;
  orders: boolean;
  positions: boolean;
  performance: boolean;
}

export interface UseTradingReturn {
  accounts: TradingAccount[];
  strategies: TradingStrategy[];
  orders: TradingOrder[];
  positions: TradingPosition[];
  allPositions: TradingPosition[];
  performance: TradingPerformance | null;
  accountBalances: Record<string, KisBalance>;
  selectedAccountId: string | null;
  setSelectedAccountId: (id: string | null) => void;
  loading: LoadingState;
  error: string | null;
  // Account mutations
  createAccount: (data: TradingAccountCreateRequest) => Promise<TradingAccount>;
  updateAccount: (id: string, data: TradingAccountUpdateRequest) => Promise<TradingAccount>;
  rebalanceAccount: (
    id: string,
    data: AccountRebalanceRequest,
  ) => Promise<TradingStrategy[]>;
  depositToAccount: (
    id: string,
    data: AccountDepositRequest,
  ) => Promise<TradingAccount>;
  deactivateAccount: (id: string) => Promise<void>;
  // Strategy mutations
  createStrategy: (data: TradingStrategyCreateRequest) => Promise<TradingStrategy>;
  updateStrategy: (id: string, data: TradingStrategyUpdateRequest) => Promise<TradingStrategy>;
  // Auto ticker selection
  previewAutoTickers: (strategyId: string) => Promise<AutoTickerPreviewResponse>;
  refreshAutoTickers: (strategyId: string) => Promise<TradingStrategy>;
  fetchAutoTickerHistory: (
    strategyId: string,
    limit?: number,
  ) => Promise<AutoTickerSelectionHistory[]>;
  fetchAccountCapitalSummary: (
    accountId: string,
    excludeStrategyId?: string,
  ) => Promise<AccountCapitalSummary>;
  // Schedule mutations
  startSchedule: (strategyId: string) => Promise<void>;
  stopSchedule: (strategyId: string) => Promise<void>;
  runNow: (strategyId: string) => Promise<void>;
  getScheduleStatus: (strategyId: string) => Promise<ScheduleStatus>;
  // KIS balance
  refreshAccountBalances: () => Promise<BalanceRefreshResult>;
  // Refetch
  refetchOrders: (filters?: OrderFilters) => Promise<void>;
  refetchPositions: () => Promise<void>;
  refetchAllPositions: () => Promise<void>;
  refetchPerformance: () => Promise<void>;
  refetchStrategies: () => Promise<void>;
}

export function useTrading(): UseTradingReturn {
  const { data: session } = useSession();
  const [accounts, setAccounts] = useState<TradingAccount[]>([]);
  const accountsRef = useRef(accounts);
  accountsRef.current = accounts;
  const [strategies, setStrategies] = useState<TradingStrategy[]>([]);
  const [orders, setOrders] = useState<TradingOrder[]>([]);
  const [positions, setPositions] = useState<TradingPosition[]>([]);
  const [allPositions, setAllPositions] = useState<TradingPosition[]>([]);
  const [performance, setPerformance] = useState<TradingPerformance | null>(null);
  const [accountBalances, setAccountBalances] = useState<Record<string, KisBalance>>({});
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<LoadingState>({
    accounts: true,
    strategies: false,
    orders: false,
    positions: false,
    performance: false,
  });

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;
  const fetchOpts = useMemo(
    () => (accessToken ? { accessToken } : {}),
    [accessToken],
  );

  // ── Accounts ──

  const fetchAccounts = useCallback(async () => {
    if (!canFetch) {
      setAccounts([]);
      setLoading((prev) => ({ ...prev, accounts: false }));
      return;
    }
    setLoading((prev) => ({ ...prev, accounts: true }));
    try {
      const res = await apiFetch<TradingAccountApi[]>("/api/trading/accounts", fetchOpts);
      const mapped = res.map(toTradingAccount);
      // 실전(live) → 모의(paper) 순으로 정렬해, 사용자가 실전 계좌를 먼저 보게 한다.
      mapped.sort((a, b) => {
        if (a.mode === b.mode) return 0;
        return a.mode === "live" ? -1 : 1;
      });
      setAccounts(mapped);
      if (mapped.length > 0 && !selectedAccountId) {
        const liveActive = mapped.find((a) => a.mode === "live" && a.isActive);
        const live = liveActive ?? mapped.find((a) => a.mode === "live");
        setSelectedAccountId((live ?? mapped[0]).id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "계좌 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading((prev) => ({ ...prev, accounts: false }));
    }
  }, [canFetch, fetchOpts, selectedAccountId]);

  const createAccount = useCallback(
    async (data: TradingAccountCreateRequest): Promise<TradingAccount> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingAccountApi>("/api/trading/accounts", {
        method: "POST",
        body: JSON.stringify(data),
        ...fetchOpts,
      });
      await fetchAccounts();
      return toTradingAccount(res);
    },
    [canFetch, fetchOpts, fetchAccounts],
  );

  const updateAccount = useCallback(
    async (id: string, data: TradingAccountUpdateRequest): Promise<TradingAccount> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingAccountApi>(`/api/trading/accounts/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
        ...fetchOpts,
      });
      await fetchAccounts();
      return toTradingAccount(res);
    },
    [canFetch, fetchOpts, fetchAccounts],
  );

  const deactivateAccount = useCallback(
    async (id: string): Promise<void> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      await apiFetch<void>(`/api/trading/accounts/${id}`, {
        method: "DELETE",
        ...fetchOpts,
      });
      await fetchAccounts();
    },
    [canFetch, fetchOpts, fetchAccounts],
  );

  // ── KIS Balance (실시간 잔고) ──

  const fetchAccountBalances = useCallback(
    async (accountList?: TradingAccount[]): Promise<BalanceRefreshResult> => {
      const target = accountList ?? accountsRef.current;
      const activeTargets = target.filter((a) => a.isActive);
      const result: BalanceRefreshResult = {
        total: activeTargets.length,
        succeeded: 0,
        failed: 0,
        errors: [],
      };
      if (activeTargets.length === 0) return result;
      if (!canFetch) {
        result.failed = result.total;
        result.errors = activeTargets.map((a) => a.id);
        return result;
      }
      const results: Record<string, KisBalance> = {};
      await Promise.all(
        activeTargets.map(async (account) => {
          try {
            const res = await apiFetch<KisBalanceApi>(
              `/api/trading/accounts/${account.id}/balance`,
              fetchOpts,
            );
            results[account.id] = toKisBalance(res);
            result.succeeded += 1;
          } catch (e) {
            console.error(`[useTrading] KIS balance fetch failed for account ${account.id}:`, e);
            result.failed += 1;
            result.errors.push(account.id);
          }
        }),
      );
      setAccountBalances((prev) => {
        const next: Record<string, KisBalance> = { ...prev, ...results };
        for (const failedId of result.errors) {
          delete next[failedId];
        }
        return next;
      });
      return result;
    },
    [canFetch, fetchOpts],
  );

  // ── Strategies ──

  const fetchStrategies = useCallback(async () => {
    if (!canFetch) {
      setStrategies([]);
      return;
    }
    setLoading((prev) => ({ ...prev, strategies: true }));
    try {
      const res = await apiFetch<TradingStrategyApi[]>("/api/trading/strategies", fetchOpts);
      setStrategies(res.map(toTradingStrategy));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "전략 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading((prev) => ({ ...prev, strategies: false }));
    }
  }, [canFetch, fetchOpts]);

  const createStrategy = useCallback(
    async (data: TradingStrategyCreateRequest): Promise<TradingStrategy> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingStrategyApi>("/api/trading/strategies", {
        method: "POST",
        body: JSON.stringify(data),
        ...fetchOpts,
      });
      await fetchStrategies();
      return toTradingStrategy(res);
    },
    [canFetch, fetchOpts, fetchStrategies],
  );

  const updateStrategy = useCallback(
    async (id: string, data: TradingStrategyUpdateRequest): Promise<TradingStrategy> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingStrategyApi>(`/api/trading/strategies/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
        ...fetchOpts,
      });
      await fetchStrategies();
      return toTradingStrategy(res);
    },
    [canFetch, fetchOpts, fetchStrategies],
  );

  // ── Auto ticker selection ──

  const previewAutoTickers = useCallback(
    async (strategyId: string): Promise<AutoTickerPreviewResponse> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<AutoTickerPreviewResponseApi>(
        `/api/trading/strategies/${strategyId}/auto-tickers/preview`,
        fetchOpts,
      );
      return toAutoTickerPreview(res);
    },
    [canFetch, fetchOpts],
  );

  const refreshAutoTickers = useCallback(
    async (strategyId: string): Promise<TradingStrategy> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingStrategyApi>(
        `/api/trading/strategies/${strategyId}/auto-tickers/refresh`,
        { method: "POST", ...fetchOpts },
      );
      await fetchStrategies();
      return toTradingStrategy(res);
    },
    [canFetch, fetchOpts, fetchStrategies],
  );

  const fetchAutoTickerHistory = useCallback(
    async (
      strategyId: string,
      limit: number = 20,
    ): Promise<AutoTickerSelectionHistory[]> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<AutoTickerSelectionHistoryApi[]>(
        `/api/trading/strategies/${strategyId}/auto-tickers/history?limit=${limit}`,
        fetchOpts,
      );
      return res.map(toAutoTickerHistory);
    },
    [canFetch, fetchOpts],
  );

  const fetchAccountCapitalSummary = useCallback(
    async (
      accountId: string,
      excludeStrategyId?: string,
    ): Promise<AccountCapitalSummary> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const qs = excludeStrategyId
        ? `?exclude_strategy_id=${encodeURIComponent(excludeStrategyId)}`
        : "";
      const res = await apiFetch<AccountCapitalSummaryApi>(
        `/api/trading/accounts/${accountId}/capital-summary${qs}`,
        fetchOpts,
      );
      return toAccountCapitalSummary(res);
    },
    [canFetch, fetchOpts],
  );

  const rebalanceAccount = useCallback(
    async (
      id: string,
      data: AccountRebalanceRequest,
    ): Promise<TradingStrategy[]> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingStrategyApi[]>(
        `/api/trading/accounts/${id}/rebalance`,
        {
          method: "POST",
          body: JSON.stringify(data),
          ...fetchOpts,
        },
      );
      const mapped = res.map(toTradingStrategy);
      await fetchStrategies();
      return mapped;
    },
    [canFetch, fetchOpts, fetchStrategies],
  );

  const depositToAccount = useCallback(
    async (
      id: string,
      data: AccountDepositRequest,
    ): Promise<TradingAccount> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<TradingAccountApi>(
        `/api/trading/accounts/${id}/deposit`,
        {
          method: "POST",
          body: JSON.stringify(data),
          ...fetchOpts,
        },
      );
      await fetchAccounts();
      await fetchStrategies();
      return toTradingAccount(res);
    },
    [canFetch, fetchOpts, fetchAccounts, fetchStrategies],
  );

  // ── Schedule ──

  const startSchedule = useCallback(
    async (strategyId: string): Promise<void> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      await apiFetch("/api/trading/schedule/start", {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId }),
        ...fetchOpts,
      });
      await fetchStrategies();
    },
    [canFetch, fetchOpts, fetchStrategies],
  );

  const stopSchedule = useCallback(
    async (strategyId: string): Promise<void> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      await apiFetch("/api/trading/schedule/stop", {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId }),
        ...fetchOpts,
      });
      await fetchStrategies();
    },
    [canFetch, fetchOpts, fetchStrategies],
  );

  const runNow = useCallback(
    async (strategyId: string): Promise<void> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      await apiFetch("/api/trading/schedule/run-now", {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId }),
        ...fetchOpts,
      });
    },
    [canFetch, fetchOpts],
  );

  const getScheduleStatus = useCallback(
    async (strategyId: string): Promise<ScheduleStatus> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<ScheduleStatusApi>(
        `/api/trading/schedule/status?strategy_id=${strategyId}`,
        fetchOpts,
      );
      return toScheduleStatus(res);
    },
    [canFetch, fetchOpts],
  );

  // ── Orders ──

  const fetchOrders = useCallback(
    async (filters: OrderFilters = {}) => {
      if (!canFetch || !selectedAccountId) {
        setOrders([]);
        return;
      }
      setLoading((prev) => ({ ...prev, orders: true }));
      try {
        const params = new URLSearchParams();
        params.set("account_id", selectedAccountId);
        if (filters.side) params.set("side", filters.side);
        if (filters.status) params.set("status", filters.status);
        params.set("limit", String(filters.limit ?? 50));
        params.set("offset", String(filters.offset ?? 0));
        const res = await apiFetch<TradingOrderApi[]>(
          `/api/trading/orders?${params.toString()}`,
          fetchOpts,
        );
        setOrders(res.map(toTradingOrder));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "주문내역을 불러오는데 실패했습니다.");
      } finally {
        setLoading((prev) => ({ ...prev, orders: false }));
      }
    },
    [canFetch, fetchOpts, selectedAccountId],
  );

  // ── Positions ──

  const fetchPositions = useCallback(async () => {
    if (!canFetch || !selectedAccountId) {
      setPositions([]);
      return;
    }
    setLoading((prev) => ({ ...prev, positions: true }));
    try {
      const res = await apiFetch<TradingPositionApi[]>(
        `/api/trading/positions?account_id=${selectedAccountId}`,
        fetchOpts,
      );
      setPositions(res.map(toTradingPosition));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "포지션을 불러오는데 실패했습니다.");
    } finally {
      setLoading((prev) => ({ ...prev, positions: false }));
    }
  }, [canFetch, fetchOpts, selectedAccountId]);

  const fetchAllPositions = useCallback(async () => {
    if (!canFetch) {
      setAllPositions([]);
      return;
    }
    setLoading((prev) => ({ ...prev, positions: true }));
    try {
      const res = await apiFetch<TradingPositionApi[]>(
        "/api/trading/positions",
        fetchOpts,
      );
      setAllPositions(res.map(toTradingPosition));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "포지션을 불러오는데 실패했습니다.");
    } finally {
      setLoading((prev) => ({ ...prev, positions: false }));
    }
  }, [canFetch, fetchOpts]);

  // ── Performance ──

  const fetchPerformance = useCallback(async () => {
    if (!canFetch || !selectedAccountId) {
      setPerformance(null);
      return;
    }
    setLoading((prev) => ({ ...prev, performance: true }));
    try {
      const res = await apiFetch<TradingPerformanceApi>(
        `/api/trading/performance?account_id=${selectedAccountId}`,
        fetchOpts,
      );
      setPerformance(toTradingPerformance(res));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "성과 데이터를 불러오는데 실패했습니다.");
    } finally {
      setLoading((prev) => ({ ...prev, performance: false }));
    }
  }, [canFetch, fetchOpts, selectedAccountId]);

  // ── Effects ──

  useEffect(() => {
    fetchAccounts().catch(() => {});
    fetchAllPositions().catch(() => {});
  }, [fetchAccounts, fetchAllPositions]);

  // 계좌 로드 후 KIS 잔고 자동 조회
  useEffect(() => {
    if (accounts.length > 0) {
      fetchAccountBalances(accounts).catch(() => {});
    }
  }, [accounts, fetchAccountBalances]);

  useEffect(() => {
    if (selectedAccountId) {
      fetchStrategies().catch(() => {});
      fetchOrders().catch(() => {});
      fetchPositions().catch(() => {});
      fetchPerformance().catch(() => {});
    }
  }, [selectedAccountId, fetchStrategies, fetchOrders, fetchPositions, fetchPerformance]);

  return {
    accounts,
    strategies,
    orders,
    positions,
    allPositions,
    performance,
    accountBalances,
    selectedAccountId,
    setSelectedAccountId,
    loading,
    error,
    createAccount,
    updateAccount,
    rebalanceAccount,
    depositToAccount,
    deactivateAccount,
    createStrategy,
    updateStrategy,
    previewAutoTickers,
    refreshAutoTickers,
    fetchAutoTickerHistory,
    fetchAccountCapitalSummary,
    startSchedule,
    stopSchedule,
    runNow,
    getScheduleStatus,
    refreshAccountBalances: fetchAccountBalances,
    refetchOrders: fetchOrders,
    refetchPositions: fetchPositions,
    refetchAllPositions: fetchAllPositions,
    refetchPerformance: fetchPerformance,
    refetchStrategies: fetchStrategies,
  };
}
