"""자동매매 라우터 — 계좌, 전략, 스케줄, 주문, 포지션, 수익률"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rate_limit import limiter
from app.dependencies.auth import get_current_active_user
from app.models.trading import (
    AdaptiveRule,
    OrderSide,
    OrderStatus,
    OrderType,
    StrategyType,
    TradingAccount,
    TradingDecision,
    TradingOrder,
    TradingPosition,
    TradingScheduleLog,
    TradingStrategy,
)
from app.models.user import User
from app.schemas.trading import (
    AdaptiveRuleResponse,
    AdaptiveRuleUpdate,
    ScheduleStartRequest,
    ScheduleStatusResponse,
    TradingAccountCreate,
    TradingAccountResponse,
    TradingDecisionResponse,
    TradingOrderResponse,
    TradingPerformanceResponse,
    TradingPositionResponse,
    TradingStrategyCreate,
    TradingStrategyResponse,
    TradingStrategyUpdate,
    account_to_response,
    adaptive_rule_to_response,
    decision_to_response,
    order_to_response,
    position_to_response,
    schedule_log_to_summary,
    strategy_to_response,
)
from app.config import settings
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_value,
    encrypt_decimal,
)
from app.services.account_lock import acquire_account_lock, clear_account_lock
from app.services.kis_client import KISClient, KISClientError
from app.services.risk_manager import RiskManager
from app.services.strategy_capital import (
    get_initial_capital,
    get_realized_pnl,
    get_strategy_available_capital,
    validate_account_allocation,
)
from app.services.strategy_position import (
    apply_buy_fill,
    apply_sell_fill,
    get_strategy_position,
    list_strategy_positions,
)
from app.services.security_service import AccessAction, log_access
from app.tasks.trading_scheduler import trading_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["자동매매"])


# ──────────────────────────────────────────────
# 계좌 관리
# ──────────────────────────────────────────────

@router.post("/accounts", response_model=TradingAccountResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("100/minute")
async def create_trading_account(
    body: TradingAccountCreate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 인증정보 등록 — KIS API에서 잔액을 조회하여 초기자금 자동 설정."""
    # 동일 (user, mode) 계좌가 이미 활성 상태로 존재하면 KIS 호출 전에 즉시 차단
    existing_result = await db.execute(
        select(TradingAccount).where(
            TradingAccount.user_id == user.id,
            TradingAccount.mode == body.mode,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None and existing.is_active:
        raise HTTPException(
            status_code=409,
            detail=f"{body.mode.value} 모드 계좌가 이미 등록되어 있습니다.",
        )

    # KIS API에서 현재 잔액 조회 (DB 세션 사용 전에 외부 호출 완료)
    creds = settings.kis_credentials(body.mode.value)
    kis = KISClient(
        app_key=creds["app_key"],
        app_secret=creds["app_secret"],
        account_number=creds["account_number"],
        account_product_code=creds["account_product_code"],
        mode=body.mode,
    )
    try:
        balance = await kis.get_balance()
        initial_capital = balance["cash"] + balance["total_eval"]
    except KISClientError as e:
        raise HTTPException(
            status_code=502,
            detail=f"KIS API 잔액 조회에 실패했습니다: {e}",
        ) from None
    finally:
        await kis.close()

    if existing is not None:
        # 비활성 계좌 재활성화 (잔액 갱신)
        existing.is_active = True
        existing.initial_capital = encrypt_decimal(initial_capital)
        existing.cash_balance = encrypt_decimal(balance["cash"])
        account = existing
    else:
        account = TradingAccount(
            user_id=user.id,
            mode=body.mode,
            initial_capital=encrypt_decimal(initial_capital),
            cash_balance=encrypt_decimal(balance["cash"]),
        )
        db.add(account)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        orig_msg = str(getattr(e, "orig", e)).lower()
        if "uq_trading_account_user_mode" in orig_msg:
            raise HTTPException(
                status_code=409,
                detail=f"{body.mode.value} 모드 계좌가 이미 등록되어 있습니다.",
            ) from None
        raise
    await db.refresh(account)
    response = account_to_response(account)

    # 액세스 로그 (실패해도 계좌 생성은 보존)
    try:
        await log_access(db, user.id, AccessAction.TRADING_ACCOUNT_CREATE, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_ACCOUNT_CREATE access logging failed", exc_info=True)

    return response


@router.get("/accounts", response_model=list[TradingAccountResponse])
@limiter.limit("100/minute")
async def list_trading_accounts(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌 목록 조회."""
    result = await db.execute(
        select(TradingAccount).where(
            TradingAccount.user_id == user.id,
            TradingAccount.is_active.is_(True),
        ).order_by(TradingAccount.created_at.desc())
    )
    accounts = result.scalars().all()
    response = [account_to_response(a) for a in accounts]

    try:
        await log_access(db, user.id, AccessAction.TRADING_ACCOUNT_LIST, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_ACCOUNT_LIST access logging failed", exc_info=True)

    return response


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("100/minute")
async def deactivate_trading_account(
    account_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌 비활성화."""
    account = await _get_user_account(db, account_id, user.id)

    # 진행 중인 매매 사이클과 직렬화: 락 안에서 비활성화 + 스케줄 제거.
    # _run_cycle은 락을 획득한 직후 account.is_active를 재검증하므로,
    # 비활성화 이후에 진입한 사이클은 즉시 스킵된다.
    async with acquire_account_lock(account_id):
        account.is_active = False

        # 해당 계좌의 모든 활성 스케줄 중지
        result = await db.execute(
            select(TradingStrategy).where(
                TradingStrategy.account_id == account_id,
                TradingStrategy.is_scheduled.is_(True),
            )
        )
        for strategy in result.scalars().all():
            strategy.is_scheduled = False
            trading_scheduler.remove_schedule(user.id, strategy.id)

        await db.commit()

    # 락 해제 후 레지스트리에서 제거 (refcount=0이고 unlocked일 때만)
    await clear_account_lock(account_id)

    # 액세스 로그 (실패해도 비활성화는 보존)
    try:
        await log_access(db, user.id, AccessAction.TRADING_ACCOUNT_DELETE, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_ACCOUNT_DELETE access logging failed", exc_info=True)


@router.get("/accounts/{account_id}/balance")
@limiter.limit("100/minute")
async def get_account_balance(
    account_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 실시간 잔고 조회."""
    account = await _get_user_account(db, account_id, user.id)

    # 액세스 로그 커밋 (활성 여부 검사 전에 시도 자체를 기록)
    try:
        await log_access(db, user.id, AccessAction.TRADING_BALANCE_INQUIRY, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_BALANCE_INQUIRY access logging failed", exc_info=True)

    if not account.is_active:
        raise HTTPException(status_code=400, detail="비활성화된 계좌입니다.")
    account_mode = account.mode
    mode_value = account_mode.value

    creds = settings.kis_credentials(mode_value)
    kis = KISClient(
        app_key=creds["app_key"],
        app_secret=creds["app_secret"],
        account_number=creds["account_number"],
        account_product_code=creds["account_product_code"],
        mode=account_mode,
    )
    try:
        balance = await kis.get_balance()
        return balance
    except KISClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    finally:
        await kis.close()


# ──────────────────────────────────────────────
# 전략 관리
# ──────────────────────────────────────────────

@router.post("/strategies", response_model=TradingStrategyResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("100/minute")
async def create_strategy(
    body: TradingStrategyCreate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """전략 생성.

    Phase 2: initial_capital(전략별 할당금)을 받아 계좌 가용 자본 내인지 검증.
    합산 초과 시 400 반환.
    """
    # 계좌 소유권 확인
    account = await _get_user_account(db, body.account_id, user.id)

    # 계좌 총 자본 (현재는 initial_capital 기준 — 추후 KIS 잔고 동기화 시 cash_balance 사용 가능)
    account_total = decrypt_decimal(account.initial_capital)

    allowed, remaining = await validate_account_allocation(
        db,
        account_id=body.account_id,
        new_initial_capital=body.initial_capital,
        account_total_capital=account_total,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"전략 할당 자본 초과: 신규 {body.initial_capital:,.0f}원 / "
                f"잔여 {remaining:,.0f}원 (계좌 총 {account_total:,.0f}원)"
            ),
        )

    strategy = TradingStrategy(
        user_id=user.id,
        account_id=body.account_id,
        name=body.name,
        strategy_type=body.strategy_type,
        params_json=body.params_json,
        target_tickers=body.target_tickers,
        interval_minutes=body.interval_minutes,
        market_hours_only=body.market_hours_only,
        initial_capital=encrypt_decimal(body.initial_capital),
        realized_pnl=encrypt_decimal(Decimal("0")),
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    try:
        await log_access(db, user.id, AccessAction.TRADING_STRATEGY_CREATE, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_STRATEGY_CREATE access logging failed", exc_info=True)

    return strategy_to_response(strategy)


@router.get("/strategies", response_model=list[TradingStrategyResponse])
async def list_strategies(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """전략 목록 조회."""
    result = await db.execute(
        select(TradingStrategy).where(
            TradingStrategy.user_id == user.id,
            TradingStrategy.is_active.is_(True),
        ).order_by(TradingStrategy.created_at.desc())
    )
    return [strategy_to_response(s) for s in result.scalars().all()]


@router.put("/strategies/{strategy_id}", response_model=TradingStrategyResponse)
@limiter.limit("100/minute")
async def update_strategy(
    strategy_id: UUID,
    body: TradingStrategyUpdate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """전략 수정."""
    strategy = await _get_user_strategy(db, strategy_id, user.id)

    update_data = body.model_dump(exclude_unset=True)

    # initial_capital 변경 시 계좌 할당 재검증 + 암호화
    if "initial_capital" in update_data:
        new_capital = update_data.pop("initial_capital")
        if new_capital is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="initial_capital은 null일 수 없습니다. 변경하지 않으려면 필드를 생략하세요.",
            )
        account = await _get_user_account(db, strategy.account_id, user.id)
        account_total = decrypt_decimal(account.initial_capital)
        allowed, remaining = await validate_account_allocation(
            db,
            account_id=strategy.account_id,
            new_initial_capital=new_capital,
            account_total_capital=account_total,
            exclude_strategy_id=strategy.id,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"전략 할당 자본 초과: 신규 {new_capital:,.0f}원 / "
                    f"잔여 {remaining:,.0f}원 (자기 자신 제외)"
                ),
            )
        strategy.initial_capital = encrypt_decimal(new_capital)

    for key, value in update_data.items():
        setattr(strategy, key, value)

    # 스케줄 간격 변경 시 활성 스케줄 갱신
    if "interval_minutes" in update_data and strategy.is_scheduled:
        trading_scheduler.remove_schedule(user.id, strategy.id)
        trading_scheduler.add_schedule(user.id, strategy.id, strategy.interval_minutes)

    await db.commit()
    await db.refresh(strategy)

    try:
        await log_access(db, user.id, AccessAction.TRADING_STRATEGY_UPDATE, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_STRATEGY_UPDATE access logging failed", exc_info=True)

    return strategy_to_response(strategy)


# ──────────────────────────────────────────────
# 스케줄 관리
# ──────────────────────────────────────────────

@router.post("/schedule/start", status_code=status.HTTP_200_OK)
async def start_schedule(
    body: ScheduleStartRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """스케줄 시작 — 크론 잡 등록."""
    strategy = await _get_user_strategy(db, body.strategy_id, user.id)

    if strategy.is_scheduled:
        raise HTTPException(status_code=409, detail="이미 스케줄이 실행 중입니다.")

    # 계좌 활성 확인
    account = await _get_user_account(db, strategy.account_id, user.id)
    if not account.is_active:
        raise HTTPException(status_code=400, detail="비활성화된 계좌입니다.")

    strategy.is_scheduled = True
    trading_scheduler.add_schedule(user.id, strategy.id, strategy.interval_minutes)

    await log_access(db, user.id, AccessAction.TRADING_SCHEDULE_START, request)
    await db.commit()

    await send_telegram_message(
        f"🤖 [자동매매 스케줄 시작]\n"
        f"전략: {strategy.name}\n"
        f"간격: {strategy.interval_minutes}분\n"
        f"모드: {account.mode.value}"
    )

    return {"message": "스케줄이 시작되었습니다.", "strategy_id": str(strategy.id)}


@router.post("/schedule/stop", status_code=status.HTTP_200_OK)
async def stop_schedule(
    body: ScheduleStartRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """스케줄 중지 — 크론 잡 해제."""
    strategy = await _get_user_strategy(db, body.strategy_id, user.id)

    if not strategy.is_scheduled:
        raise HTTPException(status_code=409, detail="실행 중인 스케줄이 없습니다.")

    strategy.is_scheduled = False
    trading_scheduler.remove_schedule(user.id, strategy.id)

    await log_access(db, user.id, AccessAction.TRADING_SCHEDULE_STOP, request)
    await db.commit()

    await send_telegram_message(f"🛑 [자동매매 스케줄 중지]\n전략: {strategy.name}")

    return {"message": "스케줄이 중지되었습니다.", "strategy_id": str(strategy.id)}


@router.get("/schedule/status", response_model=ScheduleStatusResponse)
async def get_schedule_status(
    strategy_id: UUID = Query(...),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """스케줄 상태 조회."""
    strategy = await _get_user_strategy(db, strategy_id, user.id)

    # 최근 실행 로그
    log_result = await db.execute(
        select(TradingScheduleLog).where(
            TradingScheduleLog.strategy_id == strategy_id,
        ).order_by(TradingScheduleLog.executed_at.desc()).limit(1)
    )
    last_log = log_result.scalar_one_or_none()

    next_run = trading_scheduler.get_next_run_time(user.id, strategy_id)

    return ScheduleStatusResponse(
        is_active=strategy.is_scheduled,
        strategy_id=strategy.id,
        interval_minutes=strategy.interval_minutes,
        next_run_at=next_run,
        last_run=schedule_log_to_summary(last_log) if last_log else None,
    )


@router.post("/schedule/run-now", status_code=status.HTTP_200_OK)
async def run_cycle_now(
    body: ScheduleStartRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 즉시 실행 (테스트/디버깅용)."""
    strategy = await _get_user_strategy(db, body.strategy_id, user.id)
    account = await _get_user_account(db, strategy.account_id, user.id)

    if not account.is_active:
        raise HTTPException(status_code=400, detail="비활성화된 계좌입니다.")

    await log_access(db, user.id, AccessAction.TRADING_MANUAL_RUN, request)
    await db.commit()

    # 비동기로 사이클 실행
    from app.tasks.trading_cycle import execute_trading_cycle
    import asyncio
    asyncio.create_task(execute_trading_cycle(str(user.id), str(strategy.id)))

    return {"message": "매매 사이클이 시작되었습니다.", "strategy_id": str(strategy.id)}


# ──────────────────────────────────────────────
# 주문 이력
# ──────────────────────────────────────────────

@router.get("/orders", response_model=list[TradingOrderResponse])
async def list_orders(
    account_id: UUID | None = None,
    side: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """주문 이력 조회 (페이지네이션)."""
    query = select(TradingOrder).where(TradingOrder.user_id == user.id)

    if account_id:
        query = query.where(TradingOrder.account_id == account_id)
    if side:
        query = query.where(TradingOrder.side == side)
    if status_filter:
        query = query.where(TradingOrder.status == status_filter)

    query = query.order_by(TradingOrder.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)

    return [order_to_response(o) for o in result.scalars().all()]


# ──────────────────────────────────────────────
# 포지션
# ──────────────────────────────────────────────

@router.get("/positions", response_model=list[TradingPositionResponse])
async def list_positions(
    account_id: UUID | None = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 포지션 조회."""
    query = select(TradingPosition).where(TradingPosition.user_id == user.id)
    if account_id:
        query = query.where(TradingPosition.account_id == account_id)

    result = await db.execute(query)
    return [position_to_response(p) for p in result.scalars().all()]


# ──────────────────────────────────────────────
# 의사결정 승인 (Step 3)
# ──────────────────────────────────────────────

# 매수 사전 검증 시 수수료/슬리피지 버퍼 (trading_cycle과 동일)
_BUY_FEE_BUFFER = Decimal("1.005")


@router.get("/decisions/pending", response_model=list[TradingDecisionResponse])
@limiter.limit("100/minute")
async def list_pending_decisions(
    request: Request,
    strategy_id: UUID | None = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """승인 대기 중인 LLM 의사결정 목록."""
    now = datetime.now(timezone.utc)

    # 만료된 pending 건 lazy 처리
    expired_result = await db.execute(
        select(TradingDecision).where(
            TradingDecision.user_id == user.id,
            TradingDecision.approval_status == "pending",
            TradingDecision.approval_expires_at <= now,
        )
    )
    expired_rows = expired_result.scalars().all()
    for expired in expired_rows:
        expired.approval_status = "expired"
        expired.blocked_reason = "승인 시간 만료"
    if expired_rows:
        await db.commit()

    # 유효한 pending 조회
    query = (
        select(TradingDecision)
        .where(
            TradingDecision.user_id == user.id,
            TradingDecision.approval_status == "pending",
            TradingDecision.approval_expires_at > now,
        )
        .order_by(TradingDecision.created_at.desc())
    )
    if strategy_id:
        query = query.where(TradingDecision.strategy_id == strategy_id)

    result = await db.execute(query)
    decisions = [decision_to_response(d) for d in result.scalars().all()]

    try:
        await log_access(db, user.id, AccessAction.TRADING_DECISION_LIST, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_DECISION_LIST access logging failed", exc_info=True)

    return decisions


@router.post("/decisions/{decision_id}/approve")
@limiter.limit("100/minute")
async def approve_decision(
    decision_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """승인 대기 결정을 승인하고 발주."""
    decision = await db.get(TradingDecision, decision_id)
    if not decision or decision.user_id != user.id:
        raise HTTPException(status_code=404, detail="결정을 찾을 수 없습니다.")

    if decision.approval_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"현재 상태({decision.approval_status})에서는 승인할 수 없습니다.",
        )

    # 만료 체크
    now = datetime.now(timezone.utc)
    if decision.approval_expires_at and decision.approval_expires_at <= now:
        decision.approval_status = "expired"
        decision.blocked_reason = "승인 시간 만료"
        await db.commit()
        raise HTTPException(status_code=410, detail="승인 시간이 만료되었습니다.")

    # 전략/계좌 검증
    strategy = await db.get(TradingStrategy, decision.strategy_id)
    account = await db.get(TradingAccount, decision.account_id)
    if not strategy or not strategy.is_active:
        decision.approval_status = "rejected"
        decision.blocked_reason = "전략 비활성화"
        await db.commit()
        raise HTTPException(status_code=400, detail="전략이 비활성화되었습니다.")
    if not account or not account.is_active:
        decision.approval_status = "rejected"
        decision.blocked_reason = "계좌 비활성화"
        await db.commit()
        raise HTTPException(status_code=400, detail="계좌가 비활성화되었습니다.")

    # KIS 클라이언트 생성
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

    order = None
    try:
      async with acquire_account_lock(account.id):
        # ── 락 내부 상태 재검증 (TOCTOU 방지) ──
        await db.refresh(decision)
        await db.refresh(strategy)
        await db.refresh(account)

        now_lock = datetime.now(timezone.utc)
        if decision.approval_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"현재 상태({decision.approval_status})에서는 승인할 수 없습니다.",
            )
        if decision.approval_expires_at and decision.approval_expires_at <= now_lock:
            decision.approval_status = "expired"
            decision.blocked_reason = "승인 시간 만료"
            await db.commit()
            raise HTTPException(status_code=410, detail="승인 시간이 만료되었습니다.")
        if not strategy.is_active:
            decision.approval_status = "rejected"
            decision.blocked_reason = "전략 비활성화"
            await db.commit()
            raise HTTPException(status_code=400, detail="전략이 비활성화되었습니다.")
        if not account.is_active:
            decision.approval_status = "rejected"
            decision.blocked_reason = "계좌 비활성화"
            await db.commit()
            raise HTTPException(status_code=400, detail="계좌가 비활성화되었습니다.")

        # 최신 시세 조회
        price_info = await kis.get_current_price(decision.ticker)
        current_price = Decimal(str(price_info["price"]))
        ticker_name = price_info.get("name", "")

        risk_mgr = RiskManager.from_params(strategy.params_json)

        # ── 공통 안전장치 체크 (trading_cycle과 동일) ──
        # 킬 스위치
        positions = await list_strategy_positions(db, account.id, strategy.id)
        strategy_realized = get_realized_pnl(strategy)
        strategy_unrealized = Decimal("0")
        for pos in positions:
            if pos.unrealized_pnl:
                strategy_unrealized += decrypt_decimal(pos.unrealized_pnl)
        strategy_initial = get_initial_capital(strategy)

        kill_check = risk_mgr.check_kill_switch(
            strategy_realized, strategy_unrealized, strategy_initial,
        )
        if not kill_check.allowed:
            decision.approval_status = "rejected"
            decision.blocked_reason = kill_check.reason
            await db.commit()
            raise HTTPException(status_code=400, detail=kill_check.reason)

        # 일일 손실 한도 + 일일 거래 횟수
        from datetime import timedelta
        KST = timezone(timedelta(hours=9))
        today_start = datetime.now(KST).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_start_utc = today_start.astimezone(timezone.utc)

        today_sell_result = await db.execute(
            select(TradingOrder).where(
                TradingOrder.strategy_id == strategy.id,
                TradingOrder.side == OrderSide.SELL,
                TradingOrder.status.in_([OrderStatus.FILLED, OrderStatus.SUBMITTED]),
                TradingOrder.created_at >= today_start_utc,
            )
        )
        today_realized_pnl = Decimal("0")
        for sell_ord in today_sell_result.scalars().all():
            if sell_ord.pre_apply_avg_buy_price:
                s_price = decrypt_decimal(sell_ord.price)
                s_qty = decrypt_decimal(sell_ord.quantity)
                s_avg = decrypt_decimal(sell_ord.pre_apply_avg_buy_price)
                today_realized_pnl += (s_price - s_avg) * s_qty

        daily_loss_check = risk_mgr.check_daily_loss(today_realized_pnl)
        if not daily_loss_check.allowed:
            decision.approval_status = "rejected"
            decision.blocked_reason = daily_loss_check.reason
            await db.commit()
            raise HTTPException(status_code=400, detail=daily_loss_check.reason)

        today_count_result = await db.execute(
            select(func.count()).select_from(TradingOrder).where(
                TradingOrder.strategy_id == strategy.id,
                TradingOrder.status.in_([
                    OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.PARTIAL,
                ]),
                TradingOrder.created_at >= today_start_utc,
            )
        )
        today_trade_count = today_count_result.scalar() or 0
        daily_trades_check = risk_mgr.check_daily_trades(today_trade_count)
        if not daily_trades_check.allowed:
            decision.approval_status = "rejected"
            decision.blocked_reason = daily_trades_check.reason
            await db.commit()
            raise HTTPException(status_code=400, detail=daily_trades_check.reason)

        if decision.action == "buy":
            balance = await kis.get_balance()
            available_cash = balance["cash"]
            total_eval = balance["total_eval"] + available_cash

            # 수량 결정: LLM 제안 수량 우선, 없으면 포지션 사이징
            qty = 0
            if decision.suggested_quantity:
                qty = int(decrypt_decimal(decision.suggested_quantity))

            # 포지션 사이징으로 최대 허용 수량 산출 + 비중 제약 적용
            max_qty = risk_mgr.calculate_position_size(
                available_cash, total_eval, current_price,
            )
            if qty <= 0:
                qty = max_qty
            elif max_qty > 0:
                qty = min(qty, max_qty)  # suggested_quantity가 비중 제약 초과 시 트림

            if qty <= 0:
                decision.approval_status = "rejected"
                decision.blocked_reason = "매수 가능 수량 0"
                await db.commit()
                raise HTTPException(status_code=400, detail="매수 가능 수량이 없습니다.")

            order_amount = current_price * Decimal(qty)
            required_cash = order_amount * _BUY_FEE_BUFFER

            # check_can_buy (최대 종목 수 + 단일 종목 비중)
            held_tickers = {p.ticker for p in positions}
            effective_count = (
                len(held_tickers) if decision.ticker in held_tickers
                else len(held_tickers) + 1
            )
            buy_check = risk_mgr.check_can_buy(total_eval, order_amount, effective_count)
            if not buy_check.allowed:
                decision.approval_status = "rejected"
                decision.blocked_reason = buy_check.reason
                await db.commit()
                raise HTTPException(status_code=400, detail=buy_check.reason)

            if available_cash < required_cash:
                decision.approval_status = "rejected"
                decision.blocked_reason = (
                    f"예수금 부족: {available_cash:,.0f} < {required_cash:,.0f}"
                )
                await db.commit()
                raise HTTPException(status_code=400, detail=decision.blocked_reason)

            strategy_available = await get_strategy_available_capital(db, strategy)
            if strategy_available < order_amount:
                decision.approval_status = "rejected"
                decision.blocked_reason = (
                    f"전략 가용자본 부족: {strategy_available:,.0f} < {order_amount:,.0f}"
                )
                await db.commit()
                raise HTTPException(status_code=400, detail=decision.blocked_reason)

            # KIS 발주
            order_result = await kis.place_order(
                side="buy", ticker=decision.ticker, quantity=qty, order_type="market",
            )
            # 폴링 롤백용 pre-state
            pre_pos = await get_strategy_position(
                db, account.id, strategy.id, decision.ticker,
            )
            pre_qty = decrypt_decimal(pre_pos.quantity) if pre_pos else Decimal("0")
            pre_avg = decrypt_decimal(pre_pos.avg_buy_price) if pre_pos else Decimal("0")

            order = TradingOrder(
                user_id=user.id,
                account_id=account.id,
                strategy_id=strategy.id,
                side=OrderSide.BUY,
                ticker=decision.ticker,
                ticker_name=ticker_name,
                quantity=encrypt_decimal(Decimal(qty)),
                price=encrypt_decimal(current_price),
                order_type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                kis_order_id=order_result.get("order_id"),
                reason=decision.reason,
                pre_apply_qty=encrypt_decimal(pre_qty),
                pre_apply_avg_buy_price=encrypt_decimal(pre_avg),
            )
            db.add(order)
            await apply_buy_fill(
                db, strategy, decision.ticker, ticker_name,
                Decimal(qty), current_price,
            )

        elif decision.action == "sell":
            pos = await get_strategy_position(
                db, account.id, strategy.id, decision.ticker,
            )
            if not pos:
                decision.approval_status = "rejected"
                decision.blocked_reason = "보유 포지션 없음"
                await db.commit()
                raise HTTPException(status_code=400, detail="보유 포지션이 없습니다.")

            qty = int(decrypt_decimal(pos.quantity))
            if qty <= 0:
                decision.approval_status = "rejected"
                decision.blocked_reason = "보유 수량 0"
                await db.commit()
                raise HTTPException(status_code=400, detail="보유 수량이 0입니다.")

            # 폴링 롤백용 pre-state
            pre_qty = decrypt_decimal(pos.quantity)
            pre_avg = decrypt_decimal(pos.avg_buy_price)

            order_result = await kis.place_order(
                side="sell", ticker=decision.ticker, quantity=qty, order_type="market",
            )
            order = TradingOrder(
                user_id=user.id,
                account_id=account.id,
                strategy_id=strategy.id,
                side=OrderSide.SELL,
                ticker=decision.ticker,
                ticker_name=pos.ticker_name,
                quantity=encrypt_decimal(Decimal(qty)),
                price=encrypt_decimal(current_price),
                order_type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                kis_order_id=order_result.get("order_id"),
                reason=decision.reason,
                pre_apply_qty=encrypt_decimal(pre_qty),
                pre_apply_avg_buy_price=encrypt_decimal(pre_avg),
            )
            db.add(order)
            from app.services.strategy_capital import add_realized_pnl
            realized_delta = await apply_sell_fill(
                db, strategy, decision.ticker, Decimal(qty), current_price,
            )
            add_realized_pnl(strategy, realized_delta)

        else:
            decision.approval_status = "rejected"
            decision.blocked_reason = f"승인 불가 action: {decision.action}"
            await db.commit()
            raise HTTPException(status_code=400, detail=decision.blocked_reason)

        # 공통: 상태 갱신
        decision.approval_status = "approved"
        decision.executed = True
        await db.flush()
        decision.order_id = order.id
        await db.commit()

    except KISClientError as e:
        decision.blocked_reason = f"KIS 발주 실패: {e}"
        decision.approval_status = "rejected"
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e)) from None
    finally:
        await kis.close()

    try:
        await send_telegram_message(
            f"✅ [승인 발주] {decision.ticker} {decision.action} "
            f"{qty}주 @ {current_price:,.0f}원"
        )
    except Exception:
        logger.warning("Approval telegram alert failed", exc_info=True)

    try:
        await log_access(db, user.id, AccessAction.TRADING_DECISION_APPROVE, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_DECISION_APPROVE access logging failed", exc_info=True)

    return {"message": "승인 완료", "order_id": str(order.id)}


@router.post("/decisions/{decision_id}/reject")
@limiter.limit("100/minute")
async def reject_decision(
    decision_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """승인 대기 결정을 거부."""
    decision = await db.get(TradingDecision, decision_id)
    if not decision or decision.user_id != user.id:
        raise HTTPException(status_code=404, detail="결정을 찾을 수 없습니다.")

    if decision.approval_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"현재 상태({decision.approval_status})에서는 거부할 수 없습니다.",
        )

    decision.approval_status = "rejected"
    decision.blocked_reason = "사용자 거부"
    await db.commit()

    try:
        await log_access(db, user.id, AccessAction.TRADING_DECISION_REJECT, request)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("TRADING_DECISION_REJECT access logging failed", exc_info=True)

    return {"message": "거부 완료"}


# ──────────────────────────────────────────────
# 수익률
# ──────────────────────────────────────────────

@router.get("/performance", response_model=TradingPerformanceResponse)
async def get_performance(
    account_id: UUID = Query(...),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """수익률 요약."""
    account = await _get_user_account(db, account_id, user.id)

    # 체결된 매도 주문 조회 (수익 계산)
    sell_orders_result = await db.execute(
        select(TradingOrder).where(
            TradingOrder.account_id == account_id,
            TradingOrder.side == OrderSide.SELL,
            TradingOrder.status == OrderStatus.FILLED,
        )
    )
    sell_orders = sell_orders_result.scalars().all()

    total_trades = len(sell_orders)
    winning = 0
    losing = 0
    total_realized_pnl = Decimal("0")

    for order in sell_orders:
        filled_price = decrypt_decimal(order.filled_price) if order.filled_price else Decimal("0")
        price = decrypt_decimal(order.price)
        qty = decrypt_decimal(order.quantity)
        pnl = (filled_price - price) * qty
        total_realized_pnl += pnl
        if pnl > 0:
            winning += 1
        elif pnl < 0:
            losing += 1

    # 미실현 손익
    positions_result = await db.execute(
        select(TradingPosition).where(TradingPosition.account_id == account_id)
    )
    total_unrealized = Decimal("0")
    current_value = Decimal("0")
    for pos in positions_result.scalars().all():
        if pos.unrealized_pnl:
            total_unrealized += decrypt_decimal(pos.unrealized_pnl)
        if pos.current_price:
            qty = decrypt_decimal(pos.quantity)
            current_value += Decimal(str(pos.current_price)) * qty

    initial_capital = decrypt_decimal(account.initial_capital)
    total_value = current_value + total_realized_pnl
    return_rate = (total_value - initial_capital) / initial_capital * 100 if initial_capital > 0 else Decimal("0")

    win_rate = Decimal(winning) / Decimal(total_trades) * 100 if total_trades > 0 else Decimal("0")

    return TradingPerformanceResponse(
        total_trades=total_trades,
        winning_trades=winning,
        losing_trades=losing,
        win_rate=win_rate,
        total_realized_pnl=total_realized_pnl,
        total_unrealized_pnl=total_unrealized,
        initial_capital=initial_capital,
        current_value=total_value,
        return_rate=return_rate,
    )


# ──────────────────────────────────────────────
# Adaptive Rules (Step 4: 모듈 C)
# ──────────────────────────────────────────────

@router.get(
    "/strategies/{strategy_id}/adaptive-rules",
    response_model=list[AdaptiveRuleResponse],
)
@limiter.limit("100/minute")
async def list_adaptive_rules(
    request: Request,
    strategy_id: UUID,
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """전략별 adaptive rules 목록 조회."""
    strategy = await _get_user_strategy(db, strategy_id, user.id)
    await log_access(db, user.id, AccessAction.ADAPTIVE_RULE_LIST, request)
    from app.services.adaptive_rules import list_rules
    rules = await list_rules(db, strategy.id, active_only=active_only)
    return [adaptive_rule_to_response(r) for r in rules]


@router.put(
    "/adaptive-rules/{rule_id}",
    response_model=AdaptiveRuleResponse,
)
@limiter.limit("100/minute")
async def update_adaptive_rule(
    request: Request,
    rule_id: UUID,
    body: AdaptiveRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """규칙 활성/비활성 토글."""
    rule = await db.get(AdaptiveRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")
    # 소유권 검증: 규칙 → 전략 → 사용자
    strategy = await db.get(TradingStrategy, rule.strategy_id)
    if strategy is None or strategy.user_id != user.id:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")
    rule.is_active = body.is_active
    await db.commit()
    await db.refresh(rule)
    await log_access(db, user.id, AccessAction.ADAPTIVE_RULE_UPDATE, request)
    return adaptive_rule_to_response(rule)


@router.post(
    "/strategies/{strategy_id}/meta-analysis",
    response_model=list[AdaptiveRuleResponse],
)
@limiter.limit("10/minute")
async def trigger_meta_analysis(
    request: Request,
    strategy_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """수동 메타 분석 트리거 (디버그/테스트용)."""
    strategy = await _get_user_strategy(db, strategy_id, user.id)
    if strategy.strategy_type != StrategyType.LLM_ADVISOR:
        raise HTTPException(
            status_code=400,
            detail="메타 분석은 LLM 어드바이저 전략에서만 실행할 수 있습니다.",
        )
    await log_access(db, user.id, AccessAction.META_ANALYSIS_TRIGGER, request)
    from app.services.adaptive_rules import run_weekly_meta_analysis
    created = await run_weekly_meta_analysis(db, strategy)
    await db.commit()
    return [adaptive_rule_to_response(r) for r in created]


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

async def _get_user_account(db: AsyncSession, account_id: UUID, user_id: UUID) -> TradingAccount:
    result = await db.execute(
        select(TradingAccount).where(
            TradingAccount.id == account_id,
            TradingAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="매매 계좌를 찾을 수 없습니다.")
    return account


async def _get_user_strategy(db: AsyncSession, strategy_id: UUID, user_id: UUID) -> TradingStrategy:
    result = await db.execute(
        select(TradingStrategy).where(
            TradingStrategy.id == strategy_id,
            TradingStrategy.user_id == user_id,
            TradingStrategy.is_active.is_(True),
        )
    )
    strategy = result.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다.")
    return strategy


# 임포트 for send_telegram_message in endpoints
from app.services.alert_service import send_telegram_message
