"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";
import {
  type TradingAccount,
  type TradingStrategy,
  type TradingOrder,
  type TradingPosition,
  type TradingPerformance,
  type ScheduleStatus,
  type TradingAccountApi,
  type TradingStrategyApi,
  type TradingOrderApi,
  type TradingPositionApi,
  type TradingPerformanceApi,
  type ScheduleStatusApi,
  type TradingAccountCreateRequest,
  type TradingStrategyCreateRequest,
  type TradingStrategyUpdateRequest,
  type OrderSide,
  type OrderStatus,
  toTradingAccount,
  toTradingStrategy,
  toTradingOrder,
  toTradingPosition,
  toTradingPerformance,
  toScheduleStatus,
} from "@/types/trading";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

export interface OrderFilters {
  side?: OrderSide;
  status?: OrderStatus;
  limit?: number;
  offset?: number;
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
  selectedAccountId: string | null;
  setSelectedAccountId: (id: string | null) => void;
  loading: LoadingState;
  error: string | null;
  // Account mutations
  createAccount: (data: TradingAccountCreateRequest) => Promise<TradingAccount>;
  deactivateAccount: (id: string) => Promise<void>;
  // Strategy mutations
  createStrategy: (data: TradingStrategyCreateRequest) => Promise<TradingStrategy>;
  updateStrategy: (id: string, data: TradingStrategyUpdateRequest) => Promise<TradingStrategy>;
  // Schedule mutations
  startSchedule: (strategyId: string) => Promise<void>;
  stopSchedule: (strategyId: string) => Promise<void>;
  runNow: (strategyId: string) => Promise<void>;
  getScheduleStatus: (strategyId: string) => Promise<ScheduleStatus>;
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
  const [strategies, setStrategies] = useState<TradingStrategy[]>([]);
  const [orders, setOrders] = useState<TradingOrder[]>([]);
  const [positions, setPositions] = useState<TradingPosition[]>([]);
  const [allPositions, setAllPositions] = useState<TradingPosition[]>([]);
  const [performance, setPerformance] = useState<TradingPerformance | null>(null);
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
      setAccounts(mapped);
      if (mapped.length > 0 && !selectedAccountId) {
        setSelectedAccountId(mapped[0].id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "계좌 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading((prev) => ({ ...prev, accounts: false }));
    }
  }, [canFetch, accessToken, selectedAccountId]);

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
    [canFetch, accessToken, fetchAccounts],
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
    [canFetch, accessToken, fetchAccounts],
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
  }, [canFetch, accessToken]);

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
    [canFetch, accessToken, fetchStrategies],
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
    [canFetch, accessToken, fetchStrategies],
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
    [canFetch, accessToken, fetchStrategies],
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
    [canFetch, accessToken, fetchStrategies],
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
    [canFetch, accessToken],
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
    [canFetch, accessToken],
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
    [canFetch, accessToken, selectedAccountId],
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
  }, [canFetch, accessToken, selectedAccountId]);

  const fetchAllPositions = useCallback(async () => {
    if (!canFetch) {
      setAllPositions([]);
      return;
    }
    try {
      const res = await apiFetch<TradingPositionApi[]>(
        "/api/trading/positions",
        fetchOpts,
      );
      setAllPositions(res.map(toTradingPosition));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "포지션을 불러오는데 실패했습니다.");
    }
  }, [canFetch, accessToken]);

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
  }, [canFetch, accessToken, selectedAccountId]);

  // ── Effects ──

  useEffect(() => {
    fetchAccounts().catch(() => {});
    fetchAllPositions().catch(() => {});
  }, [fetchAccounts, fetchAllPositions]);

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
    selectedAccountId,
    setSelectedAccountId,
    loading,
    error,
    createAccount,
    deactivateAccount,
    createStrategy,
    updateStrategy,
    startSchedule,
    stopSchedule,
    runNow,
    getScheduleStatus,
    refetchOrders: fetchOrders,
    refetchPositions: fetchPositions,
    refetchAllPositions: fetchAllPositions,
    refetchPerformance: fetchPerformance,
    refetchStrategies: fetchStrategies,
  };
}
