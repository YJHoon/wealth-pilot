"use client";

/**
 * 시뮬레이션 실행 훅 — DCA / 포트폴리오 / 시나리오
 */

import { useCallback, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { apiFetch, ApiError } from "@/lib/api";
import {
  SimulationParams,
  SimulationRequestApi,
  SimulationResponse,
  SimulationResponseApi,
  toSimulationParamsApi,
  toSimulationResponse,
} from "@/types";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

interface UseSimulationReturn {
  result: SimulationResponse | null;
  loading: boolean;
  error: string | null;
  runSimulation: (params: SimulationParams) => Promise<SimulationResponse>;
  reset: () => void;
}

export function useSimulation(): UseSimulationReturn {
  const { data: session } = useSession();
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;

  const runSimulation = useCallback(
    async (params: SimulationParams): Promise<SimulationResponse> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");

      const currentRequestId = ++requestIdRef.current;
      setLoading(true);
      setError(null);

      try {
        const body: SimulationRequestApi = { params: toSimulationParamsApi(params) };
        const res = await apiFetch<SimulationResponseApi>("/api/analysis/simulate", {
          method: "POST",
          body: JSON.stringify(body),
          ...(accessToken && { accessToken }),
        });
        const converted = toSimulationResponse(res);
        if (requestIdRef.current === currentRequestId) {
          setResult(converted);
        }
        return converted;
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "시뮬레이션 실행에 실패했습니다.";
        if (requestIdRef.current === currentRequestId) {
          setError(message);
        }
        throw err;
      } finally {
        if (requestIdRef.current === currentRequestId) {
          setLoading(false);
        }
      }
    },
    [canFetch, accessToken],
  );

  const reset = useCallback(() => {
    requestIdRef.current++;
    setResult(null);
    setError(null);
    setLoading(false);
  }, []);

  return {
    result,
    loading,
    error,
    runSimulation,
    reset,
  };
}
