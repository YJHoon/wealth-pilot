"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch } from "@/lib/api";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";
import type {
  DataFreshness,
  ExchangeRateApi,
  PriceModeApi,
  RefreshResponseApi,
} from "@/types";

interface UsePricesReturn {
  refreshPrices: () => Promise<RefreshResponseApi>;
  exchangeRates: Map<string, number>;
  lastRefreshedAt: string | null;
  priceMode: DataFreshness | null;
  toKrw: (amount: number, currency: string) => number | null;
  loadingRates: boolean;
}

export function usePrices(): UsePricesReturn {
  const { data: session } = useSession();
  const accessToken = (session as { accessToken?: string } | null)?.accessToken;

  const [exchangeRates, setExchangeRates] = useState<Map<string, number>>(
    new Map(),
  );
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [priceMode, setPriceMode] = useState<DataFreshness | null>(null);
  const [loadingRates, setLoadingRates] = useState(false);

  // 환율 Map 구성 헬퍼
  const buildRateMap = useCallback((rates: ExchangeRateApi[]) => {
    const map = new Map<string, number>();
    for (const r of rates) {
      map.set(`${r.from_currency}_${r.to_currency}`, r.rate);
    }
    return map;
  }, []);

  const canFetch = AUTH_DISABLED || !!accessToken;

  // 마운트 시 환율 + 모드 조회
  useEffect(() => {
    if (!canFetch) return;

    setLoadingRates(true);

    const fetchInitial = async () => {
      try {
        const [rates, mode] = await Promise.all([
          apiFetch<ExchangeRateApi[]>("/api/prices/exchange-rates", {
            ...(accessToken && { accessToken }),
          }),
          apiFetch<PriceModeApi>("/api/prices/mode", { ...(accessToken && { accessToken }) }),
        ]);
        setExchangeRates(buildRateMap(rates));
        setPriceMode(mode.current_mode);
      } catch (err) {
        console.warn("환율/모드 초기 로드 실패", err);
      } finally {
        setLoadingRates(false);
      }
    };

    fetchInitial();
  }, [canFetch, accessToken, buildRateMap]);

  // 시세 갱신
  const refreshPrices = useCallback(async (): Promise<RefreshResponseApi> => {
    if (!canFetch) throw new Error("인증이 필요합니다.");

    const res = await apiFetch<RefreshResponseApi>("/api/prices/refresh", {
      method: "POST",
      ...(accessToken && { accessToken }),
    });

    setLastRefreshedAt(res.refreshed_at);

    if (res.exchange_rates.length > 0) {
      setExchangeRates(buildRateMap(res.exchange_rates));
    }

    return res;
  }, [canFetch, accessToken, buildRateMap]);

  // 환율 변환 헬퍼
  const toKrw = useCallback(
    (amount: number, currency: string): number | null => {
      if (currency === "KRW") return amount;
      const rate = exchangeRates.get(`${currency}_KRW`);
      if (rate == null) return null;
      return amount * rate;
    },
    [exchangeRates],
  );

  return {
    refreshPrices,
    exchangeRates,
    lastRefreshedAt,
    priceMode,
    toKrw,
    loadingRates,
  };
}
