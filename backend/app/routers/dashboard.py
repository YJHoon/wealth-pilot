"""대시보드 라우터 — 요약, 히스토리, 스냅샷"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.schemas.dashboard import (
    DashboardHistoryResponse,
    DashboardSummaryResponse,
    HistoryPeriod,
    SnapshotResponse,
)
from app.services.crypto_service import decrypt_decimal
from app.services.dashboard_service import (
    create_snapshot,
    get_dashboard_history,
    get_dashboard_summary,
)
from app.services.security_service import AccessAction, log_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["대시보드"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """대시보드 요약 — 총 자산, 유형별/그룹별 비중, 손익, 전일 대비 변동."""
    summary = await get_dashboard_summary(db, user.id)

    try:
        await log_access(db, user.id, AccessAction.DASHBOARD_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning(
            "DASHBOARD_VIEW access logging failed",
            exc_info=True,
            extra={"user_id": str(user.id)},
        )

    return DashboardSummaryResponse(**summary)


@router.get("/history", response_model=DashboardHistoryResponse)
async def dashboard_history(
    request: Request,
    period: HistoryPeriod = Query(default=HistoryPeriod.ONE_MONTH),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """기간별 자산 추이 데이터 (asset_snapshots 기반)."""
    data_points = await get_dashboard_history(db, user.id, period.value)

    return DashboardHistoryResponse(
        period=period.value,
        data_points=data_points,
        total_count=len(data_points),
    )


@router.post("/snapshot", response_model=SnapshotResponse)
async def create_dashboard_snapshot(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 자산 상태를 스냅샷으로 저장 (암호화).

    - 같은 날짜에 이미 있으면 업데이트
    - expires_at = created_at + 1년
    """
    snapshot = await create_snapshot(db, user.id)

    try:
        await log_access(db, user.id, AccessAction.SNAPSHOT_CREATE, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning(
            "SNAPSHOT_CREATE access logging failed",
            exc_info=True,
            extra={"user_id": str(user.id)},
        )

    return SnapshotResponse(
        id=str(snapshot.id),
        snapshot_date=snapshot.snapshot_date.isoformat(),
        total_value_krw=decrypt_decimal(snapshot.total_value_krw),
        breakdown=snapshot.breakdown,
        created_at=snapshot.created_at,
    )
