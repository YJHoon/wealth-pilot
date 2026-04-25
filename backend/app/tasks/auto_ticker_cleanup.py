"""자동 종목 선정 이력 정리 크론.

전략당 최신 N건만 남기고 나머지를 삭제. 매일 03:00 KST에 실행.

PostgreSQL window function으로 row_number 매겨 N건 초과 행 삭제.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.sql import func

from app.database import AsyncSessionLocal
from app.models.trading import AutoTickerSelection

logger = logging.getLogger(__name__)

KEEP_PER_STRATEGY = 30


async def cleanup_auto_ticker_history(keep_per_strategy: int = KEEP_PER_STRATEGY) -> int:
    """전략당 최신 keep_per_strategy 건만 유지. 삭제 행 수 반환."""
    ranked = (
        select(
            AutoTickerSelection.id.label("id"),
            func.row_number()
            .over(
                partition_by=AutoTickerSelection.strategy_id,
                order_by=AutoTickerSelection.generated_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    stale_ids = select(ranked.c.id).where(ranked.c.rn > keep_per_strategy)
    stmt = delete(AutoTickerSelection).where(AutoTickerSelection.id.in_(stale_ids))

    async with AsyncSessionLocal() as db:
        result = await db.execute(stmt)
        await db.commit()
        deleted = result.rowcount or 0
        logger.info(
            "Auto ticker history cleanup: deleted=%d (keep=%d per strategy)",
            deleted, keep_per_strategy,
        )
        return deleted
