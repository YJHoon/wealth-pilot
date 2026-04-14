"""관심종목 알림 체크 — 크론잡용

주기적으로 관심종목의 현재가를 확인하여
목표 매수/매도가 도달 또는 변동률 초과 시 텔레그램 알림을 전송한다.

Edge-triggered: 조건 충족 시 1회만 전송하고, 조건이 해제된 후 재진입 시 재전송한다.
"""

import logging
from decimal import Decimal
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import AsyncSessionLocal
from app.models.analysis import Watchlist
from app.services.alert_service import send_telegram_message, WATCHLIST_ALERT_TEMPLATES
from app.services.crypto_service import decrypt_decimal_optional
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


async def check_watchlist_alerts() -> None:
    """전체 사용자의 관심종목을 순회하며 알림 조건을 체크한다.

    크론잡에서 호출. 독립적으로 DB 세션을 생성·소멸한다.
    """
    async with AsyncSessionLocal() as db:
        try:
            await _run_alert_check(db)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Watchlist alert check failed")


async def _run_alert_check(db: AsyncSession) -> None:
    """알림 조건 체크 핵심 로직."""
    result = await db.execute(
        select(Watchlist).options(joinedload(Watchlist.user))
    )
    watchlist_items = result.scalars().all()

    if not watchlist_items:
        logger.debug("No watchlist items to check")
        return

    price_service = PriceService()

    for item in watchlist_items:
        try:
            await _check_single_item(price_service, item)
        except Exception:
            logger.exception(
                "Failed to check watchlist item: ticker=%s, id=%s",
                item.ticker,
                item.id,
            )


async def _check_single_item(price_service: PriceService, item: Watchlist) -> None:
    """단일 관심종목의 알림 조건을 체크하고 알림을 전송한다."""
    try:
        cached = await price_service.fetch_stock_price(item.ticker)
        current_price = cached.price
    except Exception:
        logger.exception("Cannot fetch price for %s, skipping", item.ticker)
        return

    # 사용자별 텔레그램 chat_id 해석 (미설정 시 시스템 chat_id로 폴백)
    user_chat_id = getattr(item.user, "telegram_chat_id", None) if item.user else None

    target_buy = decrypt_decimal_optional(item.target_buy_price)
    target_sell = decrypt_decimal_optional(item.target_sell_price)
    threshold_pct = item.alert_threshold_pct

    # HTML-safe 값 (parse_mode="HTML" 대응)
    safe_ticker = escape(item.ticker)
    safe_market = escape(item.market)

    # 목표 매수가 도달 (현재가 <= 매수가) — edge-triggered
    if target_buy is not None and current_price <= target_buy:
        if not item.alerted_target_buy:
            message = WATCHLIST_ALERT_TEMPLATES["target_buy_reached"].format(
                ticker=safe_ticker,
                market=safe_market,
                current_price=f"{current_price:,.0f}",
                target_price=f"{target_buy:,.0f}",
            )
            sent = await send_telegram_message(message, chat_id=user_chat_id, pre_escaped=True)
            if sent:
                item.alerted_target_buy = True
    else:
        item.alerted_target_buy = False

    # 목표 매도가 도달 (현재가 >= 매도가) — edge-triggered
    if target_sell is not None and current_price >= target_sell:
        if not item.alerted_target_sell:
            message = WATCHLIST_ALERT_TEMPLATES["target_sell_reached"].format(
                ticker=safe_ticker,
                market=safe_market,
                current_price=f"{current_price:,.0f}",
                target_price=f"{target_sell:,.0f}",
            )
            sent = await send_telegram_message(message, chat_id=user_chat_id, pre_escaped=True)
            if sent:
                item.alerted_target_sell = True
    else:
        item.alerted_target_sell = False

    # 변동률 초과 알림 (기준가 = 목표 매수가 or 매도가 중 존재하는 값) — edge-triggered
    if threshold_pct is not None and threshold_pct > 0:
        ref_price = target_buy if target_buy is not None else target_sell
        if ref_price is not None and ref_price > 0:
            change_pct = abs(
                (current_price - ref_price) / ref_price * Decimal("100")
            )
            if change_pct >= threshold_pct:
                if not item.alerted_threshold:
                    message = WATCHLIST_ALERT_TEMPLATES["threshold_exceeded"].format(
                        ticker=safe_ticker,
                        market=safe_market,
                        current_price=f"{current_price:,.0f}",
                        change_pct=f"{change_pct:.1f}",
                        threshold_pct=f"{threshold_pct:.1f}",
                    )
                    sent = await send_telegram_message(message, chat_id=user_chat_id, pre_escaped=True)
                    if sent:
                        item.alerted_threshold = True
            else:
                item.alerted_threshold = False
        else:
            # 기준가 없음 (목표 매수/매도가 모두 미설정) — 플래그 리셋
            item.alerted_threshold = False
    else:
        item.alerted_threshold = False
