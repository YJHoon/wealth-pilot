"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";
import {
  PortfolioGroup,
  GroupListApiResponse,
  toGroup,
} from "@/types";

interface UseGroupsReturn {
  groups: PortfolioGroup[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useGroups(): UseGroupsReturn {
  const { data: session } = useSession();
  const [groups, setGroups] = useState<PortfolioGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;

  const fetchGroups = useCallback(async () => {
    if (!canFetch) {
      setGroups([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<GroupListApiResponse>("/api/groups", {
        ...(accessToken && { accessToken }),
      });
      setGroups(res.groups.map(toGroup));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "그룹 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [canFetch, accessToken]);

  useEffect(() => {
    fetchGroups();
  }, [fetchGroups]);

  return { groups, loading, error, refetch: fetchGroups };
}
