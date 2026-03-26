"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";
import {
  WatchlistItem,
  WatchlistItemApi,
  WatchlistCreateRequest,
  WatchlistUpdateRequest,
  toWatchlistItem,
} from "@/types";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

interface UseWatchlistReturn {
  items: WatchlistItem[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  addItem: (data: WatchlistCreateRequest) => Promise<WatchlistItem>;
  updateItem: (id: string, data: WatchlistUpdateRequest) => Promise<WatchlistItem>;
  removeItem: (id: string) => Promise<void>;
}

export function useWatchlist(): UseWatchlistReturn {
  const { data: session } = useSession();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;

  const fetchItems = useCallback(async () => {
    if (!canFetch) {
      setItems([]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await apiFetch<WatchlistItemApi[]>("/api/analysis/watchlist", {
        ...(accessToken && { accessToken }),
      });
      setItems(res.map(toWatchlistItem));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "관심종목을 불러오는데 실패했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }, [canFetch, accessToken]);

  useEffect(() => {
    fetchItems().catch(() => {});
  }, [fetchItems]);

  const addItem = useCallback(
    async (data: WatchlistCreateRequest): Promise<WatchlistItem> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<WatchlistItemApi>("/api/analysis/watchlist", {
        method: "POST",
        body: JSON.stringify(data),
        ...(accessToken && { accessToken }),
      });
      await fetchItems().catch(() => {});
      return toWatchlistItem(res);
    },
    [canFetch, accessToken, fetchItems],
  );

  const updateItem = useCallback(
    async (id: string, data: WatchlistUpdateRequest): Promise<WatchlistItem> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<WatchlistItemApi>(`/api/analysis/watchlist/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
        ...(accessToken && { accessToken }),
      });
      await fetchItems().catch(() => {});
      return toWatchlistItem(res);
    },
    [canFetch, accessToken, fetchItems],
  );

  const removeItem = useCallback(
    async (id: string): Promise<void> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      await apiFetch<void>(`/api/analysis/watchlist/${id}`, {
        method: "DELETE",
        ...(accessToken && { accessToken }),
      });
      await fetchItems().catch(() => {});
    },
    [canFetch, accessToken, fetchItems],
  );

  return {
    items,
    loading,
    error,
    refetch: fetchItems,
    addItem,
    updateItem,
    removeItem,
  };
}
