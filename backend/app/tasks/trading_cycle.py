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
    StrategyType,
    TradingAccount,
    TradingDecision,
    TradingMode,
    TradingOrder,
    TradingPosition,
    TradingScheduleLog,
    TradingStrategy,
)
from app.services.adaptive_rules import get_active_rules
from app.services.decision_backfill import backfill_sell_results
from app.services.decision_embedding import (
    build_context_text,
    embed_decision,
    format_similar_cases_for_prompt,
    search_similar_cases,
)
from app.services.decision_memory import DecisionMemory, load_decision_memory
from app.services.llm_advisor import (
    LLMDecision,
    PortfolioContext,
    get_llm_decision,
)
from app.services.account_lock import acquire_account_lock
from app.services.strategy_capital import (
    add_realized_pnl,
    get_initial_capital,
    get_realized_pnl,
    get_strategy_available_capital,
)
from app.services.order_netting import find_opposite_open_order
from app.services.order_polling import poll_open_orders
from app.services.strategy_position import (
    apply_buy_fill,
    apply_sell_fill,
    get_strategy_position,
    list_strategy_positions,
    reconcile_with_kis,
    update_position_market_data,
)
from app.services.alert_service import escape_html, send_telegram_message
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


import holidays as _holidays_lib

_KR_HOLIDAYS = _holidays_lib.KR()


