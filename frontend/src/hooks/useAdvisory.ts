"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  type AnalysisRun,
  type AnalysisRunApi,
  type AnalysisRunList,
  type AnalysisRunListApi,
  type DecisionsRequest,
  type ExecuteRequest,
  type ExecuteResponse,
  type ExecuteResponseApi,
  type RunCreateRequest,
  isRunInProgress,
  toAnalysisRun,
  toAnalysisRunList,
  toExecuteResponse,
} from "@/types/advisory";

const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

const POLL_INTERVAL_MS = 2000;

export interface UseAdvisoryReturn {
  run: AnalysisRun | null;
  history: AnalysisRunList | null;
  loading: {
    run: boolean;
    history: boolean;
    creating: boolean;
    submittingDecisions: boolean;
    executing: boolean;
  };
  error: string | null;

  createRun: (data: RunCreateRequest) => Promise<AnalysisRun>;
  loadRun: (runId: string) => Promise<AnalysisRun>;
  setActiveRun: (run: AnalysisRun | null) => void;
  submitDecisions: (
    runId: string,
    body: DecisionsRequest,
  ) => Promise<AnalysisRun>;
  executeRun: (runId: string, body?: ExecuteRequest) => Promise<ExecuteResponse>;
  refreshHistory: (limit?: number, offset?: number) => Promise<void>;
}

