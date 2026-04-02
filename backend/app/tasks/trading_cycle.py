"""단일 매매 사이클 — 스케줄러에 의해 주기적으로 호출

독립적·무상태: DB에서 읽고 → 판단하고 → 주문하고 → DB에 기록.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.trading import (
    OrderSide,
    OrderStatus,
    OrderType,
    ScheduleLogStatus,
    TradingAccount,
    TradingOrder,
    TradingPosition,
    TradingScheduleLog,
    TradingStrategy,
)
from app.services.alert_service import send_telegram_message
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_value,
    encrypt_decimal,
    encrypt_decimal_optional,
)
from app.services.kis_client import KISClient, KISClientError
from app.services.risk_manager import RiskManager
from app.services.trading_strategy import Signal, create_strategy

logger = logging.getLogger(__name__)

# 한국 시장 운영 시간 (KST)
KST = timezone(timedelta(hours=9))
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 0
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30


def _is_market_hours() -> bool:
    """장 운영 시간인지 체크 (KST 기준 평일 09:00~15:30)."""
    now = datetime.now(KST)
    # 주말 체크 (월=0, 일=6)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)
    return market_open <= now <= market_close


async def execute_trading_cycle(user_id_str: str, strategy_id_str: str):
    """단일 매매 사이클 실행.

    APScheduler가 호출하므로 인자는 문자열로 받는다.
    """
    user_id = UUID(user_id_str)
    strategy_id = UUID(strategy_id_str)

    async with AsyncSessionLocal() as db:
        try:
            await _run_cycle(db, user_id, strategy_id)
        except Exception:
            logger.exception(
                "Trading cycle failed: user=%s, strategy=%s",
                user_id, strategy_id,
            )
            # 에러 로그 기록
            try:
                import traceback
                error_log = TradingScheduleLog(
                    user_id=user_id,
                    strategy_id=strategy_id,
                    status=ScheduleLogStatus.ERROR,
                    error_message=traceback.format_exc()[:2000],
                    completed_at=datetime.now(timezone.utc),
                )
                db.add(error_log)
                await db.commit()

                await send_telegram_message(
                    f"❌ [매매 사이클 오류]\n전략: {strategy_id}\n에러: 로그 확인 필요"
                )
            except Exception:
                logger.exception("Failed to log trading cycle error")


async def _run_cycle(db: AsyncSession, user_id: UUID, strategy_id: UUID):
    """매매 사이클 핵심 로직."""

    # 1. 전략 & 계좌 로드
    strategy = await db.get(TradingStrategy, strategy_id)
    if not strategy or strategy.user_id != user_id or not strategy.is_active:
        logger.warning("Strategy not found or inactive: %s", strategy_id)
        return

    account = await db.get(TradingAccount, strategy.account_id)
    if not account or not account.is_active:
        logger.warning("Account not found or inactive: %s", strategy.account_id)
        return

    # 2. 장 운영 시간 체크
    if strategy.market_hours_only and not _is_market_hours():
        log = TradingScheduleLog(
            user_id=user_id,
            strategy_id=strategy_id,
            status=ScheduleLogStatus.SKIPPED,
            skip_reason="장 운영 시간 외",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(log)
        await db.commit()
        return

    # 3. KIS 클라이언트 생성 (인증정보는 .env에서 모드별 로드)
    creds = settings.kis_credentials(account.mode.value)
    kis = KISClient(
        app_key=creds["app_key"],
        app_secret=creds["app_secret"],
        account_number=creds["account_number"],
        account_product_code=creds["account_product_code"],
        mode=account.mode,
        access_token=decrypt_value(account.access_token) if account.access_token else None,
        token_expires_at=account.token_expires_at,
    )

    schedule_log = TradingScheduleLog(
        user_id=user_id,
        strategy_id=strategy_id,
        status=ScheduleLogStatus.SUCCESS,
    )
    db.add(schedule_log)
    await db.flush()  # schedule_log.id 확보

    orders_placed = 0
    tickers_evaluated = 0
    trade_messages: list[str] = []

    try:
        # 토큰 갱신 후 DB에 저장
        await kis._ensure_token()
        from app.services.crypto_service import encrypt_value
        account.access_token = encrypt_value(kis.access_token) if kis.access_token else None
        account.token_expires_at = kis.token_expires_at

        # 4. 잔고 조회
        balance = await kis.get_balance()
        available_cash = balance["cash"]
        total_eval = balance["total_eval"] + available_cash

        # 전략 & 리스크 매니저 생성
        strat = create_strategy(strategy.strategy_type.value, strategy.params_json)
        risk_mgr = RiskManager.from_params(strategy.params_json)

        # 현재 포지션 수 조회
        pos_result = await db.execute(
            select(func.count()).select_from(TradingPosition).where(
                TradingPosition.account_id == account.id,
            )
        )
        position_count = pos_result.scalar_one()

        # 5. 보유 포지션 손절 체크
        positions = (await db.execute(
            select(TradingPosition).where(TradingPosition.account_id == account.id)
        )).scalars().all()

        for pos in positions:
            if pos.current_price is None:
                continue
            avg_price = decrypt_decimal(pos.avg_buy_price)
            current = Decimal(str(pos.current_price))
            stop_check = risk_mgr.check_stop_loss(avg_price, current)

            if stop_check.allowed:
                # 손절 매도
                qty = int(decrypt_decimal(pos.quantity))
                try:
                    order_result = await kis.place_order(
                        side="sell", ticker=pos.ticker, quantity=qty, order_type="market",
                    )
                    order = TradingOrder(
                        user_id=user_id,
                        account_id=account.id,
                        strategy_id=strategy_id,
                        schedule_log_id=schedule_log.id,
                        side=OrderSide.SELL,
                        ticker=pos.ticker,
                        ticker_name=pos.ticker_name,
                        quantity=encrypt_decimal(Decimal(qty)),
                        price=encrypt_decimal(current),
                        order_type=OrderType.MARKET,
                        status=OrderStatus.SUBMITTED,
                        kis_order_id=order_result.get("order_id"),
                        reason=f"손절: {stop_check.reason}",
                    )
                    db.add(order)
                    orders_placed += 1
                    trade_messages.append(
                        f"🚨 [손절 매도] {pos.ticker_name}({pos.ticker}) {qty}주 @ {current:,.0f}원"
                    )
                    logger.info("Stop-loss sell: %s %d shares", pos.ticker, qty)
                except KISClientError as e:
                    logger.error("Stop-loss order failed for %s: %s", pos.ticker, e)

        # 6. 일일 손실 한도 체크
        today_start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start.astimezone(timezone.utc)

        # 오늘 체결된 주문의 손익 합계 (간략 계산)
        daily_check = risk_mgr.check_daily_loss(Decimal("0"))  # 실현 PnL 추적은 Phase 2에서 상세화
        if not daily_check.allowed:
            schedule_log.status = ScheduleLogStatus.SKIPPED
            schedule_log.skip_reason = daily_check.reason
            schedule_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await send_telegram_message(f"⛔ [일일 손실 한도]\n{daily_check.reason}")
            return

        # 7. 대상 종목별 전략 평가
        for ticker in strategy.target_tickers:
            tickers_evaluated += 1
            try:
                # 일별 시세 조회
                price_history = await kis.get_price_history(ticker, period="D", count=60)
                if not price_history:
                    continue

                # 전략 평가
                signal: Signal = strat.evaluate(ticker, price_history)
                current_price_data = price_history[-1]
                current_price = current_price_data["close"]

                if signal.action == "hold":
                    continue

                if signal.action == "buy":
                    # 매수 가능 수량 계산
                    qty = risk_mgr.calculate_position_size(
                        available_cash, total_eval, current_price,
                    )
                    if qty <= 0:
                        continue

                    buy_check = risk_mgr.check_can_buy(
                        total_eval, current_price * qty, position_count,
                    )
                    if not buy_check.allowed:
                        logger.info("Buy blocked for %s: %s", ticker, buy_check.reason)
                        continue

                    # 매수 주문
                    try:
                        # 종목명 조회
                        price_info = await kis.get_current_price(ticker)
                        ticker_name = price_info.get("name", "")

                        order_result = await kis.place_order(
                            side="buy", ticker=ticker, quantity=qty, order_type="market",
                        )
                        order = TradingOrder(
                            user_id=user_id,
                            account_id=account.id,
                            strategy_id=strategy_id,
                            schedule_log_id=schedule_log.id,
                            side=OrderSide.BUY,
                            ticker=ticker,
                            ticker_name=ticker_name,
                            quantity=encrypt_decimal(Decimal(qty)),
                            price=encrypt_decimal(current_price),
                            order_type=OrderType.MARKET,
                            status=OrderStatus.SUBMITTED,
                            kis_order_id=order_result.get("order_id"),
                            reason=signal.reason,
                        )
                        db.add(order)
                        orders_placed += 1
                        position_count += 1
                        available_cash -= current_price * qty
                        trade_messages.append(
                            f"📈 [매수] {ticker_name}({ticker}) {qty}주 @ {current_price:,.0f}원\n사유: {signal.reason}"
                        )
                    except KISClientError as e:
                        logger.error("Buy order failed for %s: %s", ticker, e)

                elif signal.action == "sell":
                    # 보유 포지션 확인
                    pos_result2 = await db.execute(
                        select(TradingPosition).where(
                            TradingPosition.account_id == account.id,
                            TradingPosition.ticker == ticker,
                        )
                    )
                    pos = pos_result2.scalar_one_or_none()
                    if pos is None:
                        continue

                    qty = int(decrypt_decimal(pos.quantity))
                    if qty <= 0:
                        continue

                    try:
                        order_result = await kis.place_order(
                            side="sell", ticker=ticker, quantity=qty, order_type="market",
                        )
                        order = TradingOrder(
                            user_id=user_id,
                            account_id=account.id,
                            strategy_id=strategy_id,
                            schedule_log_id=schedule_log.id,
                            side=OrderSide.SELL,
                            ticker=ticker,
                            ticker_name=pos.ticker_name,
                            quantity=encrypt_decimal(Decimal(qty)),
                            price=encrypt_decimal(current_price),
                            order_type=OrderType.MARKET,
                            status=OrderStatus.SUBMITTED,
                            kis_order_id=order_result.get("order_id"),
                            reason=signal.reason,
                        )
                        db.add(order)
                        orders_placed += 1
                        position_count -= 1
                        trade_messages.append(
                            f"📉 [매도] {pos.ticker_name}({ticker}) {qty}주 @ {current_price:,.0f}원\n사유: {signal.reason}"
                        )
                    except KISClientError as e:
                        logger.error("Sell order failed for %s: %s", ticker, e)

            except Exception:
                logger.exception("Error evaluating ticker %s", ticker)

        # 8. 포지션 업데이트 (KIS 잔고 기반)
        await _sync_positions(db, kis, account)

        # 9. 스케줄 로그 완료
        schedule_log.tickers_evaluated = tickers_evaluated
        schedule_log.orders_placed = orders_placed
        schedule_log.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 10. 텔레그램 알림
        if trade_messages:
            summary = "\n\n".join(trade_messages)
            await send_telegram_message(
                f"🤖 [자동매매 사이클 완료]\n"
                f"종목 분석: {tickers_evaluated}개 | 주문: {orders_placed}건\n\n"
                f"{summary}"
            )

    except Exception:
        schedule_log.status = ScheduleLogStatus.ERROR
        import traceback
        schedule_log.error_message = traceback.format_exc()[:2000]
        schedule_log.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    finally:
        await kis.close()


async def _sync_positions(db: AsyncSession, kis: KISClient, account: TradingAccount):
    """KIS 잔고를 기반으로 TradingPosition 동기화."""
    try:
        balance = await kis.get_balance()

        # 현금 잔고 동기화
        account.cash_balance = encrypt_decimal(balance["cash"])

        kis_holdings = {h["ticker"]: h for h in balance["holdings"]}

        # 기존 포지션 조회
        result = await db.execute(
            select(TradingPosition).where(TradingPosition.account_id == account.id)
        )
        existing_positions = {p.ticker: p for p in result.scalars().all()}

        # KIS 잔고 기준으로 업데이트/생성
        for ticker, holding in kis_holdings.items():
            if ticker in existing_positions:
                pos = existing_positions[ticker]
                pos.quantity = encrypt_decimal(Decimal(holding["quantity"]))
                pos.avg_buy_price = encrypt_decimal(holding["avg_price"])
                pos.current_price = float(holding["current_price"])
                pos.unrealized_pnl = encrypt_decimal_optional(holding["pnl"])
            else:
                pos = TradingPosition(
                    user_id=account.user_id,
                    account_id=account.id,
                    ticker=ticker,
                    ticker_name=holding["name"],
                    quantity=encrypt_decimal(Decimal(holding["quantity"])),
                    avg_buy_price=encrypt_decimal(holding["avg_price"]),
                    current_price=float(holding["current_price"]),
                    unrealized_pnl=encrypt_decimal_optional(holding["pnl"]),
                )
                db.add(pos)

        # KIS에 없는 포지션 삭제 (전량 매도된 것)
        for ticker, pos in existing_positions.items():
            if ticker not in kis_holdings:
                await db.delete(pos)

    except Exception:
        logger.exception("Failed to sync positions")
