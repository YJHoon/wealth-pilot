"""인증 서비스 — JWT 토큰 생성/검증, 로그인 실패 추적"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User


def hash_token(token: str) -> str:
    """토큰을 SHA-256으로 해시 (DB 저장용)"""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    user_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    totp_verified: bool = False,
) -> str:
    """Access Token 생성 (15분 만료)

    Args:
        session_id: 세션 ID (로그아웃 시 특정 세션 삭제에 사용)
        totp_verified: 2FA 검증 완료 여부
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
        "totp_verified": totp_verified,
    }
    if session_id:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Refresh Token 생성 (7일 만료)"""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def verify_google_id_token(token: str) -> dict | None:
    """Google ID Token 검증

    Google tokeninfo 엔드포인트로 토큰 유효성 확인 및 aud(client_id) 검증.
    Returns:
        검증된 payload 또는 None (실패 시)
    """
    if not settings.google_client_id:
        # GOOGLE_CLIENT_ID 미설정 시 인증 거부 (fail-closed 원칙)
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": token},
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # audience(클라이언트 ID) 검증
        if data.get("aud") != settings.google_client_id:
            return None
        return data
    except Exception:
        return None


def verify_token(token: str, expected_type: str = "access") -> dict | None:
    """토큰 검증. 유효하면 payload 반환, 아니면 None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


async def get_or_create_user(
    db: AsyncSession,
    email: str,
    name: str,
) -> User:
    """Google OAuth 로그인 후 사용자 조회 또는 생성"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, name=name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


def check_account_locked(user: User) -> bool:
    """계정 잠금 상태 확인 (I/O 없음 → 동기 함수)"""
    if user.locked_until is None:
        return False
    if user.locked_until > datetime.now(timezone.utc):
        return True
    return False


async def record_login_failure(db: AsyncSession, user: User) -> bool:
    """로그인 실패 기록. 5회 도달 시 15분 잠금. 잠금되었으면 True 반환."""
    user.failed_login_count += 1
    locked = False

    if user.failed_login_count >= 5:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        locked = True

    await db.commit()
    return locked


async def reset_login_failures(db: AsyncSession, user: User) -> None:
    """로그인 성공 시 실패 카운트 초기화"""
    if user.failed_login_count > 0 or user.locked_until is not None:
        user.failed_login_count = 0
        user.locked_until = None
        await db.commit()
