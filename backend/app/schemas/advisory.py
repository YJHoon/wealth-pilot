"""원클릭 분석·매매 (Advisory) Pydantic v2 스키마.

`/api/analysis/runs` 라우터의 요청·응답 스키마 정의.
금액/수량 응답 값은 마스킹 토글이 프론트에서 처리하므로 평문 Decimal로 노출한다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings
from app.models.trading import (
    AnalysisItemAction,
    AnalysisItemDecision,
    AnalysisItemSource,
    AnalysisRun,
    AnalysisRunItem,
    AnalysisRunStatus,
    TradingMode,
)
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
)


# ──────────────────────────────────────────────
# 요청 스키마
# ──────────────────────────────────────────────

class RunCreateRequest(BaseModel):
    """POST /api/analysis/runs — run 생성 본문."""

    account_id: UUID
    mode: TradingMode
    budget_krw: Decimal = Field(..., gt=Decimal("0"))
    candidate_pool_options: dict[str, Any] | None = None

    @field_validator("budget_krw")
    @classmethod
    def _budget_within_limit(cls, v: Decimal) -> Decimal:
        # 1회 run 예산 상한 — 운영 사고 방지용 안전장치.
        # 절대 상한은 ADVISORY_MAX_RUN_BUDGET_KRW (env) 로 설정.
        max_budget = settings.advisory_max_run_budget_krw
        if v > max_budget:
            raise ValueError(
                f"1회 run 예산은 {max_budget}원을 초과할 수 없습니다."
            )
        return v


class DecisionUpdate(BaseModel):
    """종목별 approve/reject 결정 1건."""

    item_id: UUID
    # 클라이언트가 보내는 결정. APPROVED/REJECTED 만 허용.
    decision: AnalysisItemDecision

    @field_validator("decision")
    @classmethod
    def _only_approve_or_reject(cls, v: AnalysisItemDecision) -> AnalysisItemDecision:
        if v not in (AnalysisItemDecision.APPROVED, AnalysisItemDecision.REJECTED):
            raise ValueError("decision 은 approved/rejected 만 허용합니다.")
        return v


class DecisionsRequest(BaseModel):
    """POST /api/analysis/runs/{id}/decisions — 일괄 결정 본문."""

    decisions: list[DecisionUpdate] = Field(..., min_length=1)


class ExecuteRequest(BaseModel):
    """POST /api/analysis/runs/{id}/execute — 발주 본문.

    live 모드는 totp_code 필수. paper 모드는 무시.
    """

    totp_code: str | None = None


# ──────────────────────────────────────────────
# 응답 스키마
# ──────────────────────────────────────────────

class AnalysisRunItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: UUID
    ticker: str
    ticker_name: str
    source: AnalysisItemSource
    action: AnalysisItemAction
    confidence: int
    reason: str | None
    ref_price: Decimal | None
    suggested_qty: Decimal | None
    decision: AnalysisItemDecision
    blocked_reason: str | None
    order_id: UUID | None


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: UUID
    account_id: UUID
    mode: TradingMode
    status: AnalysisRunStatus
    budget_krw: Decimal
    candidate_pool_options: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    summary_json: dict[str, Any] | None
    error_message: str | None
    items: list[AnalysisRunItemResponse]
    expired: bool


class AnalysisRunSummaryResponse(BaseModel):
    """이력 목록용 요약 — items 미포함."""

    model_config = ConfigDict(from_attributes=False)

    id: UUID
    account_id: UUID
    mode: TradingMode
    status: AnalysisRunStatus
    started_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    item_count: int


class AnalysisRunListResponse(BaseModel):
    items: list[AnalysisRunSummaryResponse]
    total: int
    limit: int
    offset: int


class ExecuteItemResult(BaseModel):
    """발주 결과 1건."""

    item_id: UUID
    ticker: str
    action: AnalysisItemAction
    success: bool
    order_id: UUID | None = None
    error_message: str | None = None


class ExecuteResponse(BaseModel):
    run_id: UUID
    executed: int
    failed: int
    results: list[ExecuteItemResult]


# ──────────────────────────────────────────────
# 모델 → 스키마 변환 헬퍼
# ──────────────────────────────────────────────

def item_to_response(item: AnalysisRunItem) -> AnalysisRunItemResponse:
    return AnalysisRunItemResponse(
        id=item.id,
        ticker=item.ticker,
        ticker_name=item.ticker_name,
        source=item.source,
        action=item.action,
        confidence=item.confidence,
        reason=item.reason,
        ref_price=decrypt_decimal_optional(item.ref_price),
        suggested_qty=decrypt_decimal_optional(item.suggested_qty),
        decision=item.decision,
        blocked_reason=item.blocked_reason,
        order_id=item.order_id,
    )


def run_to_response(
    run: AnalysisRun,
    items: list[AnalysisRunItem],
    *,
    now: datetime,
) -> AnalysisRunResponse:
    expired = (
        run.expires_at is not None
        and run.status == AnalysisRunStatus.READY
        and run.expires_at < now
    )
    return AnalysisRunResponse(
        id=run.id,
        account_id=run.account_id,
        mode=run.mode,
        status=run.status,
        budget_krw=decrypt_decimal(run.budget_krw),
        candidate_pool_options=run.candidate_pool_options or {},
        started_at=run.started_at,
        completed_at=run.completed_at,
        expires_at=run.expires_at,
        summary_json=run.summary_json,
        error_message=run.error_message,
        items=[item_to_response(it) for it in items],
        expired=expired,
    )


def run_to_summary(run: AnalysisRun, item_count: int) -> AnalysisRunSummaryResponse:
    return AnalysisRunSummaryResponse(
        id=run.id,
        account_id=run.account_id,
        mode=run.mode,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        expires_at=run.expires_at,
        item_count=item_count,
    )
