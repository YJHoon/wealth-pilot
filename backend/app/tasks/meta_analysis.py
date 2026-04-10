"""주간 메타 분석 태스크 — APScheduler에서 매주 일요일 실행

모든 활성 LLM_ADVISOR 전략을 순회하며 run_weekly_meta_analysis를 호출한다.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.trading import StrategyType, TradingStrategy
from app.services.adaptive_rules import run_weekly_meta_analysis
from app.services.alert_service import send_telegram_message

logger = logging.getLogger(__name__)


async def execute_weekly_meta_analysis():
    """모든 활성 LLM_ADVISOR 전략에 대해 주간 메타 분석 실행.

    APScheduler CronTrigger에 의해 매주 일요일 20:00 KST에 호출된다.
    """
    async with AsyncSessionLocal() as db:
        try:
            stmt = (
                select(TradingStrategy)
                .where(
                    TradingStrategy.strategy_type == StrategyType.LLM_ADVISOR,
                    TradingStrategy.is_active.is_(True),
                )
            )
            strategies = list((await db.execute(stmt)).scalars().all())

            if not strategies:
                logger.info("Weekly meta-analysis: no active LLM_ADVISOR strategies")
                return

            total_rules = 0
            errors = 0

            for strategy in strategies:
                try:
                    created = await run_weekly_meta_analysis(db, strategy)
                    total_rules += len(created)
                    await db.commit()
                except Exception:
                    logger.exception(
                        "Meta-analysis failed for strategy=%s", strategy.id,
                    )
                    await db.rollback()
                    errors += 1

            logger.info(
                "Weekly meta-analysis completed: strategies=%d rules=%d errors=%d",
                len(strategies), total_rules, errors,
            )

            if errors > 0:
                try:
                    await send_telegram_message(
                        f"⚠️ [주간 메타 분석 일부 실패]\n"
                        f"전략 {len(strategies)}개 중 {errors}개 실패\n"
                        f"생성된 규칙: {total_rules}건"
                    )
                except Exception:
                    logger.exception("Failed to send meta-analysis error alert")

        except Exception:
            logger.exception("Weekly meta-analysis job failed")
