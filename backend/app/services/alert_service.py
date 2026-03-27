"""텔레그램 알림 서비스 — 보안 알림 전송"""

import logging
from html import escape

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

# 매매 알림 (send_telegram_message로 직접 전송하는 형태)
TRADING_ALERT_TEMPLATES = {
    "trade_executed": "📈 [매매 체결] {side} {ticker} {qty}주 @ {price}원",
    "bot_started": "🤖 [자동매매 스케줄 시작] 전략: {strategy}, 모드: {mode}",
    "bot_stopped": "🛑 [자동매매 스케줄 중지] 전략: {strategy}",
    "stop_loss": "🚨 [손절 발동] {ticker} 손실: {loss}원",
    "daily_limit": "⛔ [일일 손실 한도 도달] 오늘 손실: {loss}원",
    "cycle_error": "❌ [매매 사이클 오류] {error}",
}

# 관심종목 알림
WATCHLIST_ALERT_TEMPLATES = {
    "target_buy_reached": "📉 [목표 매수가 도달] {ticker}({market}) 현재가 {current_price}원 ≤ 목표 {target_price}원",
    "target_sell_reached": "📈 [목표 매도가 도달] {ticker}({market}) 현재가 {current_price}원 ≥ 목표 {target_price}원",
    "threshold_exceeded": "⚡ [변동률 초과] {ticker}({market}) 현재가 {current_price}원 (변동 {change_pct}% ≥ 기준 {threshold_pct}%)",
}


async def send_telegram_message(message: str, *, chat_id: str | None = None) -> bool:
    """텔레그램 메시지 전송. chat_id 지정 시 해당 채팅으로, 미지정 시 시스템 chat_id 사용."""
    resolved_chat_id = chat_id or settings.telegram_chat_id
    if not settings.telegram_bot_token or not resolved_chat_id:
        logger.debug("Telegram credentials not configured, skipping alert")
        return False

    url = TELEGRAM_API_URL.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": resolved_chat_id,
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

    message = template.format(
        user_email=escape(user_email),
        ip=escape(ip),
        device=escape(device),
    )
    return await send_telegram_message(message)
