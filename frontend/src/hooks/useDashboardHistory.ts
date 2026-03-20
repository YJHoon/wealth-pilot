"use client";

import useSWR from "swr";
import { useSession } from "next-auth/react";
import { apiFetch } from "@/lib/api";
import type { DashboardHistoryApi, HistoryDataPointApi } from "@/types";

export interface HistoryDataPoint {
  date: string;
  totalValueKrw: number;
}

function toHistoryPoints(api: DashboardHistoryApi): HistoryDataPoint[] {
  return api.data_points.map((dp: HistoryDataPointApi) => ({
    date: dp.date,
    totalValueKrw: dp.total_value_krw,
  }));
}

export function useDashboardHistory(period: string = "3M") {
  const { data: session } = useSession();
  const accessToken = session?.accessToken;

  const { data, error, isLoading } = useSWR<HistoryDataPoint[]>(
    accessToken ? `/api/dashboard/history?period=${period}` : null,
    (path: string) =>
      apiFetch<DashboardHistoryApi>(path, { accessToken: accessToken! }).then(
        toHistoryPoints,
      ),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60_000,
    },
  );

  return {
    history: data ?? [],
    loading: isLoading,
    error: error ? (error instanceof Error ? error.message : "히스토리를 불러오는데 실패했습니다.") : null,
  };
}
