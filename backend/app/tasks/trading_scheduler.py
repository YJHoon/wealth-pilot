"""매매 스케줄러 — APScheduler 기반 크론 관리

FastAPI lifespan에서 setup/shutdown 호출.
DB에서 is_scheduled=True인 전략을 로드하여 크론 잡 등록.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.trading import TradingStrategy

logger = logging.getLogger(__name__)


def _job_id(user_id: UUID, strategy_id: UUID) -> str:
    return f"trading:{user_id}:{strategy_id}"


class TradingScheduler:
    """매매 스케줄 관리자 — 싱글톤."""

    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None

    @property
    def is_running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    async def setup(self):
        """스케줄러 초기화 + DB에서 활성 스케줄 복원."""
        self._scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        self._scheduler.start()
        logger.info("Trading scheduler started")

        await self._restore_schedules()

        # 계좌 락 레지스트리 주기 정리 (시간당 1회)
        from app.services.account_lock import prune_idle_account_locks
        self._scheduler.add_job(
            prune_idle_account_locks,
            trigger=IntervalTrigger(hours=1),
            id="account_lock_prune",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Stage 3 Step 4: 주간 메타 분석 (매주 일요일 20:00 KST)
        from app.tasks.meta_analysis import execute_weekly_meta_analysis
        self._scheduler.add_job(
            execute_weekly_meta_analysis,
            trigger=CronTrigger(day_of_week="sun", hour=20, minute=0),
            id="weekly_meta_analysis",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    async def shutdown(self):
        """스케줄러 종료."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Trading scheduler stopped")

    async def _restore_schedules(self):
        """DB에서 is_scheduled=True인 전략을 로드하여 크론 재등록."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(TradingStrategy).where(
                        TradingStrategy.is_scheduled.is_(True),
                        TradingStrategy.is_active.is_(True),
                    )
                )
                strategies = result.scalars().all()

                for strategy in strategies:
                    self._add_job(strategy.user_id, strategy.id, strategy.interval_minutes)

                if strategies:
                    logger.info("Restored %d trading schedules", len(strategies))
        except Exception:
            logger.exception("Failed to restore trading schedules")

    def add_schedule(self, user_id: UUID, strategy_id: UUID, interval_minutes: int):
        """크론 잡 등록."""
        self._add_job(user_id, strategy_id, interval_minutes)
        logger.info(
            "Schedule added: user=%s, strategy=%s, interval=%dm",
            user_id, strategy_id, interval_minutes,
        )

    def remove_schedule(self, user_id: UUID, strategy_id: UUID):
        """크론 잡 해제."""
        job_id = _job_id(user_id, strategy_id)
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Schedule removed: user=%s, strategy=%s", user_id, strategy_id)

    def get_next_run_time(self, user_id: UUID, strategy_id: UUID) -> datetime | None:
        """다음 실행 시각 반환."""
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(_job_id(user_id, strategy_id))
        if job is None:
            return None
        return job.next_run_time

    def has_schedule(self, user_id: UUID, strategy_id: UUID) -> bool:
        """스케줄 존재 여부."""
        if not self._scheduler:
            return False
        return self._scheduler.get_job(_job_id(user_id, strategy_id)) is not None

    def _add_job(self, user_id: UUID, strategy_id: UUID, interval_minutes: int):
        """내부: IntervalTrigger로 잡 등록."""
        if not self._scheduler:
            logger.warning("Scheduler not initialized, skipping job add")
            return

        job_id = _job_id(user_id, strategy_id)

        # 이미 등록된 잡이 있으면 교체
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        # 지연 임포트: 순환 참조 방지
        from app.tasks.trading_cycle import execute_trading_cycle

        self._scheduler.add_job(
            execute_trading_cycle,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            args=[str(user_id), str(strategy_id)],
            name=f"Trading cycle for strategy {strategy_id}",
            replace_existing=True,
            max_instances=1,  # 이전 실행이 끝나지 않았으면 스킵
        )


# 싱글톤
trading_scheduler = TradingScheduler()
