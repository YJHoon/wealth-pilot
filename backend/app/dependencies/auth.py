"""인증 의존성 — JWT 토큰 검증, 현재 사용자 조회"""

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.auth_service import verify_token

security = HTTPBearer(auto_error=not settings.auth_disabled)


async def _get_dev_user(db: AsyncSession) -> User:
    """개발용: DB의 첫 번째 유저 반환, 없으면 생성"""
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email="dev@wealthpilot.local",
            name="Dev User",
            totp_enabled=False,
            onboarding_completed=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """JWT Access Token으로 현재 사용자 조회

    Raises:
        HTTPException 401: 토큰 유효하지 않음
        HTTPException 403: 2FA 미설정 (totp_enabled=False)
    """
    # 개발용 인증 바이패스
    if settings.auth_disabled:
        user = await _get_dev_user(db)
        request.state.rate_limit_user_id = str(user.id)
        return user

    payload = verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 유효하지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 토큰입니다.",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    # Rate limiter에서 사용자별 제한에 활용
    request.state.rate_limit_user_id = str(user.id)

    return user


async def get_current_active_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """JWT 인증 + 2FA 검증 완료 확인

    2FA가 활성화된 계정은 반드시 이번 세션에서 OTP 검증을 마친 토큰만 허용.
    (JWT payload의 totp_verified=True 확인)

    Raises:
        HTTPException 401: 토큰 유효하지 않음
        HTTPException 403: 2FA 인증 미완료
    """
    # 개발용 인증 바이패스
    if settings.auth_disabled:
        user = await _get_dev_user(db)
        request.state.rate_limit_user_id = str(user.id)
        return user

    payload = verify_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 유효하지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 토큰입니다.",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    # 2FA 설정 완료 계정은 반드시 이번 세션에서 OTP 인증을 마쳐야 함
    if user.totp_enabled and not payload.get("totp_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="2FA 인증이 필요합니다.",
        )

    # Rate limiter에서 사용자별 제한에 활용
    request.state.rate_limit_user_id = str(user.id)

    return user
