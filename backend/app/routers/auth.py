"""인증 라우터 — 로그인, 2FA, 세션 관리"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.access_log import AccessLog
from app.models.session import Session
from app.models.user import User
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    SessionListResponse,
    SessionResponse,
    TokenResponse,
    TotpSetupResponse,
    TotpVerifyRequest,
    TotpVerifyResponse,
    UserResponse,
)
from app.services.auth_service import (
    check_account_locked,
    create_access_token,
    create_refresh_token,
    get_or_create_user,
    hash_token,
    record_login_failure,
    reset_login_failures,
    verify_google_id_token,
    verify_token,
)
from app.services.totp_service import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_qr_code,
    generate_totp_secret,
    verify_totp_code,
)

router = APIRouter(prefix="/api/auth", tags=["인증"])
_security = HTTPBearer()


# --- 로그인 ---


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Google OAuth 로그인 콜백

    NextAuth에서 Google 인증 후 ID Token + 이메일/이름을 전달받아
    토큰 검증 → 사용자 조회/생성 → JWT 발급.
    """
    # Google ID Token 서버 측 검증
    token_info = await verify_google_id_token(body.google_id_token)
    if token_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 인증 토큰이 유효하지 않습니다.",
        )

    # Google 토큰에서 검증된 이메일만 사용 (body.email 폴백 금지)
    verified_email = token_info.get("email")
    if not verified_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 토큰에 이메일 정보가 없습니다.",
        )

    user = await get_or_create_user(db, email=verified_email, name=body.name)

    # 계정 잠금 확인
    if check_account_locked(user):
        remaining = (user.locked_until - datetime.now(timezone.utc)).seconds // 60 + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"로그인 시도가 너무 많습니다. {remaining}분 후에 다시 시도해주세요.",
        )

    # 2FA 미사용 계정만 여기서 초기화.
    # TOTP 사용 계정은 /2fa/verify 성공 시점에 초기화해야 잠금 우회를 막을 수 있다.
    if not user.totp_enabled:
        await reset_login_failures(db, user)

    # 세션 생성 — IP는 서버 측에서만 결정 (클라이언트 제공 값 신뢰 금지)
    device_info = body.device_info or request.headers.get("user-agent", "Unknown")
    ip_address = request.client.host if request.client else "unknown"

    refresh_token = create_refresh_token(user.id)

    session = Session(
        user_id=user.id,
        device_info=device_info,
        ip_address=ip_address,
        refresh_token_hash=hash_token(refresh_token),  # Refresh Token 재사용 방지
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(session)
    await db.flush()  # session.id 확보

    # 액세스 로그 기록
    log = AccessLog(
        user_id=user.id,
        action="login",
        ip_address=ip_address,
        device_info=device_info,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(log)
    await db.commit()

    # 2FA 설정 완료된 계정은 totp_verified=False 토큰 발급 (OTP 검증 전)
    totp_verified = not user.totp_enabled
    access_token = create_access_token(
        user.id,
        session_id=session.id,
        totp_verified=totp_verified,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        totp_required=user.totp_enabled,
        totp_setup_required=not user.totp_enabled,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh Token으로 새 Access Token 발급 (토큰 로테이션)"""
    payload = verify_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="리프레시 토큰이 유효하지 않습니다.",
        )

    user_id = uuid.UUID(payload["sub"])

    # Refresh Token 해시로 세션 조회 (재사용 공격 방지)
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.refresh_token_hash == token_hash,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        # 유효하지 않은 Refresh Token — 탈취 가능성, 해당 사용자 세션 모두 무효화
        await db.execute(delete(Session).where(Session.user_id == user_id))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 리프레시 토큰입니다. 다시 로그인해주세요.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    # 토큰 로테이션: 새 Refresh Token 발급 + 세션 해시 업데이트
    new_refresh_token = create_refresh_token(user.id)
    session.refresh_token_hash = hash_token(new_refresh_token)
    session.last_active_at = datetime.now(timezone.utc)

    # 토큰 갱신 시 totp_verified 유지.
    # Refresh Token 자체가 2FA 검증 후 발급되었으므로 재검증 불필요.
    # 2FA 비활성 사용자도 True (검증 대상 없음).
    totp_verified = True
    new_access_token = create_access_token(
        user.id,
        session_id=session.id,
        totp_verified=totp_verified,
    )

    await db.commit()

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """현재 로그인한 사용자 정보"""
    return UserResponse.model_validate(user)


# --- 2FA (TOTP) ---


@router.post("/2fa/setup", response_model=TotpSetupResponse)
async def setup_2fa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2FA 설정 — QR 코드 생성

    이미 2FA가 설정된 경우 재설정 가능 (기존 시크릿 덮어쓰기).
    """
    secret = generate_totp_secret()

    # 시크릿을 암호화하여 DB에 임시 저장 (verify 전까지 totp_enabled=False 유지)
    user.totp_secret = encrypt_totp_secret(secret)
    await db.commit()

    qr_base64, uri = generate_qr_code(secret, user.email)

    return TotpSetupResponse(
        qr_code_base64=qr_base64,
        secret=secret,
        otpauth_uri=uri,
    )


@router.post("/2fa/verify", response_model=TotpVerifyResponse)
async def verify_2fa(
    body: TotpVerifyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2FA 코드 검증

    - 설정 중: 검증 성공 시 totp_enabled=True로 변경
    - 로그인 중: OTP 코드 검증 성공 시 totp_verified=True 토큰 발급
    """
    if user.totp_secret is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 설정을 먼저 진행해주세요.",
        )

    secret = decrypt_totp_secret(user.totp_secret)
    is_valid = verify_totp_code(secret, body.code)

    if not is_valid:
        # 2FA 검증 실패도 실패 카운트에 포함
        locked = await record_login_failure(db, user)
        if locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="인증 시도가 너무 많습니다. 15분 후에 다시 시도해주세요.",
            )
        return TotpVerifyResponse(
            verified=False,
            message="인증 코드가 올바르지 않습니다. 다시 확인해주세요.",
        )

    # 검증 성공
    await reset_login_failures(db, user)

    if not user.totp_enabled:
        user.totp_enabled = True
        await db.commit()

    # 기존 JWT에서 session_id 추출
    payload = verify_token(credentials.credentials, expected_type="access")
    session_id_str = payload.get("sid") if payload else None
    session_id = uuid.UUID(session_id_str) if session_id_str else None

    # totp_verified=True 토큰 발급 (이제부터 보호된 API 접근 가능)
    new_access_token = create_access_token(
        user.id,
        session_id=session_id,
        totp_verified=True,
    )

    return TotpVerifyResponse(
        verified=True,
        message="2FA 인증이 완료되었습니다.",
        access_token=new_access_token,
    )


# --- 세션 관리 ---


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """활성 세션 목록 조회"""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user.id, Session.expires_at > now)
        .order_by(Session.last_active_at.desc())
    )
    sessions = result.scalars().all()

    return SessionListResponse(
        sessions=[SessionResponse.model_validate(s) for s in sessions],
        total=len(sessions),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """세션 원격 종료 (본인 세션만)"""
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션을 찾을 수 없습니다.",
        )

    await db.delete(session)

    # 요청자의 실제 IP 기록
    ip_address = request.client.host if request.client else "0.0.0.0"
    log = AccessLog(
        user_id=user.id,
        action="session_revoke",
        ip_address=ip_address,
        device_info=f"revoked session: {session_id}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(log)
    await db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """로그아웃 — JWT의 session_id로 특정 세션 삭제"""
    ip_address = request.client.host if request.client else "0.0.0.0"
    device_info = request.headers.get("user-agent", "Unknown")

    # JWT에서 session_id 추출하여 해당 세션만 정확히 삭제
    payload = verify_token(credentials.credentials, expected_type="access")
    session_id_str = payload.get("sid") if payload else None

    if session_id_str:
        await db.execute(
            delete(Session).where(
                Session.id == uuid.UUID(session_id_str),
                Session.user_id == user.id,  # 소유권 확인
            )
        )
    else:
        # fallback: session_id 없는 구버전 토큰 — device_info 기반 삭제
        result = await db.execute(
            select(Session).where(
                Session.user_id == user.id,
                Session.device_info == device_info,
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            await db.delete(s)

    # 액세스 로그
    log = AccessLog(
        user_id=user.id,
        action="logout",
        ip_address=ip_address,
        device_info=device_info,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(log)
    await db.commit()