def _is_market_hours() -> bool:
    """장 운영 시간인지 체크 (KST 기준 평일 09:00~15:30, 공휴일 제외)."""
    now = datetime.now(KST)
    # 주말 체크 (월=0, 일=6)
    if now.weekday() >= 5:
        return False
    # 한국 공휴일 체크
    if now.date() in _KR_HOLIDAYS:
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

    # 0. 글로벌 킬 스위치 체크 (런타임)
    if not settings.trading_enabled:
        logger.info("Trading disabled globally, skipping cycle: strategy=%s", strategy_id)
        return

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

    # ── Stage 3: LLM 사전 패스 (락 밖) ──
    # LLM 호출은 종목당 수 초가 걸려 계좌 락을 길게 점유하면 다른 전략 사이클을
    # 차단한다. 시세조회 + Claude 호출을 락 *진입 전* 에 끝내고 결과만 캐시한 뒤,
    # 락 안에서는 잔고/포지션 최신 상태로 재검증해 발주만 수행한다.
    # 사전 패스 스냅샷은 약간 stale할 수 있지만 LLM 컨텍스트로는 충분하며,
    # 발주 시점의 정합성은 락 내부 Pre-Trade Check가 보장한다.
    is_llm_strategy = strategy.strategy_type == StrategyType.LLM_ADVISOR
    llm_cache: dict[str, tuple[LLMDecision, list[dict]]] = {}
    decision_memory: DecisionMemory | None = None
    active_adaptive_rules: list[str] | None = None
    # Step 6: 락 밖에서 임베딩 생성할 decision ID 수집
    pending_embed_ids: list[UUID] = []
    if is_llm_strategy:
        try:
            pre_balance = await kis.get_balance()
            pre_cash = pre_balance["cash"]
            pre_total_eval = pre_balance["total_eval"] + pre_cash
            decision_memory = await load_decision_memory(db, strategy_id)
            # Step 4 (모듈 C): 활성 adaptive rules 로드
            # 규칙 로드 실패는 사이클을 중단하지 않는다 (fail-open).
            try:
                active_adaptive_rules = await get_active_rules(db, strategy_id) or None
            except Exception:
                logger.warning(
                    "Failed to load adaptive rules (continuing without): strategy=%s",
                    strategy_id, exc_info=True,
                )
            # holdings는 KIS 응답에서 직접 구성 — 현금/총평가와 동일 소스라
            # 정합되며, DB 포지션은 reconcile(poll_open_orders) 전이라
            # 일시적으로 KIS와 어긋날 수 있다. 발주 시점의 전략 격리는
            # 락 안 Pre-Trade Check가 보장하므로 LLM 컨텍스트만 계좌 전체
            # 기준으로 단일화한다.
            pre_holdings = [
                {
                    "ticker": h["ticker"],
                    "ticker_name": h.get("name", ""),
                    "quantity": str(h["quantity"]),
                    "avg_buy_price": str(h["avg_price"]),
                    "current_price": str(h.get("current_price"))
                    if h.get("current_price") is not None else None,
                    "unrealized_pnl": str(h.get("pnl"))
                    if h.get("pnl") is not None else None,
                }
                for h in pre_balance.get("holdings", [])
            ]
            pre_portfolio_ctx = PortfolioContext(
                cash=pre_cash, total_eval=pre_total_eval, holdings=pre_holdings,
            )
            for ticker in strategy.target_tickers:
                try:
                    ph = await kis.get_price_history(ticker, period="D", count=60)
                    if not ph:
                        continue
                    try:
                        tinfo = await kis.get_current_price(ticker)
                        tname = tinfo.get("name", "") or ""
                    except KISClientError as e:
                        logger.debug(
                            "kis.get_current_price 실패 ticker=%s: %s",
                            ticker, e, exc_info=True,
                        )
                        tname = ""
                    # Step 6 (모듈 D): 유사 케이스 검색 (fail-open)
                    similar_cases_text: str | None = None
                    try:
                        search_ctx = build_context_text(
                            ticker=ticker,
                            ticker_name=tname,
                            action="",  # 아직 행동 미결정
                            confidence=0,
                            reason="",
                            market_regime=None,
                            used_indicators=None,
                            is_query=True,
                        )
                        similar = await search_similar_cases(
                            db, search_ctx, strategy_id,
                        )
                        similar_cases_text = format_similar_cases_for_prompt(similar)
                    except Exception:
                        logger.warning(
                            "RAG search failed for %s (continuing without)",
                            ticker, exc_info=True,
                        )

                    decision = await get_llm_decision(
                        ticker=ticker,
                        ticker_name=tname,
                        price_history=ph,
                        portfolio=pre_portfolio_ctx,
                        memory=decision_memory,
                        adaptive_rules=active_adaptive_rules,
                        similar_cases=similar_cases_text,
                    )
                    llm_cache[ticker] = (decision, ph)
                except Exception:
                    logger.exception("LLM pre-pass failed for %s", ticker)
        except Exception:
            # 사전 패스 전체 실패 시 LLM 사이클은 발주 없이 진행 (fail-safe).
            logger.exception("LLM pre-pass aborted; cycle will place no orders")

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

        # 3.5 미체결/부분체결 주문 폴링 — 이전 사이클의 SUBMITTED를 reconcile
        # eager apply 가정과 KIS 실체결의 차이를 잔고/포지션을 읽기 전에 보정한다.
        try:
            poll_result = await poll_open_orders(db, account, kis)
            if poll_result.cancelled or poll_result.partial:
                logger.info(
                    "Fill polling: polled=%d filled=%d partial=%d cancelled=%d",
                    poll_result.polled, poll_result.filled,
                    poll_result.partial, poll_result.cancelled,
                )
            if poll_result.errors:
                logger.warning("Fill polling errors: %s", poll_result.errors)
        except Exception:
            # 폴링 실패는 사이클 자체를 막지 않는다. 다음 사이클에서 다시 시도.
            logger.exception("Fill polling failed; continuing cycle")

        # 4. 잔고 조회
        balance = await kis.get_balance()
        available_cash = balance["cash"]
        total_eval = balance["total_eval"] + available_cash

        # 전략 & 리스크 매니저 생성
        # LLM 어드바이저는 룰베이스 strat 인스턴스가 없다 — 사전 패스에서 캐시됨.
        strat = (
            None if is_llm_strategy
            else create_strategy(strategy.strategy_type.value, strategy.params_json)
        )
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

        # 손절 루프에서도 카운트를 증가시키므로 여기서 초기화
        today_trade_count = 0

        # 4.5 킬 스위치 — 누적 손실률이 기준 이상이면 전략 자동 비활성화
        # 미실현PnL을 최신 시세(balance)로 재계산하여 stale 값 방지
        strategy_realized = get_realized_pnl(strategy)
        strategy_unrealized = Decimal("0")
        kis_holdings = {h["ticker"]: h for h in balance.get("holdings", [])}
        for pos in positions:
            qty = decrypt_decimal(pos.quantity)
            avg = decrypt_decimal(pos.avg_buy_price)
            kis_h = kis_holdings.get(pos.ticker)
            if kis_h and kis_h.get("current_price") is not None:
                cur = Decimal(str(kis_h["current_price"]))
                strategy_unrealized += (cur - avg) * qty
            elif pos.current_price is not None:
                cur = Decimal(str(pos.current_price))
                strategy_unrealized += (cur - avg) * qty
        strategy_initial = get_initial_capital(strategy)

        kill_check = risk_mgr.check_kill_switch(
            strategy_realized, strategy_unrealized, strategy_initial,
        )
        if not kill_check.allowed:
            strategy.is_active = False
            strategy.is_scheduled = False
            strategy.killed_at = datetime.now(timezone.utc)
            strategy.killed_reason = kill_check.reason
            schedule_log.status = ScheduleLogStatus.SKIPPED
            schedule_log.skip_reason = kill_check.reason
            schedule_log.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # DB 커밋 성공 후 인메모리 스케줄 제거 (실패해도 DB 상태는 보존)
            try:
                from app.tasks.trading_scheduler import trading_scheduler
                trading_scheduler.remove_schedule(user_id, strategy_id)
            except Exception:
                logger.warning(
                    "Failed to remove in-memory schedule after kill switch: strategy=%s",
                    strategy_id, exc_info=True,
                )

            await send_telegram_message(
                f"🚨 [킬 스위치 발동]\n전략: {escape_html(strategy.name)}\n{escape_html(kill_check.reason)}\n"
                f"전략이 자동 비활성화되었습니다.",
                pre_escaped=True,
            )
            return

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

                # Phase 4: 네팅 — 같은 계좌의 반대 방향 PENDING/SUBMITTED 주문이 있으면 스킵.
                if account.allow_netting:
                    opp = await find_opposite_open_order(
                        db, account.id, pos.ticker, OrderSide.SELL,
                    )
                    if opp is not None:
                        skip_msg = (
                            f"손절 매도 스킵(네팅): 같은 종목 반대 방향 주문 존재 — "
                            f"{pos.ticker} / opp_order={opp.id}"
                        )
                        logger.warning(skip_msg)
                        skip_messages.append(skip_msg)
                        continue
                try:
                    # 폴링 롤백용 pre-state: 매도 직전 보유분
                    pre_qty_snap = decrypt_decimal(pos.quantity)
                    pre_avg_snap = decrypt_decimal(pos.avg_buy_price)

                    # DB에 PENDING 주문 먼저 기록 (고아 주문 방지)
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
                        status=OrderStatus.PENDING,
                        reason=f"손절: {stop_check.reason}",
                        pre_apply_qty=encrypt_decimal(pre_qty_snap),
                        pre_apply_avg_buy_price=encrypt_decimal(pre_avg_snap),
                    )
                    db.add(order)
                    await db.flush()

                    # KIS 발주
                    order_result = await kis.place_order(
                        side="sell", ticker=pos.ticker, quantity=qty, order_type="market",
                    )
                    order.status = OrderStatus.SUBMITTED
                    order.kis_order_id = order_result.get("order_id")

                    # Phase 3: 전략 포지션 차감 + 실현손익 누적
                    try:
                        realized_delta = await apply_sell_fill(
                            db, strategy, pos.ticker, Decimal(qty), current,
                        )
                        add_realized_pnl(strategy, realized_delta)
                    except ValueError as fill_err:
                        logger.critical(
                            "Stop-loss fill apply failed (order persisted): "
                            "kis_order_id=%s ticker=%s qty=%d err=%s",
                            order.kis_order_id, pos.ticker, qty, fill_err,
                        )
                        skip_messages.append(
                            f"🚨 [회계 오류] 손절 매도는 KIS에서 실행됐으나 내부 포지션 갱신 실패: "
                            f"{pos.ticker} {qty}주 / kis_order_id={order.kis_order_id} / {fill_err}"
                        )
                    # 손절은 전량 매도 → 보유 set에서 제거하고 재매수 금지 set에 등록
                    held_tickers.discard(pos.ticker)
                    recently_sold_tickers.add(pos.ticker)
                    orders_placed += 1
                    # 손절은 안전장치이므로 일일 횟수로 차단하지 않지만 카운트에 반영
                    today_trade_count += 1
                    trade_messages.append(
                        f"🚨 [손절 매도] {escape_html(pos.ticker_name)}({escape_html(pos.ticker)}) {qty}주 @ {current:,.0f}원"
                    )
                    # 의사결정 결과 백필 (모듈 B/C 학습 데이터)
                    try:
                        stop_pnl = (current - avg_price) * Decimal(qty)
                        await backfill_sell_results(
                            db, strategy_id, pos.ticker, current, stop_pnl,
                        )
                    except Exception:
                        logger.warning(
                            "Decision backfill failed (stop-loss): ticker=%s",
                            pos.ticker, exc_info=True,
                        )
                    logger.info("Stop-loss sell: %s %d shares", pos.ticker, qty)
                except KISClientError as e:
                    order.status = OrderStatus.REJECTED
                    logger.error("Stop-loss order failed for %s: %s", pos.ticker, e)

        # 손절 후 strategy_realized 갱신 (종목 루프 내 킬 스위치 재체크 정확도)
        if orders_placed > 0:
            strategy_realized = get_realized_pnl(strategy)

        # 6. 일일 손실 한도 체크 — 실제 오늘 실현 PnL 계산
        today_start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start.astimezone(timezone.utc)

        today_sell_orders_result = await db.execute(
            select(TradingOrder).where(
                TradingOrder.strategy_id == strategy_id,
                TradingOrder.side == OrderSide.SELL,
                TradingOrder.status.in_([OrderStatus.FILLED, OrderStatus.SUBMITTED]),
                TradingOrder.created_at >= today_start_utc,
            )
        )
        today_realized_pnl = Decimal("0")
        for sell_order in today_sell_orders_result.scalars().all():
            sell_price = decrypt_decimal(sell_order.price)
            sell_qty = decrypt_decimal(sell_order.quantity)
            if sell_order.pre_apply_avg_buy_price:
                avg_buy = decrypt_decimal(sell_order.pre_apply_avg_buy_price)
                today_realized_pnl += (sell_price - avg_buy) * sell_qty

        daily_check = risk_mgr.check_daily_loss(today_realized_pnl)
        if not daily_check.allowed:
            schedule_log.status = ScheduleLogStatus.SKIPPED
            schedule_log.skip_reason = daily_check.reason
            schedule_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await send_telegram_message(f"⛔ [일일 손실 한도]\n{daily_check.reason}")
            return

        # 6.5 일일 거래 횟수 한도 체크
        today_orders_count_result = await db.execute(
            select(func.count()).select_from(TradingOrder).where(
                TradingOrder.strategy_id == strategy_id,
                TradingOrder.status.in_([
                    OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.PARTIAL,
                ]),
                TradingOrder.created_at >= today_start_utc,
            )
        )
        today_trade_count = today_orders_count_result.scalar() or 0
        daily_trades_check = risk_mgr.check_daily_trades(today_trade_count)
        if not daily_trades_check.allowed:
            schedule_log.status = ScheduleLogStatus.SKIPPED
            schedule_log.skip_reason = daily_trades_check.reason
            schedule_log.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await send_telegram_message(f"⛔ [일일 거래 횟수 한도]\n{daily_trades_check.reason}")
            return

        # 사이클 내 일일 거래 횟수 추적 — 주문 생성 시마다 증가시켜
        # 같은 사이클에서 max_daily_trades를 초과하지 않도록 한다.
        # today_trade_count를 직접 사용 (손절 루프에서 이미 증가분 반영됨).

        # 7. 대상 종목별 전략 평가
        _kill_switch_tripped = False
        for ticker in strategy.target_tickers:
            tickers_evaluated += 1
            try:
                # 전략 평가 — 룰베이스 vs LLM 분기
                llm_decision: LLMDecision | None = None
                if is_llm_strategy:
                    cached = llm_cache.get(ticker)
                    if cached is None:
                        # 사전 패스에서 실패했거나 시세 없음 — 발주 없이 스킵
                        continue
                    llm_decision, price_history = cached
                    current_price_data = price_history[-1]
                    current_price = current_price_data["close"]
                    signal = Signal(
                        action=llm_decision.action,
                        confidence=Decimal(llm_decision.confidence) / Decimal(100),
                        reason=llm_decision.reason,
                    )
                    # 의사결정 로그 — 발주 여부와 무관하게 항상 기록
                    decision_row = TradingDecision(
                        user_id=user_id,
                        strategy_id=strategy_id,
                        account_id=account.id,
                        schedule_log_id=schedule_log.id,
                        ticker=ticker,
                        action=llm_decision.action,
                        confidence=llm_decision.confidence,
                        reason=llm_decision.reason,
                        suggested_quantity=(
                            encrypt_decimal(Decimal(llm_decision.suggested_quantity))
                            if llm_decision.suggested_quantity else None
                        ),
                        # suggested_amount는 현재 LLM 응답 스키마에 없음(수량만 받음).
                        # 컬럼은 미래 확장용으로 남겨둔다.
                        market_regime=llm_decision.market_regime,
                        used_indicators=llm_decision.used_indicators,
                        model=llm_decision.model,
                        input_tokens=llm_decision.input_tokens,
                        output_tokens=llm_decision.output_tokens,
                        executed=False,
                    )
                    db.add(decision_row)
                    await db.flush()

                    # Step 6 (모듈 D): 임베딩은 CPU-bound라 락 밖에서 생성
                    pending_embed_ids.append(decision_row.id)

                    # 신뢰도 임계값 — 미달이면 hold로 강제
                    if (
                        llm_decision.action != "hold"
                        and llm_decision.confidence < settings.llm_advisor_min_confidence
                    ):
                        decision_row.blocked_reason = (
                            f"confidence {llm_decision.confidence} < "
                            f"{settings.llm_advisor_min_confidence}"
                        )
                        logger.info(
                            "LLM decision blocked (low confidence): %s %s conf=%d",
                            ticker, llm_decision.action, llm_decision.confidence,
                        )
                        continue

                    # Step 3: 사용자 승인 모드 — pending으로 저장 후 발주 스킵
                    _raw_approval = strategy.params_json.get("approval_required", False)
                    approval_required = (
                        _raw_approval is True
                        or str(_raw_approval).lower() in ("true", "1", "yes")
                    )
                    if approval_required and llm_decision.action != "hold":
                        try:
                            timeout_minutes = max(1, int(
                                strategy.params_json.get("approval_timeout_minutes", 30)
                            ))
                        except (TypeError, ValueError):
                            timeout_minutes = 30
                        decision_row.approval_status = "pending"
                        decision_row.approval_expires_at = (
                            datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
                        )
                        trade_messages.append(
                            f"⏳ [승인 대기] {escape_html(ticker)} {escape_html(llm_decision.action)} "
                            f"(confidence={llm_decision.confidence}): "
                            f"{escape_html(llm_decision.reason[:80])}"
                        )
                        logger.info(
                            "LLM decision pending approval: %s %s conf=%d",
                            ticker, llm_decision.action, llm_decision.confidence,
                        )
                        continue
                else:
                    # 룰베이스: 락 안에서 시세 조회 (LLM 사전 패스 미적용)
                    price_history = await kis.get_price_history(
                        ticker, period="D", count=60,
                    )
                    if not price_history:
                        continue
                    current_price_data = price_history[-1]
                    current_price = current_price_data["close"]
                    signal = strat.evaluate(ticker, price_history)

                if signal.action == "hold":
                    continue

                # 사이클 내 일일 거래 횟수 재체크 (손절 등으로 카운트 증가 가능)
                if (
                    risk_mgr.max_daily_trades > 0
                    and today_trade_count >= risk_mgr.max_daily_trades
                ):
                    logger.info(
                        "Order skipped (daily trade limit in-cycle): %s %s count=%d",
                        ticker, signal.action, today_trade_count,
                    )
                    skip_messages.append(
                        f"일일 거래 횟수 한도 (사이클 내): {ticker} {signal.action} 스킵"
                    )
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

                    # Phase 4: 네팅 — 같은 종목 반대 방향(매도) 주문이 있으면 스킵.
                    if account.allow_netting:
                        opp = await find_opposite_open_order(
                            db, account.id, ticker, OrderSide.BUY,
                        )
                        if opp is not None:
                            skip_msg = (
                                f"매수 스킵(네팅): 같은 종목 반대 방향 주문 존재 — "
                                f"{ticker} / opp_order={opp.id}"
                            )
                            logger.warning(skip_msg)
                            skip_messages.append(skip_msg)
                            continue

                    # 매수 주문
                    try:
                        # 종목명 조회
                        price_info = await kis.get_current_price(ticker)
                        ticker_name = price_info.get("name", "")

                        # 폴링 롤백용 pre-state: 매수 직전 (없으면 0)
                        pre_pos = await get_strategy_position(
                            db, account.id, strategy.id, ticker,
                        )
                        if pre_pos is None:
                            pre_qty_snap = Decimal("0")
                            pre_avg_snap = Decimal("0")
                        else:
                            pre_qty_snap = decrypt_decimal(pre_pos.quantity)
                            pre_avg_snap = decrypt_decimal(pre_pos.avg_buy_price)

                        # DB에 PENDING 주문 먼저 기록 (고아 주문 방지)
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
                            status=OrderStatus.PENDING,
                            reason=signal.reason,
                            pre_apply_qty=encrypt_decimal(pre_qty_snap),
                            pre_apply_avg_buy_price=encrypt_decimal(pre_avg_snap),
                        )
                        db.add(order)
                        await db.flush()

                        # KIS 발주
                        order_result = await kis.place_order(
                            side="buy", ticker=ticker, quantity=qty, order_type="market",
                        )
                        order.status = OrderStatus.SUBMITTED
                        order.kis_order_id = order_result.get("order_id")

                        if llm_decision is not None:
                            decision_row.executed = True
                            decision_row.order_id = order.id
                        # Phase 3: 전략 포지션 증가 (신규 ticker일 때만 set에 추가)
                        await apply_buy_fill(
                            db, strategy, ticker, ticker_name, qty_dec, price_dec,
                        )
                        held_tickers.add(ticker)
                        orders_placed += 1
                        today_trade_count += 1
                        available_cash -= order_amount
                        trade_messages.append(
                            f"📈 [매수] {escape_html(ticker_name)}({escape_html(ticker)}) {qty}주 @ {current_price:,.0f}원\n사유: {escape_html(signal.reason)}"
                        )
                    except KISClientError as e:
                        order.status = OrderStatus.REJECTED
                        order.reason = (order.reason or "") + f" | KIS error: {e}"
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

                    # Phase 4: 네팅 — 같은 종목 반대 방향(매수) 주문이 있으면 스킵.
                    if account.allow_netting:
                        opp = await find_opposite_open_order(
                            db, account.id, ticker, OrderSide.SELL,
                        )
                        if opp is not None:
                            skip_msg = (
                                f"매도 스킵(네팅): 같은 종목 반대 방향 주문 존재 — "
                                f"{ticker} / opp_order={opp.id}"
                            )
                            logger.warning(skip_msg)
                            skip_messages.append(skip_msg)
                            continue

                    try:
                        # 폴링 롤백용 pre-state
                        pre_qty_snap = decrypt_decimal(pos.quantity)
                        pre_avg_snap = decrypt_decimal(pos.avg_buy_price)

                        # DB에 PENDING 주문 먼저 기록 (고아 주문 방지)
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
                            status=OrderStatus.PENDING,
                            reason=signal.reason,
                            pre_apply_qty=encrypt_decimal(pre_qty_snap),
                            pre_apply_avg_buy_price=encrypt_decimal(pre_avg_snap),
                        )
                        db.add(order)
                        await db.flush()

                        # KIS 발주
                        order_result = await kis.place_order(
                            side="sell", ticker=ticker, quantity=qty, order_type="market",
                        )
                        order.status = OrderStatus.SUBMITTED
                        order.kis_order_id = order_result.get("order_id")

                        if llm_decision is not None:
                            decision_row.executed = True
                            decision_row.order_id = order.id
                        # Phase 3: 전략 포지션 차감 + 실현손익 누적
                        # 손절 케이스와 동일한 사유로 try/except (회계 정합성 방어).
                        try:
                            realized_delta = await apply_sell_fill(
                                db, strategy, ticker, Decimal(qty),
                                Decimal(str(current_price)),
                            )
                            add_realized_pnl(strategy, realized_delta)
                        except Exception as fill_err:
                            # ValueError(수량부족 등 알려진 비즈니스 예외)만 기록 후 진행.
                            # 그 외(DB/암호화 등)는 critical 로깅 후 re-raise해야 한다 —
                            # 그렇지 않으면 ticker 루프의 외곽 `except Exception`이
                            # 이를 swallow해 회계 오류가 침묵하게 된다.
                            logger.critical(
                                "Signal sell fill apply failed (order persisted): "
                                "kis_order_id=%s ticker=%s qty=%d err=%s",
                                order.kis_order_id, ticker, qty, fill_err,
                            )
                            skip_messages.append(
                                f"🚨 [회계 오류] 시그널 매도는 KIS에서 실행됐으나 내부 포지션 갱신 실패: "
                                f"{ticker} {qty}주 / kis_order_id={order.kis_order_id} / {fill_err}"
                            )
                            if not isinstance(fill_err, ValueError):
                                raise
                        # 시그널 매도는 전량 매도 → set 제거 + 재매수 금지 등록
                        held_tickers.discard(ticker)
                        recently_sold_tickers.add(ticker)
                        orders_placed += 1
                        today_trade_count += 1
                        trade_messages.append(
                            f"📉 [매도] {escape_html(pos.ticker_name)}({escape_html(ticker)}) {qty}주 @ {current_price:,.0f}원\n사유: {escape_html(signal.reason)}"
                        )
                        # 의사결정 결과 백필 (모듈 B/C 학습 데이터)
                        try:
                            sell_avg = decrypt_decimal(pos.avg_buy_price)
                            sig_pnl = (Decimal(str(current_price)) - sell_avg) * Decimal(qty)
                            await backfill_sell_results(
                                db, strategy_id, ticker,
                                Decimal(str(current_price)), sig_pnl,
                            )
                        except Exception:
                            logger.warning(
                                "Decision backfill failed (signal sell): ticker=%s",
                                ticker, exc_info=True,
                            )

                        # 매도 후 킬 스위치 재체크 — 실현PnL 변동으로 한도 초과 가능
                        strategy_realized = get_realized_pnl(strategy)
                        # 매도한 포지션은 제거되었으므로 unrealized 재계산
                        post_positions = await list_strategy_positions(
                            db, account.id, strategy.id,
                        )
                        strategy_unrealized = Decimal("0")
                        for pp in post_positions:
                            pp_qty = decrypt_decimal(pp.quantity)
                            pp_avg = decrypt_decimal(pp.avg_buy_price)
                            pp_kis = kis_holdings.get(pp.ticker)
                            if pp_kis and pp_kis.get("current_price") is not None:
                                pp_cur = Decimal(str(pp_kis["current_price"]))
                                strategy_unrealized += (pp_cur - pp_avg) * pp_qty
                            elif pp.current_price is not None:
                                pp_cur = Decimal(str(pp.current_price))
                                strategy_unrealized += (pp_cur - pp_avg) * pp_qty

                        kill_recheck = risk_mgr.check_kill_switch(
                            strategy_realized, strategy_unrealized, strategy_initial,
                        )
                        if not kill_recheck.allowed:
                            # 전체 비활성화 경로 (초기 킬 스위치와 동일)
                            strategy.is_active = False
                            strategy.is_scheduled = False
                            strategy.killed_at = datetime.now(timezone.utc)
                            strategy.killed_reason = kill_recheck.reason
                            trade_messages.append(
                                "🚨 [킬 스위치 발동] 매도 후 누적 손실 기준 초과 — "
                                "이후 주문 중단"
                            )
                            logger.warning(
                                "Kill switch tripped after sell: %s",
                                kill_recheck.reason,
                            )
                            _kill_switch_tripped = True

                    except KISClientError as e:
                        order.status = OrderStatus.REJECTED
                        logger.error("Sell order failed for %s: %s", ticker, e)

            except Exception:
                logger.exception("Error evaluating ticker %s", ticker)

            # 킬 스위치가 사이클 내에서 발동되면 더 이상 주문하지 않음
            if _kill_switch_tripped:
                break

        # 사이클 내 킬 스위치: 인메모리 스케줄 제거는 db.commit() 이후로 지연
        # (strategy 변경은 위에서 수행, 텔레그램은 아래 사이클 완료 알림에 포함)

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
                    f"⚠️ [포지션 정합성 불일치] 계좌={account.id}\n{escape_html(mismatch_text)}",
                    pre_escaped=True,
                )
            except Exception:
                logger.exception("Failed to send reconciliation mismatch alert")

        # 9. 스케줄 로그 완료
        schedule_log.tickers_evaluated = tickers_evaluated
        schedule_log.orders_placed = orders_placed
        schedule_log.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # 사이클 내 킬 스위치: DB 커밋 성공 후 인메모리 스케줄 제거
        if _kill_switch_tripped:
            try:
                from app.tasks.trading_scheduler import trading_scheduler
                trading_scheduler.remove_schedule(user_id, strategy_id)
            except Exception:
                logger.warning(
                    "Failed to remove in-memory schedule after in-cycle kill switch: "
                    "strategy=%s", strategy_id, exc_info=True,
                )

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
                    + "\n".join(f"- {escape_html(m)}" for m in skip_messages)
                )
            await send_telegram_message("\n\n".join(sections), pre_escaped=True)

    except Exception:
        schedule_log.status = ScheduleLogStatus.ERROR
        import traceback
        schedule_log.error_message = traceback.format_exc()[:2000]
        schedule_log.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    finally:
        await kis.close()

    # Step 6 (모듈 D): 계좌 락 해제 후 임베딩 생성 — CPU-bound encode를 락 밖에서 실행
    for did in pending_embed_ids:
        try:
            await embed_decision(db, did)
        except Exception:
            logger.warning(
                "Embedding creation failed for decision %s (continuing)",
                did, exc_info=True,
            )
    if pending_embed_ids:
        await db.commit()


