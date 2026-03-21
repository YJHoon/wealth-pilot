"""온보딩 라우터 — 온보딩 완료 처리"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.onboarding import OnboardingCompleteRequest, OnboardingCompleteResponse
from app.services.security_service import AccessAction, log_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["온보딩"])


@router.put("/complete", response_model=OnboardingCompleteResponse)
@limiter.limit("100/minute")
async def complete_onboarding(
    request: Request,
    body: OnboardingCompleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """온보딩 완료 처리

    면책 동의 확인 + 2FA 설정 확인 후 onboarding_completed=True 설정.
    """
    if user.onboarding_completed:
        return OnboardingCompleteResponse(
            onboarding_completed=True,
            message="이미 온보딩이 완료되었습니다.",
        )

    if not body.disclaimer_agreed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="면책 조항에 동의해야 합니다.",
        )

    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2단계 인증(2FA) 설정을 완료해야 합니다.",
        )

    user.onboarding_completed = True

    # selected_asset_types는 프론트엔드 위저드 가이드용으로만 사용되며 DB에 저장하지 않음.
    # 분석 목적으로 로그에만 기록.
    if body.selected_asset_types:
        logger.info(
            "Onboarding asset types selected: user=%s types=%s",
            user.id,
            [t.value for t in body.selected_asset_types],
        )

    await log_access(db, user.id, AccessAction.ONBOARDING_COMPLETE, request)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception("Onboarding commit failed for user %s", user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="온보딩 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
        ) from None

    return OnboardingCompleteResponse(
        onboarding_completed=True,
        message="온보딩이 완료되었습니다. 대시보드로 이동합니다.",
    )
