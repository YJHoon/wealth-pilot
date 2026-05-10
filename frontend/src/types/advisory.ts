// 원클릭 분석·매매 (Advisory) 타입.
// 백엔드 `app/schemas/advisory.py` 와 1:1 매칭.

import type { TradingMode } from "@/types/trading";

export type AnalysisRunStatus =
  | "pending"
  | "analyzing"
  | "ready"
  | "executing"
  | "done"
  | "failed";

export type AnalysisItemSource = "holding" | "auto_pick";
export type AnalysisItemAction = "buy" | "sell" | "hold";
export type AnalysisItemDecision =
  | "pending"
  | "approved"
  | "skipped"
  | "rejected";

export interface CandidatePoolOptions {
  top_n?: number;
  market?: "KOSPI" | "KOSDAQ" | "ALL";
  min_volume_value?: number;
  blacklist?: string[];
}

// ── API 응답 (snake_case) ──

export interface AnalysisRunItemApi {
  id: string;
  ticker: string;
  ticker_name: string;
  source: AnalysisItemSource;
  action: AnalysisItemAction;
  confidence: number;
  reason: string | null;
  ref_price: number | string | null;
  suggested_qty: number | string | null;
  decision: AnalysisItemDecision;
  blocked_reason: string | null;
  order_id: string | null;
}

export interface AnalysisRunApi {
  id: string;
  account_id: string;
  mode: TradingMode;
  status: AnalysisRunStatus;
  budget_krw: number | string;
  candidate_pool_options: CandidatePoolOptions;
  started_at: string;
  completed_at: string | null;
  expires_at: string | null;
  summary_json: Record<string, unknown> | null;
  error_message: string | null;
  items: AnalysisRunItemApi[];
  expired: boolean;
}

export interface AnalysisRunSummaryApi {
  id: string;
  account_id: string;
  mode: TradingMode;
  status: AnalysisRunStatus;
  started_at: string;
  completed_at: string | null;
  expires_at: string | null;
  item_count: number;
}

export interface AnalysisRunListApi {
  items: AnalysisRunSummaryApi[];
  total: number;
  limit: number;
  offset: number;
}

export interface ExecuteItemResultApi {
  item_id: string;
  ticker: string;
  action: AnalysisItemAction;
  success: boolean;
  order_id: string | null;
  error_message: string | null;
}

export interface ExecuteResponseApi {
  run_id: string;
  executed: number;
  failed: number;
  results: ExecuteItemResultApi[];
}

// ── 프론트 타입 (camelCase) ──

export interface AnalysisRunItem {
  id: string;
  ticker: string;
  tickerName: string;
  source: AnalysisItemSource;
  action: AnalysisItemAction;
  confidence: number;
  reason: string | null;
  refPrice: number | null;
  suggestedQty: number | null;
  decision: AnalysisItemDecision;
  blockedReason: string | null;
  orderId: string | null;
}

export interface AnalysisRun {
  id: string;
  accountId: string;
  mode: TradingMode;
  status: AnalysisRunStatus;
  budgetKrw: number;
  candidatePoolOptions: CandidatePoolOptions;
  startedAt: string;
  completedAt: string | null;
  expiresAt: string | null;
  summaryJson: Record<string, unknown> | null;
  errorMessage: string | null;
  items: AnalysisRunItem[];
  expired: boolean;
}

export interface AnalysisRunSummary {
  id: string;
  accountId: string;
  mode: TradingMode;
  status: AnalysisRunStatus;
  startedAt: string;
  completedAt: string | null;
  expiresAt: string | null;
  itemCount: number;
}