def _build_portfolio_context(
    available_cash: Decimal,
    total_eval: Decimal,
    positions: list[TradingPosition],
) -> PortfolioContext:
    """LLM 어드바이저에 주입할 포트폴리오 스냅샷.

    DB에 암호화 저장된 quantity/avg_buy_price를 평문으로 풀어 LLM 컨텍스트에
    싣는다. paper 모드 전용 흐름이라 외부로 유출되지 않으며, 본 함수의
    호출자가 LLM 응답까지의 짧은 수명 동안만 메모리에 들고 있는다.
    """
    holdings: list[dict] = []
    for p in positions:
        try:
            qty = decrypt_decimal(p.quantity)
            avg = decrypt_decimal(p.avg_buy_price)
        except Exception as e:
            logger.error(
                "decrypt_decimal 실패 position_id=%s ticker=%s "
                "(quantity/avg_buy_price): %s",
                getattr(p, "id", None), getattr(p, "ticker", None), e,
                exc_info=True,
            )
            continue
        unrealized_pnl_str: str | None = None
        if p.unrealized_pnl:
            try:
                unrealized_pnl_str = str(decrypt_decimal(p.unrealized_pnl))
            except Exception as e:
                logger.error(
                    "decrypt_decimal 실패 position_id=%s ticker=%s "
                    "(unrealized_pnl): %s",
                    getattr(p, "id", None), getattr(p, "ticker", None), e,
                    exc_info=True,
                )
        holdings.append({
            "ticker": p.ticker,
            "ticker_name": p.ticker_name,
            "quantity": str(qty),
            "avg_buy_price": str(avg),
            "current_price": str(p.current_price) if p.current_price is not None else None,
            "unrealized_pnl": unrealized_pnl_str,
        })
    return PortfolioContext(
        cash=available_cash,
        total_eval=total_eval,
        holdings=holdings,
    )


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
