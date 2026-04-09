"""LLM 어드바이저 — 모듈 B: 의사결정 메모리 컨텍스트

매 사이클 LLM 호출 직전에 같은 전략의 최근 의사결정 이력과 간단한 집계를
조회해 프롬프트에 주입한다. "기억상실증 트레이더"가 같은 실수를 반복하지
않도록 하는 단기 학습 장치.

결과(realized_pnl/exit_price 등)의 백필은 별도 작업(모듈 B 후속)에서 다룬다.
이 모듈은 *읽기 전용*이며 DB 쓰기를 수행하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import TradingDecision

# 프롬프트에 실어 보내는 최근 결정 개수 (토큰 절약 + 신호 노이즈 균형)
DEFAULT_RECENT_LIMIT = 20
# 집계 통계 윈도우 (일)
SUMMARY_WINDOW_DAYS = 30


@dataclass
class DecisionMemory:
    """LLM 프롬프트에 주입할 의사결정 메모리.

    Attributes:
        recent: 최신순으로 정렬된 최근 N건의 의사결정 dict 리스트.
                각 항목: {created_at, ticker, action, confidence, executed,
                          blocked_reason, reason}
        summary: 한국어 한 줄 집계 ("최근 30일: 총 N건, 발주 X건, hold Y건, ...").
                 데이터가 없으면 None.
    """

    recent: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.recent and self.summary is None


async def load_decision_memory(
    db: AsyncSession,
    strategy_id: UUID,
    limit: int = DEFAULT_RECENT_LIMIT,
) -> DecisionMemory:
    """전략별 최근 의사결정 + 집계를 조회.

    Args:
        db: 비동기 세션
        strategy_id: 대상 전략
        limit: 최근 결정 최대 개수
    """
    # 1. 최근 N건 (최신순)
    stmt = (
        select(TradingDecision)
        .where(TradingDecision.strategy_id == strategy_id)
        .order_by(TradingDecision.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    recent: list[dict[str, Any]] = []
    for r in rows:
        recent.append({
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "ticker": r.ticker,
            "action": r.action,
            "confidence": r.confidence,
            "executed": r.executed,
            "blocked_reason": r.blocked_reason,
            "reason": (r.reason or "")[:200],
        })

    # 2. 최근 30일 집계 — action별 카운트 + 발주 카운트
    # Boolean sum이 dialect-specific해서 두 쿼리로 분리(가독성·이식성↑).
    window_start = datetime.now(timezone.utc) - timedelta(days=SUMMARY_WINDOW_DAYS)
    by_action_stmt = (
        select(TradingDecision.action, func.count())
        .where(
            TradingDecision.strategy_id == strategy_id,
            TradingDecision.created_at >= window_start,
        )
        .group_by(TradingDecision.action)
    )
    by_action = dict((await db.execute(by_action_stmt)).all())

    executed_stmt = (
        select(func.count())
        .where(
            TradingDecision.strategy_id == strategy_id,
            TradingDecision.created_at >= window_start,
            TradingDecision.executed.is_(True),
        )
    )
    executed_count = (await db.execute(executed_stmt)).scalar() or 0

    total = sum(by_action.values())
    summary: str | None = None
    if total > 0:
        buy_n = by_action.get("buy", 0)
        sell_n = by_action.get("sell", 0)
        hold_n = by_action.get("hold", 0)
        summary = (
            f"최근 {SUMMARY_WINDOW_DAYS}일: 총 {total}건 의사결정 "
            f"(buy {buy_n} / sell {sell_n} / hold {hold_n}), "
            f"실제 발주 {executed_count}건"
        )

    return DecisionMemory(recent=recent, summary=summary)