export interface AnalysisRunList {
  items: AnalysisRunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ExecuteItemResult {
  itemId: string;
  ticker: string;
  action: AnalysisItemAction;
  success: boolean;
  orderId: string | null;
  errorMessage: string | null;
}

export interface ExecuteResponse {
  runId: string;
  executed: number;
  failed: number;
  results: ExecuteItemResult[];
}

// ── 요청 타입 ──

export interface RunCreateRequest {
  account_id: string;
  mode: TradingMode;
  budget_krw: number;
  candidate_pool_options?: CandidatePoolOptions;
}

export interface DecisionUpdateRequest {
  item_id: string;
  decision: "approved" | "rejected";
}

export interface DecisionsRequest {
  decisions: DecisionUpdateRequest[];
}

export interface ExecuteRequest {
  totp_code?: string;
}

// ── 변환 함수 ──

function toNumberOrNull(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function toAnalysisRunItem(api: AnalysisRunItemApi): AnalysisRunItem {
  return {
    id: api.id,
    ticker: api.ticker,
    tickerName: api.ticker_name,
    source: api.source,
    action: api.action,
    confidence: api.confidence,
    reason: api.reason,
    refPrice: toNumberOrNull(api.ref_price),
    suggestedQty: toNumberOrNull(api.suggested_qty),
    decision: api.decision,
    blockedReason: api.blocked_reason,
    orderId: api.order_id,
  };
}

export function toAnalysisRun(api: AnalysisRunApi): AnalysisRun {
  return {
    id: api.id,
    accountId: api.account_id,
    mode: api.mode,
    status: api.status,
    budgetKrw: Number(api.budget_krw),
    candidatePoolOptions: api.candidate_pool_options ?? {},
    startedAt: api.started_at,
    completedAt: api.completed_at,
    expiresAt: api.expires_at,
    summaryJson: api.summary_json,
    errorMessage: api.error_message,
    items: (api.items ?? []).map(toAnalysisRunItem),
    expired: api.expired,
  };
}

export function toAnalysisRunSummary(
  api: AnalysisRunSummaryApi,
): AnalysisRunSummary {
  return {
    id: api.id,
    accountId: api.account_id,
    mode: api.mode,
    status: api.status,
    startedAt: api.started_at,
    completedAt: api.completed_at,
    expiresAt: api.expires_at,
    itemCount: api.item_count,
  };
}

export function toAnalysisRunList(api: AnalysisRunListApi): AnalysisRunList {
  return {
    items: (api.items ?? []).map(toAnalysisRunSummary),
    total: api.total,
    limit: api.limit,
    offset: api.offset,
  };
}

export function toExecuteResponse(api: ExecuteResponseApi): ExecuteResponse {
  return {
    runId: api.run_id,
    executed: api.executed,
    failed: api.failed,
    results: (api.results ?? []).map((r) => ({
      itemId: r.item_id,
      ticker: r.ticker,
      action: r.action,
      success: r.success,
      orderId: r.order_id,
      errorMessage: r.error_message,
    })),
  };
}

// ── 라벨/판정 헬퍼 ──

export const runStatusLabels: Record<AnalysisRunStatus, string> = {
  pending: "준비 중",
  analyzing: "분석 중",
  ready: "결과 준비",
  executing: "발주 중",
  done: "완료",
  failed: "실패",
};

export const itemActionLabels: Record<AnalysisItemAction, string> = {
  buy: "매수",
  sell: "매도",
  hold: "관망",
};

export const itemDecisionLabels: Record<AnalysisItemDecision, string> = {
  pending: "대기",
  approved: "승인",
  // "차단" 은 blocked_reason 의미와 충돌해 UI 혼동을 일으킨다 — 자동 마킹된 항목은 "스킵".
  skipped: "스킵",
  rejected: "거절",
};

export const itemSourceLabels: Record<AnalysisItemSource, string> = {
  holding: "보유",
  auto_pick: "자동선정",
};

export const RUN_IN_PROGRESS_STATUSES: AnalysisRunStatus[] = [
  "pending",
  "analyzing",
  "executing",
];

export function isRunInProgress(status: AnalysisRunStatus): boolean {
  return RUN_IN_PROGRESS_STATUSES.includes(status);
}
