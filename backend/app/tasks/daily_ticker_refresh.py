"""일일 자동 종목 갱신 크론 (08:30 KST).

`auto_select_config.enabled=True` 인 활성 전략 전체에 대해 `schedule`
트리거로 `select_and_persist` 를 호출한다. 시드 기준값은 전략의
`initial_capital` 을 사용한다 — 시장 변동과 무관하게 안정적이며, 실제
발주 시점의 현금 기준 검증은 trading_cycle 에서 재확인된다.

실패한 전략은 스킵하고 다음 전략으로 진행 (fail-open).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.trading import TradingStrategy
from app.services.auto_ticker_service import is_enabled, select_and_persist
from app.services.strategy_capital import get_initial_capital
from app.services.ticker_selector import UniverseLoader, load_universe

logger = logging.getLogger(__name__)


async def execute_daily_ticker_refresh(
    loader: UniverseLoader = load_universe,
) -> None:
    """auto_select 활성 전략의 종목 리스트를 일 1회 갱신."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TradingStrategy).where(
                TradingStrategy.is_active.is_(True),
            )
        )
        strategies = result.scalars().all()

        total = 0
        refreshed = 0
        errors = 0
        for strategy in strategies:
            if not is_enabled(strategy):
                continue
            total += 1
            try:
                seed = get_initial_capital(strategy)
                if seed <= 0:
                    seed = Decimal("1000000")  # 안전 기본값 — 시드 0인 전략 방지
                await select_and_persist(
                    db,
                    strategy,
                    available_cash=seed,
                    total_eval=seed,
                    triggered_by="schedule",
                    loader=loader,
                )
                refreshed += 1
            except Exception:
                errors += 1
                logger.exception(
                    "Daily ticker refresh failed for strategy=%s", strategy.id,
                )
        await db.commit()
        logger.info(
            "Daily ticker refresh complete: eligible=%d refreshed=%d errors=%d",
            total, refreshed, errors,
        )
