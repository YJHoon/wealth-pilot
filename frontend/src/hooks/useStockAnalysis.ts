"use client";

/**
 * 종목 분석 훅 — fundamental/technical/signals 병렬 fetch
 */

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";
import {
  FundamentalAnalysis,
  FundamentalAnalysisApi,
  TechnicalAnalysis,
  TechnicalAnalysisApi,
  TradingSignals,
  TradingSignalsApi,
  MARKETS,
  MarketType,
  toFundamentalAnalysis,
  toTechnicalAnalysis,
  toTradingSignals,
} from "@/types";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

interface UseStockAnalysisOptions {
  ticker: string;
  market?: MarketType;
  enabled?: boolean;
}

interface UseStockAnalysisReturn {
  fundamental: FundamentalAnalysis | null;
  technical: TechnicalAnalysis | null;
  signals: TradingSignals | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useStockAnalysis({
  ticker,
  market = MARKETS[0],
  enabled = true,
}: UseStockAnalysisOptions): UseStockAnalysisReturn {
  const { data: session } = useSession();
  const [fundamental, setFundamental] = useState<FundamentalAnalysis | null>(null);
  const [technical, setTechnical] = useState<TechnicalAnalysis | null>(null);
  const [signals, setSignals] = useState<TradingSignals | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;

  const fetchAnalysis = useCallback(async () => {
    if (!canFetch || !enabled || !ticker) {
      setFundamental(null);
      setTechnical(null);
      setSignals(null);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    const tokenOpts = accessToken ? { accessToken } : {};
    const qs = `?market=${encodeURIComponent(market)}`;

    try {
      const [fundRes, techRes, sigRes] = await Promise.all([
        apiFetch<FundamentalAnalysisApi>(
          `/api/analysis/stock/${encodeURIComponent(ticker)}${qs}`,
          tokenOpts,
        ),
        apiFetch<TechnicalAnalysisApi>(
          `/api/analysis/stock/${encodeURIComponent(ticker)}/technical${qs}`,
          tokenOpts,
        ),
        apiFetch<TradingSignalsApi>(
          `/api/analysis/stock/${encodeURIComponent(ticker)}/signals${qs}`,
          tokenOpts,
        ),
      ]);

      setFundamental(toFundamentalAnalysis(fundRes));
      setTechnical(toTechnicalAnalysis(techRes));
      setSignals(toTradingSignals(sigRes));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "종목 분석 데이터를 불러오는데 실패했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }, [canFetch, enabled, ticker, market, accessToken]);

  useEffect(() => {
    fetchAnalysis().catch(() => {});
  }, [fetchAnalysis]);

  return {
    fundamental,
    technical,
    signals,
    loading,
    error,
    refetch: fetchAnalysis,
  };
}