export function useAdvisory(): UseAdvisoryReturn {
  const { data: session } = useSession();
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [history, setHistory] = useState<AnalysisRunList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [creating, setCreating] = useState(false);
  const [submittingDecisions, setSubmittingDecisions] = useState(false);
  const [executing, setExecuting] = useState(false);

  const accessToken = (session as { accessToken?: string } | null)?.accessToken;
  const canFetch = AUTH_DISABLED || !!accessToken;
  const fetchOpts = useMemo(
    () => (accessToken ? { accessToken } : {}),
    [accessToken],
  );

  // 폴링 — run.status 가 진행 중이면 2초 간격으로 갱신.
  // 활성 runId 가 바뀌면 이전 timer 정리.
  const pollRunIdRef = useRef<string | null>(null);
  pollRunIdRef.current = run?.id ?? null;

  const loadRun = useCallback(
    async (runId: string): Promise<AnalysisRun> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      const res = await apiFetch<AnalysisRunApi>(
        `/api/analysis/runs/${runId}`,
        fetchOpts,
      );
      const next = toAnalysisRun(res);
      setRun((prev) => (prev?.id === next.id || !prev ? next : prev));
      return next;
    },
    [canFetch, fetchOpts],
  );

  // run.status 가 진행 중이면 폴링.
  useEffect(() => {
    if (!run) return;
    if (!isRunInProgress(run.status)) return;

    let cancelled = false;
    const id = run.id;

    const tick = async () => {
      if (cancelled) return;
      if (pollRunIdRef.current !== id) return;
      try {
        const res = await apiFetch<AnalysisRunApi>(
          `/api/analysis/runs/${id}`,
          fetchOpts,
        );
        if (cancelled) return;
        const next = toAnalysisRun(res);
        setRun((prev) => (prev?.id === id ? next : prev));
        if (isRunInProgress(next.status)) {
          handle = setTimeout(tick, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        // 폴링 중 에러는 토스트 대신 상태에만 반영 — 사용자 토스트 폭주 방지.
        setError(
          err instanceof ApiError ? err.message : "폴링 중 오류가 발생했습니다.",
        );
      }
    };

    let handle: ReturnType<typeof setTimeout> = setTimeout(
      tick,
      POLL_INTERVAL_MS,
    );
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [run, fetchOpts]);

  const createRun = useCallback(
    async (data: RunCreateRequest): Promise<AnalysisRun> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      setCreating(true);
      setError(null);
      try {
        const res = await apiFetch<AnalysisRunApi>("/api/analysis/runs", {
          method: "POST",
          body: JSON.stringify(data),
          ...fetchOpts,
        });
        const next = toAnalysisRun(res);
        setRun(next);
        return next;
      } finally {
        setCreating(false);
      }
    },
    [canFetch, fetchOpts],
  );

  const submitDecisions = useCallback(
    async (
      runId: string,
      body: DecisionsRequest,
    ): Promise<AnalysisRun> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      setSubmittingDecisions(true);
      setError(null);
      try {
        const res = await apiFetch<AnalysisRunApi>(
          `/api/analysis/runs/${runId}/decisions`,
          {
            method: "POST",
            body: JSON.stringify(body),
            ...fetchOpts,
          },
        );
        const next = toAnalysisRun(res);
        setRun((prev) => (prev?.id === runId ? next : prev));
        return next;
      } finally {
        setSubmittingDecisions(false);
      }
    },
    [canFetch, fetchOpts],
  );

  const executeRun = useCallback(
    async (
      runId: string,
      body: ExecuteRequest = {},
    ): Promise<ExecuteResponse> => {
      if (!canFetch) throw new Error("인증이 필요합니다.");
      setExecuting(true);
      setError(null);
      try {
        const res = await apiFetch<ExecuteResponseApi>(
          `/api/analysis/runs/${runId}/execute`,
          {
            method: "POST",
            body: JSON.stringify(body),
            ...fetchOpts,
          },
        );
        // 발주 후 상태 재조회 (DONE/FAILED 마킹 반영)
        try {
          await loadRun(runId);
        } catch {
          // 본 응답은 받았으니 후속 조회 실패는 조용히 넘어간다
        }
        return toExecuteResponse(res);
      } finally {
        setExecuting(false);
      }
    },
    [canFetch, fetchOpts, loadRun],
  );

  const refreshHistory = useCallback(
    async (limit: number = 20, offset: number = 0): Promise<void> => {
      if (!canFetch) {
        setHistory(null);
        return;
      }
      setLoadingHistory(true);
      try {
        const res = await apiFetch<AnalysisRunListApi>(
          `/api/analysis/runs?limit=${limit}&offset=${offset}`,
          fetchOpts,
        );
        setHistory(toAnalysisRunList(res));
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "분석 이력을 불러오는데 실패했습니다.",
        );
      } finally {
        setLoadingHistory(false);
      }
    },
    [canFetch, fetchOpts],
  );

  // 최초 로드 — 진행 중 run 자동 복귀
  useEffect(() => {
    if (!canFetch) return;
    let cancelled = false;
    (async () => {
      setLoadingRun(true);
      try {
        const res = await apiFetch<AnalysisRunListApi>(
          `/api/analysis/runs?limit=5&offset=0`,
          fetchOpts,
        );
        if (cancelled) return;
        const list = toAnalysisRunList(res);
        setHistory(list);
        // 진행 중 또는 가장 최근 READY run 을 활성으로 복귀
        const inFlight = list.items.find((r) => isRunInProgress(r.status));
        const recentReady = list.items.find((r) => r.status === "ready");
        const target = inFlight ?? recentReady;
        if (target) {
          try {
            const detail = await apiFetch<AnalysisRunApi>(
              `/api/analysis/runs/${target.id}`,
              fetchOpts,
            );
            if (!cancelled) setRun(toAnalysisRun(detail));
          } catch {
            /* 무시 */
          }
        }
      } catch {
        /* 무시 — 이력 비어있을 수 있음 */
      } finally {
        if (!cancelled) setLoadingRun(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canFetch, fetchOpts]);

  const setActiveRun = useCallback((next: AnalysisRun | null) => {
    setRun(next);
  }, []);

  return {
    run,
    history,
    loading: {
      run: loadingRun,
      history: loadingHistory,
      creating,
      submittingDecisions,
      executing,
    },
    error,
    createRun,
    loadRun,
    setActiveRun,
    submitDecisions,
    executeRun,
    refreshHistory,
  };
}
