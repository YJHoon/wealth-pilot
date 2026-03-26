"""자동매매 라우터 — 계좌, 전략, 스케줄, 주문, 포지션, 수익률"""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.trading import (
    OrderSide,
    OrderStatus,
    TradingAccount,
    TradingOrder,
    TradingPosition,
    TradingScheduleLog,
    TradingStrategy,
)
from app.models.user import User
from app.schemas.trading import (
    ScheduleStartRequest,
    ScheduleStatusResponse,
    TradingAccountCreate,
    TradingAccountResponse,
    TradingOrderResponse,
    TradingPerformanceResponse,
    TradingPositionResponse,
    TradingStrategyCreate,
    TradingStrategyResponse,
    TradingStrategyUpdate,
    account_to_response,
    order_to_response,
    position_to_response,
    schedule_log_to_summary,
    strategy_to_response,
)
from app.config import settings
from app.services.crypto_service import (
    decrypt_decimal,
    encrypt_decimal,
)
from app.services.kis_client import KISClient, KISClientError
from app.services.security_service import AccessAction, log_access
from app.tasks.trading_scheduler import trading_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["자동매매"])


# ──────────────────────────────────────────────
# 계좌 관리
# ──────────────────────────────────────────────

@router.post("/accounts", response_model=TradingAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_trading_account(
    body: TradingAccountCreate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 인증정보 등록."""
    # 같은 모드의 계좌가 이미 있는지 확인
    existing = await db.execute(
        select(TradingAccount).where(
            TradingAccount.user_id == user.id,
            TradingAccount.mode == body.mode,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"{body.mode.value} 모드 계좌가 이미 등록되어 있습니다.",
        )

    account = TradingAccount(
        user_id=user.id,
        mode=body.mode,
        initial_capital=encrypt_decimal(body.initial_capital),
    )
    db.add(account)

    await log_access(db, user.id, AccessAction.TRADING_ACCOUNT_CREATE, request)
    await db.commit()
    await db.refresh(account)

    return account_to_response(account)


@router.get("/accounts", response_model=list[TradingAccountResponse])
async def list_trading_accounts(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌 목록 조회."""
    result = await db.execute(
        select(TradingAccount).where(
            TradingAccount.user_id == user.id,
        ).order_by(TradingAccount.created_at.desc())
    )
    accounts = result.scalars().all()
    return [account_to_response(a) for a in accounts]


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_trading_account(
    account_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌 비활성화."""
    account = await _get_user_account(db, account_id, user.id)
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

    await log_access(db, user.id, AccessAction.TRADING_ACCOUNT_DELETE, request)
    await db.commit()


@router.get("/accounts/{account_id}/balance")
async def get_account_balance(
    account_id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 실시간 잔고 조회."""
    account = await _get_user_account(db, account_id, user.id)

    kis = KISClient(
        app_key=settings.kis_app_key,
        app_secret=settings.kis_app_secret,
        account_number=settings.kis_account_number,
        account_product_code=settings.kis_account_product_code,
        mode=account.mode,
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
async def create_strategy(
    body: TradingStrategyCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """전략 생성."""
    # 계좌 소유권 확인
    await _get_user_account(db, body.account_id, user.id)

    strategy = TradingStrategy(
        user_id=user.id,
        account_id=body.account_id,
        name=body.name,
        strategy_type=body.strategy_type,
        params_json=body.params_json,
        target_tickers=body.target_tickers,
        interval_minutes=body.interval_minutes,
        market_hours_only=body.market_hours_only,
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

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
async def update_strategy(
    strategy_id: UUID,
    body: TradingStrategyUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """전략 수정."""
    strategy = await _get_user_strategy(db, strategy_id, user.id)

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(strategy, key, value)

    # 스케줄 간격 변경 시 활성 스케줄 갱신
    if "interval_minutes" in update_data and strategy.is_scheduled:
        trading_scheduler.remove_schedule(user.id, strategy.id)
        trading_scheduler.add_schedule(user.id, strategy.id, strategy.interval_minutes)

    await db.commit()
    await db.refresh(strategy)

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
