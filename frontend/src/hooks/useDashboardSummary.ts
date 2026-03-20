"use client";

import useSWR from "swr";
import { useSession } from "next-auth/react";
import { apiFetch } from "@/lib/api";
import {
  DashboardSummary,
  DashboardSummaryApi,
  toDashboardSummary,
} from "@/types";

export function useDashboardSummary() {
  const { data: session } = useSession();
  const accessToken = (session as { accessToken?: string } | null)?.accessToken;

  const { data, error, isLoading, mutate } = useSWR<DashboardSummary>(
    accessToken ? "/api/dashboard/summary" : null,
    (path: string) =>
      apiFetch<DashboardSummaryApi>(path, { accessToken: accessToken! }).then(
        toDashboardSummary,
      ),
    {
      revalidateOnFocus: false,
      dedupingInterval: 30_000,
    },
  );

  return {
    summary: data ?? null,
    loading: isLoading,
    error: error ? (error instanceof Error ? error.message : "데이터를 불러오는데 실패했습니다.") : null,
    refetch: mutate,
  };
}
