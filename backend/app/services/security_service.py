"""보안 서비스 — 액세스 로그 헬퍼 + 비정상 접근 탐지"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_log import AccessLog
from app.services.alert_service import send_security_alert

logger = logging.getLogger(__name__)


class AccessAction:
    """액세스 로그 액션 상수"""

    LOGIN = "login"
    LOGIN_CHALLENGE = "login_challenge"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_REVOKE = "session_revoke"
    ASSET_CREATE = "asset_create"
    ASSET_UPDATE = "asset_update"
    ASSET_DELETE = "asset_delete"
    ASSET_SELL = "asset_sell"
    TOTP_SETUP = "totp_setup"
    TOTP_VERIFY = "totp_verify"


async def log_access(
    db: AsyncSession,
    user_id,
    action: str,
    request: Request,
    *,
    is_suspicious: bool = False,
    device_info_override: str | None = None,
) -> AccessLog:
    """AccessLog 생성 — IP/User-Agent 자동 추출, expires_at +365일 자동 계산."""
    ip_address = request.client.host if request.client else "unknown"
    device_info = device_info_override or request.headers.get("user-agent", "Unknown")

    log = AccessLog(
        user_id=user_id,
        action=action,
        ip_address=ip_address,
        device_info=device_info,
        is_suspicious=is_suspicious,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(log)
    return log


async def check_new_device(
    db: AsyncSession, user_id, ip: str, device_info: str
) -> bool:
    """과거 로그인 기록에서 IP+device 조합이 처음이면 True."""
    login_actions = (AccessAction.LOGIN, AccessAction.LOGIN_CHALLENGE)
    result = await db.execute(
        select(func.count())
        .select_from(AccessLog)
        .where(
            AccessLog.user_id == user_id,
            AccessLog.action.in_(login_actions),
            AccessLog.ip_address == ip,
            AccessLog.device_info == device_info,
        )
    )
    count = result.scalar_one()
    return count == 0


async def check_rapid_login_attempts(db: AsyncSession, user_id) -> bool:
    """5분 내 로그인 관련 액션이 3회 이상이면 True."""
    five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    login_actions = (
        AccessAction.LOGIN,
        AccessAction.LOGIN_CHALLENGE,
        AccessAction.LOGIN_FAILURE,
    )
    result = await db.execute(
        select(func.count())
        .select_from(AccessLog)
        .where(
            AccessLog.user_id == user_id,
            AccessLog.action.in_(login_actions),
            AccessLog.created_at >= five_minutes_ago,
        )
    )
    count = result.scalar_one()
    return count >= 3


async def detect_anomalies(
    db: AsyncSession, user_id, user_email: str, request: Request
) -> bool:
    """비정상 접근 탐지 — 새 기기 / 빠른 반복 로그인 시 텔레그램 알림 발송."""
    ip = request.client.host if request.client else "unknown"
    device = request.headers.get("user-agent", "Unknown")
    detected = False

    try:
        is_new = await check_new_device(db, user_id, ip, device)
        if is_new:
            detected = True
            await send_security_alert("new_device_login", user_email, ip, device)

        is_rapid = await check_rapid_login_attempts(db, user_id)
        if is_rapid:
            detected = True
            await send_security_alert("repeated_login_failures", user_email, ip, device)
    except Exception:
        logger.exception("Anomaly detection failed")

    return detected
