"""인증 라우터 — 로그인, 2FA, 세션 관리"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.middleware.rate_limit import limiter
from app.models.session import Session
from app.models.user import User
from app.services.security_service import AccessAction, detect_anomalies, log_access
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
@limiter.limit("10/minute")
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
        await log_access(db, user.id, AccessAction.LOGIN_FAILURE, request, is_suspicious=True)
        await detect_anomalies(db, user.id, user.email, request)
        await db.commit()
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

    # 2FA 사용자: totp_verified=False (OTP 검증 전), 비사용자: True
    # 리프레시 토큰에 totp_verified 포함 → /refresh에서 2FA 우회 불가
    refresh_token = create_refresh_token(user.id, totp_verified=not user.totp_enabled)

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
    # 2FA 사용자는 OTP 검증 전이므로 login_challenge 로그, 완료 후 login 로그는 /2fa/verify에서 기록
    action = AccessAction.LOGIN_CHALLENGE if user.totp_enabled else AccessAction.LOGIN
    await log_access(db, user.id, action, request, device_info_override=device_info)

    # 비정상 접근 탐지 (새 기기, 빠른 반복 로그인 등)
    await detect_anomalies(db, user.id, user.email, request, device_info=device_info)

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
    now = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    # 리프레시 토큰의 totp_verified 클레임 유지 (2FA 우회 방지)
    prior_totp_verified = bool(payload.get("totp_verified", False))
    totp_verified = prior_totp_verified or not user.totp_enabled

    # 새 토큰 미리 생성 (CAS UPDATE에 사용)
    new_refresh_token = create_refresh_token(user.id, totp_verified=totp_verified)
    old_hash = hash_token(body.refresh_token)
    new_hash = hash_token(new_refresh_token)

    # CAS(compare-and-swap) 방식 토큰 로테이션:
    # old hash가 일치하는 세션만 원자적으로 갱신 → 동시 요청 레이스 컨디션 방지.
    # SELECT + UPDATE 2단계 대신 단일 UPDATE WHERE로 처리하므로 TOCTOU 없음.
    result = await db.execute(
        update(Session)
        .where(
            Session.user_id == user_id,
            Session.refresh_token_hash == old_hash,
            Session.expires_at > now,
        )
        .values(
            refresh_token_hash=new_hash,
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
        .returning(Session.id)
    )
    row = result.one_or_none()

    if row is None:
        # hash miss: 이미 다른 요청에서 갱신되었거나 세션 만료/탈취
        # 즉시 전체 세션 폐기 대신 401 반환 (정상 동시 요청 오탐 방지)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 리프레시 토큰입니다. 다시 로그인해주세요.",
        )

    await db.commit()

    session_id = row[0]
    new_access_token = create_access_token(
        user.id,
        session_id=session_id,
        totp_verified=totp_verified,
    )

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
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2FA 설정 — QR 코드 생성

    이미 2FA가 활성화된 경우: 기존 OTP 검증(totp_verified=True)이 완료된 세션에서만 재설정 허용.
    기존 시크릿은 유지하고 pending_totp_secret에 임시 저장.
    /2fa/verify 성공 시점에 실제 시크릿으로 교체 (설정 중 기존 2FA 유지).
    """
    secret = generate_totp_secret()
    encrypted = encrypt_totp_secret(secret)

    if user.totp_enabled:
        # 재설정: 현재 OTP 검증 완료 여부 확인 (탈취된 1차 토큰으로 OTP 교체 방지)
        payload = verify_token(credentials.credentials, expected_type="access")
        if not payload or not payload.get("totp_verified", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA 재설정을 위해 현재 OTP 인증이 필요합니다.",
            )
        # 기존 시크릿(활성)을 유지하고 새 시크릿은 pending에 임시 저장
        user.pending_totp_secret = encrypted
    else:
        # 최초 설정: totp_secret에 직접 저장 (아직 totp_enabled=False)
        user.totp_secret = encrypted
    await db.commit()

    qr_base64, uri = generate_qr_code(secret, user.email)

    return TotpSetupResponse(
        qr_code_base64=qr_base64,
        secret=secret,
        otpauth_uri=uri,
    )


