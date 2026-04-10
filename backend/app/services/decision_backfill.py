"""TradingDecision 결과 백필

매도 발생 시 해당 종목의 미완결 buy decision에 realized_pnl, holding_days,
exit_price를 기록한다. 모듈 B(메모리 컨텍스트)와 모듈 C(메타 분석)가
"이 판단이 결국 수익이었나 손실이었나"를 학습하기 위한 데이터.

호출 지점: trading_cycle.py의 매도 성공 직후 (손절/시그널 매도 공통).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import TradingDecision
from app.services.crypto_service import encrypt_decimal

logger = logging.getLogger(__name__)


async def backfill_sell_results(
    db: AsyncSession,
    strategy_id: UUID,
    ticker: str,
    exit_price: Decimal,
    realized_pnl: Decimal,
) -> int:
    """매도 시 해당 종목의 미완결 buy decision에 결과를 백필.

    대상: 같은 전략/종목에서 executed=True, action='buy', exit_price IS NULL인
    가장 오래된 decision부터 채운다 (FIFO).

    전량 매도를 가정하므로 미완결 buy가 여러 건이면 모두 동일한
    exit_price/realized_pnl를 기록한다. 부분 매도 세분화는 추후 확장.

    Returns:
        백필된 decision 건수
    """
    stmt = (
        select(TradingDecision)
        .where(
            TradingDecision.strategy_id == strategy_id,
            TradingDecision.ticker == ticker,
            TradingDecision.action == "buy",
            TradingDecision.executed.is_(True),
            TradingDecision.exit_price.is_(None),
        )
        .order_by(TradingDecision.created_at.asc())
    )
    result = await db.execute(stmt)
    decisions = result.scalars().all()

    if not decisions:
        return 0

    now = datetime.now(timezone.utc)
    encrypted_exit = encrypt_decimal(exit_price)
    encrypted_pnl = encrypt_decimal(realized_pnl)
    count = 0

    for d in decisions:
        d.exit_price = encrypted_exit
        d.realized_pnl = encrypted_pnl
        d.holding_days = (now - d.created_at).days if d.created_at else None
        count += 1

    logger.info(
        "Backfilled %d buy decision(s): strategy=%s ticker=%s exit_price=%s pnl=%s",
        count, strategy_id, ticker, exit_price, realized_pnl,
    )
    return count
