"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";
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

  const fetchAssets = useCallback(async () => {
    if (!accessToken) return;
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
        { accessToken },
      );
      setAssets(res.assets.map(toAsset));
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "자산 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, options.type, options.status, options.groupId]);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  const createAsset = useCallback(
    async (data: AssetCreateRequest): Promise<Asset> => {
      const res = await apiFetch<AssetApiResponse>("/api/assets", {
        method: "POST",
        body: JSON.stringify(data),
        accessToken,
      });
      await fetchAssets();
      return toAsset(res);
    },
    [accessToken, fetchAssets],
  );

  const updateAsset = useCallback(
    async (id: string, data: AssetUpdateRequest): Promise<Asset> => {
      const res = await apiFetch<AssetApiResponse>(`/api/assets/${id}`, {
        method: "PUT",
        body: JSON.stringify(data),
        accessToken,
      });
      await fetchAssets();
      return toAsset(res);
    },
    [accessToken, fetchAssets],
  );

  const deleteAsset = useCallback(
    async (id: string): Promise<void> => {
      await apiFetch<void>(`/api/assets/${id}`, {
        method: "DELETE",
        accessToken,
      });
      await fetchAssets();
    },
    [accessToken, fetchAssets],
  );

  const sellAsset = useCallback(
    async (id: string, data: SellRequest): Promise<Asset> => {
      const res = await apiFetch<AssetApiResponse>(`/api/assets/${id}/sell`, {
        method: "POST",
        body: JSON.stringify(data),
        accessToken,
      });
      await fetchAssets();
      return toAsset(res);
    },
    [accessToken, fetchAssets],
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