@router.post("/2fa/verify", response_model=TotpVerifyResponse)
async def verify_2fa(
    request: Request,
    body: TotpVerifyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2FA 코드 검증

    - 최초 설정 완료: totp_enabled=True로 변경
    - 2FA 재설정 완료: pending_totp_secret → totp_secret으로 교체
    - 로그인 중: OTP 코드 검증 성공 시 totp_verified=True 토큰 발급
    """
    # 계정 잠금 확인 (잠금 상태에서 OTP를 맞혀도 잠금 해제 불가)
    if check_account_locked(user):
        remaining = (user.locked_until - datetime.now(timezone.utc)).seconds // 60 + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"인증 시도가 너무 많습니다. {remaining}분 후에 다시 시도해주세요.",
        )

    # 검증 대상 시크릿 결정: pending(재설정 중) → totp_secret(활성) 순서
    active_secret_field = user.pending_totp_secret or user.totp_secret
    if active_secret_field is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 설정을 먼저 진행해주세요.",
        )

    secret = decrypt_totp_secret(active_secret_field)
    is_valid = verify_totp_code(secret, body.code)

    if not is_valid:
        locked = await record_login_failure(db, user)
        await log_access(db, user.id, AccessAction.LOGIN_FAILURE, request, is_suspicious=True)
        await detect_anomalies(db, user.id, user.email, request)
        await db.commit()
        if locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="인증 시도가 너무 많습니다. 15분 후에 다시 시도해주세요.",
            )
        return TotpVerifyResponse(
            verified=False,
            message="인증 코드가 올바르지 않습니다. 다시 확인해주세요.",
        )

    # 검증 성공 — 실패 카운터 초기화
    await reset_login_failures(db, user)

    if user.pending_totp_secret:
        # 재설정 완료: pending → 활성 시크릿으로 교체
        user.totp_secret = user.pending_totp_secret
        user.pending_totp_secret = None
        user.totp_enabled = True
    elif not user.totp_enabled:
        # 최초 설정 완료
        user.totp_enabled = True

    # 기존 JWT에서 session_id 추출
    payload = verify_token(credentials.credentials, expected_type="access")
    session_id_str = payload.get("sid") if payload else None
    session_id = uuid.UUID(session_id_str) if session_id_str else None

    # Refresh Token 로테이션: totp_verified=True로 갱신 (2FA 우회 방지)
    new_refresh_token: str | None = None
    if session_id:
        result = await db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user.id)
        )
        session_obj = result.scalar_one_or_none()
        if session_obj:
            new_refresh_token = create_refresh_token(user.id, totp_verified=True)
            session_obj.refresh_token_hash = hash_token(new_refresh_token)
            session_obj.last_active_at = datetime.now(timezone.utc)
            # 세션 만료 시각 갱신 (새 refresh token TTL과 동기화)
            session_obj.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # 2FA 최종 로그인 감사 로그 기록
    await log_access(db, user.id, AccessAction.LOGIN, request)

    # 비정상 접근 탐지
    await detect_anomalies(db, user.id, user.email, request)

    await db.commit()

    new_access_token = create_access_token(
        user.id,
        session_id=session_id,
        totp_verified=True,
    )

    return TotpVerifyResponse(
        verified=True,
        message="2FA 인증이 완료되었습니다.",
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


# --- 세션 관리 ---


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """활성 세션 목록 조회"""
    # 현재 요청의 JWT에서 session_id 추출 → is_current 표시에 사용
    payload = verify_token(credentials.credentials, expected_type="access")
    current_sid_str = payload.get("sid") if payload else None
    current_session_id = uuid.UUID(current_sid_str) if current_sid_str else None

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user.id, Session.expires_at > now)
        .order_by(Session.last_active_at.desc())
    )
    sessions = result.scalars().all()

    def to_response(s: Session) -> SessionResponse:
        data = SessionResponse.model_validate(s)
        data.is_current = (current_session_id is not None and s.id == current_session_id)
        return data

    return SessionListResponse(
        sessions=[to_response(s) for s in sessions],
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

    # 액세스 로그 기록
    await log_access(
        db, user.id, AccessAction.SESSION_REVOKE, request,
        device_info_override=f"revoked session: {session_id}",
    )
    await db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """로그아웃 — JWT의 session_id로 특정 세션 삭제"""
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
    await log_access(db, user.id, AccessAction.LOGOUT, request)
    await db.commit()
