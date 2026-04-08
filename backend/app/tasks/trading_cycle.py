"""단일 매매 사이클 — 스케줄러에 의해 주기적으로 호출

독립적·무상태: DB에서 읽고 → 판단하고 → 주문하고 → DB에 기록.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
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
from app.services.account_lock import acquire_account_lock
from app.services.strategy_capital import (
    add_realized_pnl,
    get_strategy_available_capital,
)
from app.services.strategy_position import (
    apply_buy_fill,
    apply_sell_fill,
    list_strategy_positions,
    reconcile_with_kis,
    update_position_market_data,
)
from app.services.alert_service import send_telegram_message
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_value,
    encrypt_decimal,
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

# 매수 사전 검증 시 수수료/슬리피지 버퍼 (0.5%)
# KIS 위탁수수료(약 0.015%) + 시장가 슬리피지 여유분
BUY_FEE_BUFFER = Decimal("1.005")


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
    skip_messages: list[str] = []  # 사이클 종료 시 단일 알림으로 배치 전송

    # 같은 계좌의 다른 전략 사이클과 잔고조회→발주 구간이 인터리브되지 않도록
    # 계좌 단위로 직렬화. acquire_account_lock은 refcount를 자동 관리하므로
    # 임계 구간 진입 직전에 prune이 락을 회수하는 TOCTOU 경합이 차단된다.
    # TODO(Phase 2): 현재는 in-process라 멀티 워커/멀티 인스턴스 환경에서는
    # 직렬화가 보장되지 않는다. 스케일아웃 전에 Redis 분산 락
    # (aioredlock / redis-py Lock)으로 교체 필요. account_lock.py 참고.

    try:
      async with acquire_account_lock(account.id):
        # 락 획득 후 상태 재검증 — 비활성화 라우터와 직렬화되어,
        # 비활성화가 먼저 커밋되었으면 즉시 스킵.
        await db.refresh(account)
        await db.refresh(strategy)
        if not account.is_active or not strategy.is_active:
            schedule_log.status = ScheduleLogStatus.SKIPPED
            schedule_log.skip_reason = "계좌/전략 비활성화 상태"
            schedule_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

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

        # 현재 보유 종목 집합 (Phase 3: 전략별, distinct ticker 기준)
        # check_can_buy의 max_positions 제약은 "동시 보유 종목 수"이므로
        # 같은 ticker 추가 매수는 카운트 증가 없이 set 멤버십으로만 판정한다.
        positions = await list_strategy_positions(db, account.id, strategy.id)
        held_tickers: set[str] = {p.ticker for p in positions}
        # 같은 사이클 내에서 손절/시그널 매도된 ticker는 재매수 금지.
        # held_tickers에서 discard만 하면 직후 buy 분기가 "신규 종목"으로 오인해
        # 다시 매수할 수 있으므로 별도 집합으로 격리한다.
        recently_sold_tickers: set[str] = set()

        # 5. 보유 포지션 손절 체크 (Phase 3: 해당 전략 보유분만)

        for pos in positions:
            if pos.current_price is None:
                continue
            avg_price = decrypt_decimal(pos.avg_buy_price)
            current = Decimal(str(pos.current_price))
            stop_check = risk_mgr.check_stop_loss(avg_price, current)

            if stop_check.allowed:
                # 손절 매도
                qty = int(decrypt_decimal(pos.quantity))
                # Pre-Trade Check: 매도 수량 ≥ 1
                if qty <= 0:
                    logger.warning("Stop-loss skipped: zero quantity for %s", pos.ticker)
                    continue
                try:
                    order_result = await kis.place_order(
                        side="sell", ticker=pos.ticker, quantity=qty, order_type="market",
                    )
                    # NOTE: SUBMITTED를 체결로 간주하는 단순화 모델 (fill polling은 별도 작업).
                    # 거부/부분체결/슬리피지 정확화는 fill polling 도입 후 처리.
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
                    # Phase 3: 전략 포지션 차감 + 실현손익 누적
                    # KIS 주문은 이미 실행된 회복 불가 부수효과이므로, 포지션 갱신이 실패해도
                    # order 레코드는 진실로 남긴다 (삭제 금지). 대신 critical 경고를 띄우고
                    # 실현PnL은 누적하지 않는다 — 사이클 말미의 reconcile_with_kis가
                    # 합계 불일치를 추가로 surface한다.
                    try:
                        realized_delta = await apply_sell_fill(
                            db, strategy, pos.ticker, Decimal(qty), current,
                        )
                        add_realized_pnl(strategy, realized_delta)
                    except ValueError as fill_err:
                        # 알려진 비즈니스 예외(수량 부족 등)만 swallow.
                        # DB/암호화 등 미지의 예외는 사이클을 중단해야 한다.
                        logger.critical(
                            "Stop-loss fill apply failed (order persisted): "
                            "kis_order_id=%s ticker=%s qty=%d err=%s",
                            order_result.get("order_id"), pos.ticker, qty, fill_err,
                        )
                        skip_messages.append(
                            f"🚨 [회계 오류] 손절 매도는 KIS에서 실행됐으나 내부 포지션 갱신 실패: "
                            f"{pos.ticker} {qty}주 / kis_order_id={order_result.get('order_id')} / {fill_err}"
                        )
                    # 손절은 전량 매도 → 보유 set에서 제거하고 재매수 금지 set에 등록
                    held_tickers.discard(pos.ticker)
                    recently_sold_tickers.add(pos.ticker)
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
                    # 같은 사이클에서 이미 매도된 ticker는 재매수 금지 (whipsaw 방지)
                    if ticker in recently_sold_tickers:
                        logger.info("Buy skipped (sold earlier this cycle): %s", ticker)
                        continue
                    # 매수 가능 수량 계산
                    qty = risk_mgr.calculate_position_size(
                        available_cash, total_eval, current_price,
                    )
                    if qty <= 0:
                        continue

                    # 이후 산술은 모두 Decimal로 일관 처리
                    price_dec = Decimal(str(current_price))
                    qty_dec = Decimal(qty)
                    order_amount = price_dec * qty_dec

                    # 같은 ticker는 추가 매수해도 동시 보유 종목 수가 늘지 않으므로 set 멤버십 기준
                    effective_count = (
                        len(held_tickers) if ticker in held_tickers else len(held_tickers) + 1
                    )
                    buy_check = risk_mgr.check_can_buy(
                        total_eval, order_amount, effective_count,
                    )
                    if not buy_check.allowed:
                        logger.info("Buy blocked for %s: %s", ticker, buy_check.reason)
                        continue

                    # Pre-Trade Check 1: 계좌 예수금 (KIS 잔고) ≥ 주문금액 × 버퍼
                    required_cash = order_amount * BUY_FEE_BUFFER
                    if available_cash < required_cash:
                        skip_msg = (
                            f"매수 스킵: 예수금 부족 — 필요 {required_cash:,.0f}원 / "
                            f"가용 {available_cash:,.0f}원 ({ticker})"
                        )
                        logger.warning(skip_msg)
                        skip_messages.append(skip_msg)
                        continue

                    # Pre-Trade Check 2 (Phase 2): 전략별 가용 자본 ≥ 주문금액
                    # 같은 계좌의 다른 전략이 자본을 소진한 경우 차단
                    strategy_available = await get_strategy_available_capital(db, strategy)
                    if strategy_available < order_amount:
                        skip_msg = (
                            f"매수 스킵: 전략 가용자본 부족 — 필요 {order_amount:,.0f}원 / "
                            f"전략가용 {strategy_available:,.0f}원 ({ticker})"
                        )
                        logger.warning(skip_msg)
                        skip_messages.append(skip_msg)
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
                        # Phase 3: 전략 포지션 증가 (신규 ticker일 때만 set에 추가)
                        await apply_buy_fill(
                            db, strategy, ticker, ticker_name, qty_dec, price_dec,
                        )
                        held_tickers.add(ticker)
                        orders_placed += 1
                        available_cash -= order_amount
                        trade_messages.append(
                            f"📈 [매수] {ticker_name}({ticker}) {qty}주 @ {current_price:,.0f}원\n사유: {signal.reason}"
                        )
                    except KISClientError as e:
                        logger.error("Buy order failed for %s: %s", ticker, e)

                elif signal.action == "sell":
                    # Phase 3: 해당 전략의 보유 포지션만 확인 (다른 전략 보유분 침범 금지)
                    pos_result2 = await db.execute(
                        select(TradingPosition).where(
                            TradingPosition.account_id == account.id,
                            TradingPosition.strategy_id == strategy.id,
                            TradingPosition.ticker == ticker,
                        )
                    )
                    pos = pos_result2.scalar_one_or_none()
                    if pos is None:
                        continue

                    # Pre-Trade Check: 보유수량 > 0 (시그널 매도는 전량 매도)
                    qty = int(decrypt_decimal(pos.quantity))
                    if qty <= 0:
                        continue

                    try:
                        order_result = await kis.place_order(
                            side="sell", ticker=ticker, quantity=qty, order_type="market",
                        )
                        # NOTE: SUBMITTED 단순화 — fill polling은 별도 작업.
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
                        # Phase 3: 전략 포지션 차감 + 실현손익 누적
                        # 손절 케이스와 동일한 사유로 try/except (회계 정합성 방어).
                        try:
                            realized_delta = await apply_sell_fill(
                                db, strategy, ticker, Decimal(qty),
                                Decimal(str(current_price)),
                            )
                            add_realized_pnl(strategy, realized_delta)
                        except ValueError as fill_err:
                            # 알려진 비즈니스 예외만 swallow. 그 외는 위로 전파.
                            logger.critical(
                                "Signal sell fill apply failed (order persisted): "
                                "kis_order_id=%s ticker=%s qty=%d err=%s",
                                order_result.get("order_id"), ticker, qty, fill_err,
                            )
                            skip_messages.append(
                                f"🚨 [회계 오류] 시그널 매도는 KIS에서 실행됐으나 내부 포지션 갱신 실패: "
                                f"{ticker} {qty}주 / kis_order_id={order_result.get('order_id')} / {fill_err}"
                            )
                        # 시그널 매도는 전량 매도 → set 제거 + 재매수 금지 등록
                        held_tickers.discard(ticker)
                        recently_sold_tickers.add(ticker)
                        orders_placed += 1
                        trade_messages.append(
                            f"📉 [매도] {pos.ticker_name}({ticker}) {qty}주 @ {current_price:,.0f}원\n사유: {signal.reason}"
                        )
                    except KISClientError as e:
                        logger.error("Sell order failed for %s: %s", ticker, e)

            except Exception:
                logger.exception("Error evaluating ticker %s", ticker)

        # 8. 포지션 시세 갱신 + KIS 정합성 체크 (Phase 3)
        mismatches = await _sync_positions(db, kis, account)
        if mismatches:
            mismatch_text = "\n".join(f"- {m}" for m in mismatches)
            logger.error(
                "Position reconciliation mismatch (account=%s):\n%s",
                account.id, mismatch_text,
            )
            schedule_log.error_message = (
                ((schedule_log.error_message or "") + "\n[정합성 불일치]\n" + mismatch_text)[:2000]
            )
            # 알림 실패가 사이클 자체를 ERROR로 뒤집지 않도록 격리.
            # 정합성 불일치 사실은 schedule_log.error_message에 이미 기록되어 있다.
            try:
                await send_telegram_message(
                    f"⚠️ [포지션 정합성 불일치] 계좌={account.id}\n{mismatch_text}"
                )
            except Exception:
                logger.exception("Failed to send reconciliation mismatch alert")

        # 9. 스케줄 로그 완료
        schedule_log.tickers_evaluated = tickers_evaluated
        schedule_log.orders_placed = orders_placed
        schedule_log.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 10. 텔레그램 알림 (체결 + 사전검증 스킵을 단일 메시지로 배치 전송)
        if trade_messages or skip_messages:
            sections = [
                f"🤖 [자동매매 사이클 완료]\n"
                f"종목 분석: {tickers_evaluated}개 | 주문: {orders_placed}건"
            ]
            if trade_messages:
                sections.append("\n\n".join(trade_messages))
            if skip_messages:
                sections.append(
                    "⚠️ 사전검증 스킵 (" + str(len(skip_messages)) + "건)\n"
                    + "\n".join(f"- {m}" for m in skip_messages)
                )
            await send_telegram_message("\n\n".join(sections))

    except Exception:
        schedule_log.status = ScheduleLogStatus.ERROR
        import traceback
        schedule_log.error_message = traceback.format_exc()[:2000]
        schedule_log.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    finally:
        await kis.close()


async def _sync_positions(
    db: AsyncSession, kis: KISClient, account: TradingAccount,
) -> list[str]:
    """Phase 3: KIS 잔고는 포지션 소유권의 source of truth가 아니다.

    책임:
    1. 현금 잔고 동기화 (account.cash_balance)
    2. 같은 종목의 모든 전략 포지션에 current_price/unrealized_pnl 갱신
    3. Σ(전략 포지션 수량) vs KIS 실잔고 정합성 체크

    실제 포지션 증감은 매수/매도 체결 시 apply_buy_fill / apply_sell_fill에서 수행.

    Returns:
        정합성 불일치 메시지 목록 (정상이면 빈 리스트).

    예외는 swallow하지 않고 호출자에게 전파한다 — sync 실패를
    "정합성 OK([])"로 오인하면 회계 모니터링이 침묵하게 된다.
    """
    balance = await kis.get_balance()
    account.cash_balance = encrypt_decimal(balance["cash"])

    kis_holdings = {h["ticker"]: h for h in balance["holdings"]}

    for ticker, holding in kis_holdings.items():
        await update_position_market_data(
            db, account.id, ticker, float(holding["current_price"]),
        )

    return await reconcile_with_kis(db, account.id, kis_holdings)
