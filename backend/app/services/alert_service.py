"""텔레그램 알림 서비스 — 보안 알림 전송"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# 알림 포맷 템플릿
_ALERT_TEMPLATES = {
    "new_device_login": "🔐 [새 기기 로그인]\n사용자: {user_email}\nIP: {ip}\n기기: {device}",
    "suspicious_access": "⚠️ [비정상 접근 감지]\n사용자: {user_email}\nIP: {ip}\n기기: {device}",
    "repeated_login_failures": "🚨 [반복 로그인 실패]\n사용자: {user_email}\nIP: {ip}\n기기: {device}",
}


async def send_telegram_message(message: str) -> bool:
    """텔레그램 메시지 전송. 토큰 미설정 시 skip."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("Telegram credentials not configured, skipping alert")
        return False

    url = TELEGRAM_API_URL.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception:
        logger.exception("Failed to send Telegram alert")
        return False


async def send_security_alert(
    alert_type: str, user_email: str, ip: str, device: str
) -> bool:
    """보안 알림 포맷팅 후 텔레그램 전송."""
    template = _ALERT_TEMPLATES.get(alert_type)
    if template is None:
        logger.warning("Unknown alert type: %s", alert_type)
        return False

    message = template.format(user_email=user_email, ip=ip, device=device)
    return await send_telegram_message(message)
