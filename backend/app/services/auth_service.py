"""인증 서비스 — JWT 토큰 생성/검증, 로그인 실패 추적"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
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
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)  # type: ignore[arg-type]


def create_refresh_token(user_id: uuid.UUID, totp_verified: bool = False) -> str:
    """Refresh Token 생성 (7일 만료)

    Args:
        totp_verified: 2FA 검증 완료 여부 — /refresh에서 access token으로 전달됨
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),   # 토큰 고유 ID (동시 발급 토큰 구별)
        "totp_verified": totp_verified,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)  # type: ignore[arg-type]


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
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])  # type: ignore[arg-type]
        if payload.get("type") != expected_type:
            return None
        return payload
    except InvalidTokenError:
        return None


async def get_or_create_user(
    db: AsyncSession,
    email: str,
    name: str,
) -> User:
    """Google OAuth 로그인 후 사용자 조회 또는 생성

    동시 요청으로 인한 IntegrityError(unique 위반) 발생 시 재조회하여 안전하게 처리.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, name=name)
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            # 동시 요청으로 이미 생성된 경우 — 롤백 후 재조회
            await db.rollback()
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one()

    return user


def check_account_locked(user: User) -> bool:
    """계정 잠금 상태 확인 (I/O 없음 → 동기 함수)"""
    if user.locked_until is None:
        return False
    if user.locked_until > datetime.now(timezone.utc):
        return True
    return False


async def record_login_failure(db: AsyncSession, user: User) -> bool:
    """로그인 실패 기록. 5회 도달 시 15분 잠금. 잠금되었으면 True 반환.

    SELECT FOR UPDATE로 행 잠금 → 카운터 증가 + 잠금 설정을 단일 트랜잭션으로 처리.
    동시 요청에서 카운터 증가분 손실 및 잠금 우회를 방지.
    """
    now = datetime.now(timezone.utc)
    lock_duration = timedelta(minutes=15)

    # 행 잠금: 동시 요청이 동일 행을 동시에 수정하지 못하도록 직렬화
    result = await db.execute(select(User).where(User.id == user.id).with_for_update())
    current = result.scalar_one()

    # 만료된 잠금이면 카운터 초기화
    if current.locked_until is not None and current.locked_until <= now:
        current.failed_login_count = 0
        current.locked_until = None

    current.failed_login_count += 1

    is_locked = False
    if current.failed_login_count >= 5:
        current.locked_until = now + lock_duration
        is_locked = True

    await db.commit()

    # 호출자 객체도 최신 상태로 갱신
    user.failed_login_count = current.failed_login_count
    user.locked_until = current.locked_until

    return is_locked


async def reset_login_failures(db: AsyncSession, user: User) -> None:
    """로그인 성공 시 실패 카운트 초기화"""
    if user.failed_login_count > 0 or user.locked_until is not None:
        user.failed_login_count = 0
        user.locked_until = None
        await db.commit()
