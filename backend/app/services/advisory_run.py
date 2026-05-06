"""원클릭 분석 실행 오케스트레이터.

`AnalysisRun` 1건을 입력으로 받아:
1. 종목별 시세 + LLM 호출을 동시성 제한과 타임아웃으로 실행
2. 결과를 `AnalysisRunItem` 행으로 영속화
3. min_confidence 미달은 자동 차단(decision=skipped)
4. BUY 후보 합 > 예산이면 신뢰도 순으로 자르고 나머지를 skipped 처리

LLM 호출이 부분 실패해도 안전 폴백(hold)로 전체 잡을 진행시킨다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trading import (
    AnalysisItemAction,
    AnalysisItemDecision,
    AnalysisItemSource,
    AnalysisRun,
    AnalysisRunItem,
    AnalysisRunStatus,
)
from app.services.advisory_candidate import CandidateItem, CandidatePool
from app.services.crypto_service import (
    decrypt_decimal,
    encrypt_decimal_optional,
)
from app.services.llm_advisor import (
    LLMDecision,
    PortfolioContext,
    get_llm_decision,
)

logger = logging.getLogger(__name__)


# 결과 TTL — `expires_at` 경과 시 /execute 차단, 재분석 강제
DEFAULT_TTL_MINUTES = 5

# 시세 조회 동시성 제한 (KIS rate limit 감안). LLM은 별도 limit.
DEFAULT_PRICE_CONCURRENCY = 4
DEFAULT_LLM_CONCURRENCY = 4

# per-call timeout
DEFAULT_PRICE_TIMEOUT = 10.0
DEFAULT_LLM_TIMEOUT = 30.0

PriceFetcher = Callable[[str], Awaitable[list[dict]]]
LLMCaller = Callable[..., Awaitable[LLMDecision]]


@dataclass(slots=True)
class _ItemEvaluation:
    """후보 1건에 대한 평가 중간 결과."""

    candidate: CandidateItem
    decision: LLMDecision
    blocked_reason: str | None = None


@dataclass(slots=True)
class AnalysisRunSummary:
    """run 종료 후 summary_json 으로 저장할 메타 정보."""

    total: int
    by_action: dict[str, int] = field(default_factory=dict)
    by_decision: dict[str, int] = field(default_factory=dict)
    skipped_low_confidence: int = 0
    skipped_over_budget: int = 0
    failed: int = 0
    elapsed_seconds: float | None = None
    rule_version: str | None = None
    excluded_by_active_strategy: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "by_action": self.by_action,
            "by_decision": self.by_decision,
            "skipped_low_confidence": self.skipped_low_confidence,
            "skipped_over_budget": self.skipped_over_budget,
            "failed": self.failed,
            "elapsed_seconds": self.elapsed_seconds,
            "rule_version": self.rule_version,
            "excluded_by_active_strategy": self.excluded_by_active_strategy,
        }


def _safe_hold_decision(reason: str) -> LLMDecision:
    return LLMDecision(action="hold", confidence=0, reason=f"[안전 폴백] {reason}")


async def _fetch_history_with_timeout(
    fetcher: PriceFetcher,
    ticker: str,
    timeout: float,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[dict] | None, str | None]:
    """시세 조회 — 타임아웃/실패 시 (ticker, None, error_msg)."""
    async with semaphore:
        try:
            history = await asyncio.wait_for(fetcher(ticker), timeout=timeout)
        except asyncio.TimeoutError:
            return ticker, None, "시세 조회 타임아웃"
        except Exception as e:  # noqa: BLE001 — 부분 실패는 로깅 후 진행
            logger.warning("price fetch failed for %s: %s", ticker, e)
            return ticker, None, f"시세 조회 실패: {type(e).__name__}"
    return ticker, history, None


async def _call_llm_with_timeout(
    caller: LLMCaller,
    candidate: CandidateItem,
    price_history: list[dict],
    portfolio: PortfolioContext,
    timeout: float,
    semaphore: asyncio.Semaphore,
) -> _ItemEvaluation:
    """LLM 호출 — 타임아웃/실패 시 hold 폴백."""
    async with semaphore:
        try:
            decision = await asyncio.wait_for(
                caller(
                    ticker=candidate.ticker,
                    ticker_name=candidate.ticker_name,
                    price_history=price_history,
                    portfolio=portfolio,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return _ItemEvaluation(
                candidate=candidate,
                decision=_safe_hold_decision("LLM 타임아웃"),
                blocked_reason="LLM 타임아웃",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM call failed for %s: %s", candidate.ticker, e)
            return _ItemEvaluation(
                candidate=candidate,
                decision=_safe_hold_decision(f"LLM 호출 실패: {type(e).__name__}"),
                blocked_reason=f"LLM 호출 실패: {type(e).__name__}",
            )
    return _ItemEvaluation(candidate=candidate, decision=decision)


def _resolve_action(
    candidate: CandidateItem, decision: LLMDecision,
) -> AnalysisItemAction:
    """LLM 결과를 AnalysisItemAction enum 으로 매핑."""
    raw = decision.action
    if raw == "buy":
        return AnalysisItemAction.BUY
    if raw == "sell":
        return AnalysisItemAction.SELL
    return AnalysisItemAction.HOLD


def _classify_decision(
    candidate: CandidateItem,
    action: AnalysisItemAction,
    decision: LLMDecision,
    min_confidence: int,
) -> tuple[AnalysisItemDecision, str | None]:
    """min_confidence/source 충돌 등을 반영해 초기 decision 결정.

    예산 컷은 분리 단계에서 적용된다.
    """
    if action == AnalysisItemAction.HOLD:
        return AnalysisItemDecision.SKIPPED, "LLM hold"

    if decision.confidence < min_confidence:
        return AnalysisItemDecision.SKIPPED, (
            f"신뢰도 {decision.confidence} < 최소 {min_confidence}"
        )

    # SELL 후보는 advisory 보유분에 한정 (build_candidate_pool에서 보장)
    if action == AnalysisItemAction.SELL:
        if candidate.source != AnalysisItemSource.HOLDING:
            return AnalysisItemDecision.SKIPPED, "SELL 가능한 보유분 없음 (advisory 미보유)"
        if candidate.held_qty is None or candidate.held_qty <= 0:
            return AnalysisItemDecision.SKIPPED, "advisory 보유 수량 0"

    return AnalysisItemDecision.PENDING, None


def _normalize_qty(
    action: AnalysisItemAction,
    candidate: CandidateItem,
    decision: LLMDecision,
) -> Decimal | None:
    """action 별 suggested_qty 결정.

    - BUY: LLM 제안 수량 그대로 (이후 예산 컷 단계에서 추가 조정 가능)
    - SELL: 제안 수량을 보유량 상한으로 cap. 제안이 없으면 보유량 전량.
    - HOLD: None
    """
    if action == AnalysisItemAction.HOLD:
        return None
    if action == AnalysisItemAction.SELL:
        held = candidate.held_qty or Decimal("0")
        if held <= 0:
            return None
        if decision.suggested_quantity is None:
            return held
        return min(Decimal(decision.suggested_quantity), held)
    # BUY
    if decision.suggested_quantity is None:
        return None
    return Decimal(decision.suggested_quantity)


def _apply_budget_cap(
    items: list[AnalysisRunItem],
    budget: Decimal,
) -> int:
    """BUY 후보 합 > 예산이면 신뢰도 내림차순으로 채우고 초과분을 skipped 처리.

    Returns:
        예산 초과로 skipped 마킹된 BUY 항목 수.
    """
    if budget is None or budget <= 0:
        return 0

    buy_items = [
        i for i in items
        if i.action == AnalysisItemAction.BUY
        and i.decision == AnalysisItemDecision.PENDING
    ]
    # 신뢰도 내림차순. 동신뢰도는 ticker 사전순으로 결정성 확보.
    buy_items.sort(key=lambda i: (-i.confidence, i.ticker))

    spent = Decimal("0")
    skipped_count = 0
    for item in buy_items:
        if item.ref_price is None or item.suggested_qty is None:
            continue
        try:
            ref_price = decrypt_decimal(item.ref_price)
            qty = decrypt_decimal(item.suggested_qty)
        except (ValueError, ArithmeticError):
            continue
        cost = ref_price * qty
        if spent + cost > budget:
            item.decision = AnalysisItemDecision.SKIPPED
            prev_reason = item.blocked_reason
            tag = "예산 초과"
            item.blocked_reason = (
                f"{tag} (잔여 예산 부족)" if prev_reason is None
                else f"{prev_reason}; {tag}"
            )
            skipped_count += 1
            continue
        spent += cost
    return skipped_count


async def run_analysis(
    db: AsyncSession,
    run: AnalysisRun,
    *,
    candidates: CandidatePool,
    portfolio: PortfolioContext,
    price_fetcher: PriceFetcher,
    llm_caller: LLMCaller = get_llm_decision,
    min_confidence: int | None = None,
    price_concurrency: int = DEFAULT_PRICE_CONCURRENCY,
    llm_concurrency: int = DEFAULT_LLM_CONCURRENCY,
    price_timeout: float = DEFAULT_PRICE_TIMEOUT,
    llm_timeout: float = DEFAULT_LLM_TIMEOUT,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    now: datetime | None = None,
) -> AnalysisRun:
    """`AnalysisRun` 1건의 분석을 끝까지 실행.

    호출자는 run을 PENDING 상태로 commit한 뒤 이 함수를 호출한다. 이 함수가
    run.status, summary_json, expires_at 을 업데이트하고 AnalysisRunItem 들을
    add 한다. commit 은 호출자 책임.

    실패 시 run.status=FAILED, error_message 세팅.
    """
    started = time.monotonic()
    now = now or datetime.now(timezone.utc)
    min_conf = (
        min_confidence
        if min_confidence is not None
        else settings.llm_advisor_min_confidence
    )

    if not candidates.items:
        run.status = AnalysisRunStatus.READY
        run.completed_at = now
        run.expires_at = now + timedelta(minutes=ttl_minutes)
        run.summary_json = AnalysisRunSummary(
            total=0,
            elapsed_seconds=time.monotonic() - started,
            rule_version=candidates.auto_pick_rule_version,
            excluded_by_active_strategy=candidates.excluded_by_active_strategy,
        ).to_dict()
        return run

    run.status = AnalysisRunStatus.ANALYZING

    # 1) 시세 병렬 조회
    price_sem = asyncio.Semaphore(max(1, price_concurrency))
    price_tasks = [
        _fetch_history_with_timeout(price_fetcher, c.ticker, price_timeout, price_sem)
        for c in candidates.items
    ]
    price_results = await asyncio.gather(*price_tasks)
    history_by_ticker: dict[str, list[dict]] = {}
    fetch_errors: dict[str, str] = {}
    for ticker, history, err in price_results:
        if history is None:
            fetch_errors[ticker] = err or "시세 조회 실패"
        else:
            history_by_ticker[ticker] = history

    # 2) LLM 병렬 호출 — 시세가 있는 종목만
    llm_sem = asyncio.Semaphore(max(1, llm_concurrency))
    llm_tasks = []
    skipped_items: list[_ItemEvaluation] = []
    for c in candidates.items:
        history = history_by_ticker.get(c.ticker)
        if history is None:
            err = fetch_errors.get(c.ticker, "시세 데이터 없음")
            skipped_items.append(
                _ItemEvaluation(
                    candidate=c,
                    decision=_safe_hold_decision(err),
                    blocked_reason=err,
                )
            )
            continue
        llm_tasks.append(
            _call_llm_with_timeout(
                llm_caller, c, history, portfolio, llm_timeout, llm_sem,
            )
        )
    llm_results: list[_ItemEvaluation] = list(
        await asyncio.gather(*llm_tasks)
    ) + skipped_items

    # 3) AnalysisRunItem 생성
    items: list[AnalysisRunItem] = []
    summary = AnalysisRunSummary(
        total=len(llm_results),
        rule_version=candidates.auto_pick_rule_version,
        excluded_by_active_strategy=candidates.excluded_by_active_strategy,
    )

    for ev in llm_results:
        c = ev.candidate
        d = ev.decision
        action = _resolve_action(c, d)
        decision_status, decision_reason = _classify_decision(
            c, action, d, min_conf,
        )

        suggested_qty = _normalize_qty(action, c, d)

        # blocked_reason 우선순위: LLM 폴백 사유 → decision_reason
        blocked_reason = ev.blocked_reason or decision_reason

        item = AnalysisRunItem(
            run_id=run.id,
            ticker=c.ticker,
            ticker_name=c.ticker_name,
            source=c.source,
            action=action,
            confidence=int(d.confidence),
            reason=(d.reason or "")[:1000],
            ref_price=encrypt_decimal_optional(c.ref_price),
            suggested_qty=encrypt_decimal_optional(suggested_qty),
            decision=decision_status,
            blocked_reason=blocked_reason,
        )
        items.append(item)
        db.add(item)

        summary.by_action[action.value] = summary.by_action.get(action.value, 0) + 1
        summary.by_decision[decision_status.value] = (
            summary.by_decision.get(decision_status.value, 0) + 1
        )
        if (
            ev.blocked_reason is not None
            or (decision_reason or "").startswith("LLM hold")
            is False  # noqa: PLR2004 — placeholder for clarity
        ):
            pass
        if (
            decision_status == AnalysisItemDecision.SKIPPED
            and decision_reason
            and decision_reason.startswith("신뢰도")
        ):
            summary.skipped_low_confidence += 1
        if ev.blocked_reason is not None:
            summary.failed += 1

    # 4) 예산 컷 (BUY only)
    try:
        budget = decrypt_decimal(run.budget_krw)
    except (ValueError, ArithmeticError):
        budget = Decimal("0")
    over_budget_count = _apply_budget_cap(items, budget)
    summary.skipped_over_budget = over_budget_count
    if over_budget_count:
        # 결정 카운트 재집계 (예산 컷으로 PENDING → SKIPPED 변경된 항목 반영)
        summary.by_decision = {}
        for it in items:
            summary.by_decision[it.decision.value] = (
                summary.by_decision.get(it.decision.value, 0) + 1
            )

    # 5) 마무리
    run.status = AnalysisRunStatus.READY
    run.completed_at = now
    run.expires_at = now + timedelta(minutes=ttl_minutes)
    summary.elapsed_seconds = time.monotonic() - started
    run.summary_json = summary.to_dict()
    return run


async def fail_run(
    db: AsyncSession,
    run_id: UUID,
    error_message: str,
) -> None:
    """오케스트레이터 외부에서 발생한 치명적 에러로 run 을 FAILED 마킹."""
    run = (
        await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        return
    run.status = AnalysisRunStatus.FAILED
    run.error_message = error_message[:1000]
    run.completed_at = datetime.now(timezone.utc)
