"""주문 네팅 (Phase 4).

계좌에 `allow_netting=True`가 켜진 경우,
같은 계좌·같은 종목의 반대 방향 PENDING/SUBMITTED 주문이 있으면
신규 주문을 전량 스킵한다 (동시 매수/매도 충돌 방지).

v1은 **전량 스킵** 단순 전략. 수량 기반 부분 네팅은 향후 확장.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import OrderSide, OrderStatus, TradingOrder


async def find_opposite_open_order(
    db: AsyncSession,
    account_id: UUID,
    ticker: str,
    new_side: OrderSide,
) -> TradingOrder | None:
    """계좌 내 같은 종목의 반대 방향 PENDING/SUBMITTED 주문을 찾는다.

    Returns:
        첫 번째 매칭 주문, 없으면 None.
    """
    opposite = OrderSide.SELL if new_side == OrderSide.BUY else OrderSide.BUY
    result = await db.execute(
        select(TradingOrder)
        .where(
            TradingOrder.account_id == account_id,
            TradingOrder.ticker == ticker,
            TradingOrder.side == opposite,
            TradingOrder.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED]),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()
