"use client";

/**
 * 국내 종목(KOSPI/KOSDAQ) 이름/코드 자동완성 검색 훅
 * 300ms debounce 후 `/api/market/search` 호출
 */

import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";

export interface TickerSearchItem {
  ticker: string;
  name: string;
  market: "KOSPI" | "KOSDAQ" | "KONEX";
}

interface SearchResponse {
  query: string;
  results: TickerSearchItem[];
}

interface UseTickerSearchOptions {
  debounceMs?: number;
  limit?: number;
}

interface UseTickerSearchReturn {
  query: string;
  setQuery: (q: string) => void;
  results: TickerSearchItem[];
  loading: boolean;
  error: string | null;
}

export function useTickerSearch({
  debounceMs = 300,
  limit = 20,
}: UseTickerSearchOptions = {}): UseTickerSearchReturn {
  const { data: session } = useSession();
  const accessToken = (session as { accessToken?: string } | null)?.accessToken;

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TickerSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 동시 요청 경합 방지 — 최신 query만 반영
  const latestQueryRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }

    const reqId = ++latestQueryRef.current;
    const handle = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch<SearchResponse>(
          `/api/market/search?q=${encodeURIComponent(trimmed)}&limit=${limit}`,
          { ...(accessToken && { accessToken }) },
        );
        if (reqId !== latestQueryRef.current) return; // 오래된 응답 무시
        setResults(res.results);
      } catch (err) {
        if (reqId !== latestQueryRef.current) return;
        setError(err instanceof ApiError ? err.message : "검색 실패");
        setResults([]);
      } finally {
        if (reqId === latestQueryRef.current) setLoading(false);
      }
    }, debounceMs);

    return () => clearTimeout(handle);
  }, [query, debounceMs, limit, accessToken]);

  return { query, setQuery, results, loading, error };
}
