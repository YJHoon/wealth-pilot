"""원클릭 분석·매매 (Advisory) 포지션 관리.

자동매매 `TradingPosition`과 완전히 분리된 수동 매매 보유분을 관리한다.
정합성 식: KIS실잔고(ticker) = Σ TradingPosition(ticker) + AdvisoryPosition(ticker)

`strategy_position.py` 와 동일한 호출 규약을 따른다 — 호출자가 체결 시점에
`apply_*_fill_advisory` 를 호출해 포지션을 가/감산한다.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import AdvisoryPosition
from app.services.crypto_service import (
    decrypt_decimal,
    encrypt_decimal,
    encrypt_decimal_optional,
)


async def get_advisory_position(
    db: AsyncSession,
    account_id: UUID,
    ticker: str,
) -> AdvisoryPosition | None:
    """(account, ticker) 수동 보유분 조회."""
    result = await db.execute(
        select(AdvisoryPosition).where(
            AdvisoryPosition.account_id == account_id,
            AdvisoryPosition.ticker == ticker,
        )
    )
    return result.scalar_one_or_none()


async def list_advisory_positions(
    db: AsyncSession,
    account_id: UUID,
) -> list[AdvisoryPosition]:
    """계좌의 모든 수동 보유 포지션."""
    result = await db.execute(
        select(AdvisoryPosition).where(AdvisoryPosition.account_id == account_id)
    )
    return list(result.scalars().all())


async def apply_buy_fill_advisory(
    db: AsyncSession,
    user_id: UUID,
    account_id: UUID,
    ticker: str,
    ticker_name: str,
    fill_qty: Decimal,
    fill_price: Decimal,
) -> AdvisoryPosition:
    """원클릭 매수 체결을 AdvisoryPosition에 반영.

    기존 포지션이 있으면 가중평균으로 avg_buy_price 갱신, 없으면 신규 생성.
    `strategy_position.apply_buy_fill` 과 같은 의미를 갖되 advisory 도메인 전용.
    """
    if fill_qty <= 0:
        raise ValueError(f"fill_qty must be positive: {fill_qty}")

    pos = await get_advisory_position(db, account_id, ticker)

    if pos is None:
        pos = AdvisoryPosition(
            user_id=user_id,
            account_id=account_id,
            ticker=ticker,
            ticker_name=ticker_name,
            quantity=encrypt_decimal(fill_qty),
            avg_buy_price=encrypt_decimal(fill_price),
        )
        db.add(pos)
        return pos

    cur_qty = decrypt_decimal(pos.quantity)
    cur_avg = decrypt_decimal(pos.avg_buy_price)
    new_qty = cur_qty + fill_qty
    new_avg = ((cur_qty * cur_avg) + (fill_qty * fill_price)) / new_qty

    pos.quantity = encrypt_decimal(new_qty)
    pos.avg_buy_price = encrypt_decimal(new_avg)
    if ticker_name and not pos.ticker_name:
        pos.ticker_name = ticker_name
    return pos


async def apply_sell_fill_advisory(
    db: AsyncSession,
    account_id: UUID,
    ticker: str,
    fill_qty: Decimal,
    fill_price: Decimal,
) -> Decimal:
    """원클릭 매도 체결을 AdvisoryPosition에 반영.

    Returns:
        실현손익 델타 = (fill_price - avg_buy_price) * fill_qty

    포지션이 없거나 보유수량 부족이면 ValueError.
    수량이 0이 되면 row 삭제.

    **중요**: advisory가 매도할 수 있는 건 자기가 보유한 분량(=AdvisoryPosition)뿐.
    전략 보유분은 후보풀 단계에서 차단된다 — 여기서 다시 검증 안 해도 됨.
    """
    if fill_qty <= 0:
        raise ValueError(f"fill_qty must be positive: {fill_qty}")

    pos = await get_advisory_position(db, account_id, ticker)
    if pos is None:
        raise ValueError(
            f"sell fill on missing advisory position: "
            f"account={account_id}, ticker={ticker}"
        )

    cur_qty = decrypt_decimal(pos.quantity)
    if cur_qty < fill_qty:
        raise ValueError(
            f"sell qty exceeds advisory holding: account={account_id}, "
            f"ticker={ticker}, holding={cur_qty}, sell={fill_qty}"
        )

    avg = decrypt_decimal(pos.avg_buy_price)
    realized_delta = (fill_price - avg) * fill_qty

    new_qty = cur_qty - fill_qty
    if new_qty == 0:
        await db.delete(pos)
    else:
        pos.quantity = encrypt_decimal(new_qty)

    return realized_delta


async def update_advisory_market_data(
    db: AsyncSession,
    account_id: UUID,
    ticker: str,
    current_price: float,
) -> None:
    """현재가/평가손익을 advisory 포지션에 반영. (account, ticker) UNIQUE 이므로 1행."""
    pos = await get_advisory_position(db, account_id, ticker)
    if pos is None:
        return
    cp = Decimal(str(current_price))
    pos.current_price = float(cp)
    qty = decrypt_decimal(pos.quantity)
    avg = decrypt_decimal(pos.avg_buy_price)
    pnl = (cp - avg) * qty
    pos.unrealized_pnl = encrypt_decimal_optional(pnl)


async def sum_advisory_positions_by_ticker(
    db: AsyncSession,
    account_id: UUID,
) -> dict[str, Decimal]:
    """ticker별 advisory 보유수량 합산 (reconcile용)."""
    result = await db.execute(
        select(AdvisoryPosition).where(AdvisoryPosition.account_id == account_id)
    )
    out: dict[str, Decimal] = {}
    for pos in result.scalars().all():
        out[pos.ticker] = out.get(pos.ticker, Decimal("0")) + decrypt_decimal(
            pos.quantity
        )
    return out
