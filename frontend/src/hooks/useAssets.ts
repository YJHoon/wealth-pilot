"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";
import {
  Asset,
  AssetType,
  AssetStatus,
  AssetCreateRequest,
  AssetUpdateRequest,
  SellRequest,
  AssetListApiResponse,
  AssetApiResponse,
  toAsset,
} from "@/types";

interface UseAssetsOptions {
  type?: AssetType;
  status?: AssetStatus;
  groupId?: string;
}

interface UseAssetsReturn {
  assets: Asset[];
  total: number;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  createAsset: (data: AssetCreateRequest) => Promise<Asset>;
  updateAsset: (id: string, data: AssetUpdateRequest) => Promise<Asset>;
  deleteAsset: (id: string) => Promise<void>;
  sellAsset: (id: string, data: SellRequest) => Promise<Asset>;
}

export function useAssets(options: UseAssetsOptions = {}): UseAssetsReturn {
  const { data: session } = useSession();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;

  const fetchAssets = useCallback(async () => {
    if (!canFetch) {
      setAssets([]);
      setTotal(0);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (options.type) params.set("type", options.type);
      if (options.status) params.set("status", options.status);
      if (options.groupId) params.set("group_id", options.groupId);
      const qs = params.toString();
      const res = await apiFetch<AssetListApiResponse>(
        `/api/assets${qs ? `?${qs}` : ""}`,
        { ...(accessToken && { accessToken }) },
      );
      setAssets(res.assets.map(toAsset));
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "자산 목록을 불러오는데 실패했습니다.");
      throw err;
    } finally {
      setLoading(false);
    }
  }, [canFetch, accessToken, options.type, options.status, options.groupId]);

  useEffect(() => {
    fetchAssets().catch(() => {});
  }, [fetchAssets]);

  const createAsset = useCallback(
    async (data: AssetCreateRequest): Promise<Asset> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<AssetApiResponse>("/api/assets", {
        method: "POST",
        body: JSON.stringify(data),
        ...(accessToken && { accessToken }),
      });
      await fetchAssets().catch(() => {});
      return toAsset(res);
    },
    [canFetch, accessToken, fetchAssets],
  );

  const updateAsset = useCallback(
    async (id: string, data: AssetUpdateRequest): Promise<Asset> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<AssetApiResponse>(`/api/assets/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
        ...(accessToken && { accessToken }),
      });
      await fetchAssets().catch(() => {});
      return toAsset(res);
    },
    [canFetch, accessToken, fetchAssets],
  );

  const deleteAsset = useCallback(
    async (id: string): Promise<void> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      await apiFetch<void>(`/api/assets/${id}`, {
        method: "DELETE",
        ...(accessToken && { accessToken }),
      });
      await fetchAssets().catch(() => {});
    },
    [canFetch, accessToken, fetchAssets],
  );

  const sellAsset = useCallback(
    async (id: string, data: SellRequest): Promise<Asset> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<AssetApiResponse>(`/api/assets/${id}/sell`, {
        method: "POST",
        body: JSON.stringify(data),
        ...(accessToken && { accessToken }),
      });
      await fetchAssets().catch(() => {});
      return toAsset(res);
    },
    [canFetch, accessToken, fetchAssets],
  );

  return {
    assets,
    total,
    loading,
    error,
    refetch: fetchAssets,
    createAsset,
    updateAsset,
    deleteAsset,
    sellAsset,
  };
}
