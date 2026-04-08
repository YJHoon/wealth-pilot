"""전략별 자본 관리 — Phase 2 (다중 전략 단일 계좌, 모델 1: Drift 허용).

핵심 공식:
    available = initial_capital + realized_pnl - locked_cash - 현재포지션매입가합계

- locked_cash: 미체결 매수 주문에 묶인 금액 (Phase 2에서는 SUBMITTED 매수 주문 금액)
- 포지션 매입가 합계: 해당 전략 strategy_id로 체결된 매수 주문의 평균매입가 × 보유수량
  (Phase 3에서 positions.strategy_id 격리가 도입되면 단순 SUM으로 대체)

이 모듈은 strategy_id에 묶인 자본만 다룬다. 계좌 전체 잔고는 KIS API + asyncio.Lock
(account_lock)이 별도로 보호한다.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    OrderSide,
    OrderStatus,
    TradingOrder,
    TradingStrategy,
)
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
    encrypt_decimal,
)


def get_initial_capital(strategy: TradingStrategy) -> Decimal:
    """전략의 초기 할당 자본 (None=0)."""
    if strategy.initial_capital is None:
        return Decimal("0")
    return decrypt_decimal(strategy.initial_capital)


def get_realized_pnl(strategy: TradingStrategy) -> Decimal:
    """전략의 누적 실현 손익 (None=0)."""
    val = decrypt_decimal_optional(strategy.realized_pnl)
    return val if val is not None else Decimal("0")


def add_realized_pnl(strategy: TradingStrategy, delta: Decimal) -> Decimal:
    """매도 체결 시 (매도가 - 평균매입가) × 수량 을 누적.

    Returns 갱신 후 누적 실현 손익.
    """
    current = get_realized_pnl(strategy)
    new_total = current + delta
    strategy.realized_pnl = encrypt_decimal(new_total)
    return new_total


async def get_strategy_available_capital(
    db: AsyncSession,
    strategy: TradingStrategy,
) -> Decimal:
    """전략별 가용 자본 계산.

    available = initial_capital + realized_pnl - locked_cash - 포지션매입가합계

    Phase 2에서는 positions가 아직 strategy_id로 격리되지 않았으므로
    `TradingOrder` (BUY, FILLED+SUBMITTED) 누적금을 보유분 근사치로 쓴다.
    Phase 3에서 positions.strategy_id 도입 후 더 정확한 계산으로 교체할 것.
    """
    initial = get_initial_capital(strategy)
    realized = get_realized_pnl(strategy)

    # 해당 전략으로 발주된 주문 전수 조회
    result = await db.execute(
        select(TradingOrder).where(
            TradingOrder.strategy_id == strategy.id,
            TradingOrder.status.in_(
                [OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.PARTIAL]
            ),
        )
    )
    orders = result.scalars().all()

    locked_cash = Decimal("0")  # SUBMITTED 매수 (체결 대기)
    held_cost = Decimal("0")    # FILLED 매수 - FILLED 매도 (잔존 매입원가)

    for o in orders:
        qty = decrypt_decimal(o.quantity)
        price = decrypt_decimal(o.price)
        amount = qty * price
        if o.side == OrderSide.BUY:
            if o.status == OrderStatus.SUBMITTED:
                locked_cash += amount
            else:
                held_cost += amount
        else:  # SELL
            if o.status in (OrderStatus.FILLED, OrderStatus.PARTIAL):
                # 매도 체결 = 보유분 감소. 평균매입가가 아닌 매도가로 차감하는 건
                # 실제 원가 추적이 아니라 근사. Phase 3에서 평균매입가 기반으로 교체.
                held_cost -= amount

    if held_cost < 0:
        held_cost = Decimal("0")

    return initial + realized - locked_cash - held_cost


async def validate_account_allocation(
    db: AsyncSession,
    account_id: UUID,
    new_initial_capital: Decimal,
    account_total_capital: Decimal,
    exclude_strategy_id: UUID | None = None,
) -> tuple[bool, Decimal]:
    """계좌 내 모든 전략의 initial_capital 합계 + 신규 ≤ 계좌 총 자본 검증.

    Returns:
        (allowed, remaining): 통과 여부와 잔여 가용 자본
    """
    stmt = select(TradingStrategy).where(
        TradingStrategy.account_id == account_id,
        TradingStrategy.is_active.is_(True),
    )
    if exclude_strategy_id is not None:
        stmt = stmt.where(TradingStrategy.id != exclude_strategy_id)

    result = await db.execute(stmt)
    strategies = result.scalars().all()

    allocated_sum = sum(
        (get_initial_capital(s) for s in strategies),
        start=Decimal("0"),
    )
    remaining = account_total_capital - allocated_sum
    return new_initial_capital <= remaining, remaining
