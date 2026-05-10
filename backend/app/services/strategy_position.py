"""전략별 포지션 관리 — Phase 3 (다중 전략 단일 계좌, 포지션 격리).

KIS는 전략을 모르므로, 내부 주문 체결 시점에 전략별 포지션을 직접 증감한다.
KIS 잔고는 정합성 검증과 current_price/unrealized_pnl 갱신에만 사용한다.

핵심 함수:
- apply_buy_fill: 매수 체결 시 호출 → 전략 포지션 증가, 평균매입가 가중평균 갱신
- apply_sell_fill: 매도 체결 시 호출 → 전략 포지션 감소, 0 되면 삭제
- get_strategy_position: 전략+종목 보유분 조회
- reconcile_with_kis: Σ(전략 포지션) + Σ(advisory 포지션) vs KIS 실잔고 정합성 체크
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import AdvisoryPosition, TradingPosition, TradingStrategy
from app.services.crypto_service import (
    decrypt_decimal,
    encrypt_decimal,
    encrypt_decimal_optional,
)


async def get_strategy_position(
    db: AsyncSession,
    account_id: UUID,
    strategy_id: UUID,
    ticker: str,
) -> TradingPosition | None:
    """특정 (account, strategy, ticker) 포지션 조회."""
    result = await db.execute(
        select(TradingPosition).where(
            TradingPosition.account_id == account_id,
            TradingPosition.strategy_id == strategy_id,
            TradingPosition.ticker == ticker,
        )
    )
    return result.scalar_one_or_none()


async def list_strategy_positions(
    db: AsyncSession,
    account_id: UUID,
    strategy_id: UUID,
) -> list[TradingPosition]:
    """전략의 모든 보유 포지션 목록."""
    result = await db.execute(
        select(TradingPosition).where(
            TradingPosition.account_id == account_id,
            TradingPosition.strategy_id == strategy_id,
        )
    )
    return list(result.scalars().all())


async def apply_buy_fill(
    db: AsyncSession,
    strategy: TradingStrategy,
    ticker: str,
    ticker_name: str,
    fill_qty: Decimal,
    fill_price: Decimal,
) -> TradingPosition:
    """매수 체결을 전략 포지션에 반영.

    기존 포지션이 있으면 가중평균으로 avg_buy_price 갱신.
    없으면 새 포지션 생성.

    주의: 현재 코드는 SUBMITTED를 체결로 간주하는 단순화 모델을 따른다.
    fill polling 도입(별도 작업) 이후엔 실제 체결 콜백에서만 호출되어야 한다.
    """
    if fill_qty <= 0:
        raise ValueError(f"fill_qty must be positive: {fill_qty}")

    pos = await get_strategy_position(db, strategy.account_id, strategy.id, ticker)

    if pos is None:
        pos = TradingPosition(
            user_id=strategy.user_id,
            account_id=strategy.account_id,
            strategy_id=strategy.id,
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
    # 가중평균 매입가
    new_avg = ((cur_qty * cur_avg) + (fill_qty * fill_price)) / new_qty

    pos.quantity = encrypt_decimal(new_qty)
    pos.avg_buy_price = encrypt_decimal(new_avg)
    if ticker_name and not pos.ticker_name:
        pos.ticker_name = ticker_name
    return pos


async def apply_sell_fill(
    db: AsyncSession,
    strategy: TradingStrategy,
    ticker: str,
    fill_qty: Decimal,
    fill_price: Decimal,
) -> Decimal:
    """매도 체결을 전략 포지션에 반영.

    Returns:
        실현손익 델타 = (fill_price - avg_buy_price) * fill_qty

    포지션이 없거나 보유수량 부족이면 ValueError.
    수량이 0이 되면 포지션 row 삭제.
    """
    if fill_qty <= 0:
        raise ValueError(f"fill_qty must be positive: {fill_qty}")

    pos = await get_strategy_position(db, strategy.account_id, strategy.id, ticker)
    if pos is None:
        raise ValueError(
            f"sell fill on missing position: strategy={strategy.id}, ticker={ticker}"
        )

    cur_qty = decrypt_decimal(pos.quantity)
    if cur_qty < fill_qty:
        raise ValueError(
            f"sell qty exceeds holding: strategy={strategy.id}, ticker={ticker}, "
            f"holding={cur_qty}, sell={fill_qty}"
        )

    avg = decrypt_decimal(pos.avg_buy_price)
    realized_delta = (fill_price - avg) * fill_qty

    new_qty = cur_qty - fill_qty
    if new_qty == 0:
        await db.delete(pos)
    else:
        pos.quantity = encrypt_decimal(new_qty)
        # avg_buy_price는 부분 매도해도 변하지 않음

    return realized_delta


async def update_position_market_data(
    db: AsyncSession,
    account_id: UUID,
    ticker: str,
    current_price: float,
) -> None:
    """KIS에서 가져온 현재가/평가손익을 같은 종목의 모든 전략 포지션에 반영.

    여러 전략이 동일 종목을 보유할 수 있으므로 일괄 업데이트.
    """
    result = await db.execute(
        select(TradingPosition).where(
            TradingPosition.account_id == account_id,
            TradingPosition.ticker == ticker,
        )
    )
    positions = result.scalars().all()
    cp = Decimal(str(current_price))
    for pos in positions:
        pos.current_price = float(current_price)
        qty = decrypt_decimal(pos.quantity)
        avg = decrypt_decimal(pos.avg_buy_price)
        pnl = (cp - avg) * qty
        pos.unrealized_pnl = encrypt_decimal_optional(pnl)


async def reconcile_with_kis(
    db: AsyncSession,
    account_id: UUID,
    kis_holdings: dict[str, dict],
) -> list[str]:
    """KIS 실잔고와 (전략 포지션 합계 + advisory 포지션 합계) 를 비교.

    정합성 식: KIS실잔고(ticker) = Σ TradingPosition(ticker) + Σ AdvisoryPosition(ticker)

    Args:
        kis_holdings: {ticker: {"quantity": int|Decimal, "current_price": ..., ...}}

    Returns:
        불일치 메시지 목록 (ticker별 1줄). 빈 리스트면 정합성 OK.
        메시지에는 strategy/advisory 분해를 포함해 어느 도메인이 어긋났는지 추적 가능.
    """
    # 전략 포지션 합계 (ticker별)
    strat_rows = await db.execute(
        select(TradingPosition).where(TradingPosition.account_id == account_id)
    )
    strat_qty: dict[str, Decimal] = {}
    for pos in strat_rows.scalars().all():
        qty = decrypt_decimal(pos.quantity)
        strat_qty[pos.ticker] = strat_qty.get(pos.ticker, Decimal("0")) + qty

    # advisory 포지션 합계 (ticker별)
    adv_rows = await db.execute(
        select(AdvisoryPosition).where(AdvisoryPosition.account_id == account_id)
    )
    adv_qty: dict[str, Decimal] = {}
    for pos in adv_rows.scalars().all():
        qty = decrypt_decimal(pos.quantity)
        adv_qty[pos.ticker] = adv_qty.get(pos.ticker, Decimal("0")) + qty

    mismatches: list[str] = []
    all_tickers = set(strat_qty.keys()) | set(adv_qty.keys()) | set(kis_holdings.keys())

    # set 은 비결정 순서 → 메시지/로그가 매 실행마다 달라지지 않도록 정렬
    for ticker in sorted(all_tickers):
        strat = strat_qty.get(ticker, Decimal("0"))
        adv = adv_qty.get(ticker, Decimal("0"))
        internal = strat + adv
        kis_raw = kis_holdings.get(ticker, {}).get("quantity", 0)
        kis_qty = Decimal(str(kis_raw))
        if internal != kis_qty:
            mismatches.append(
                f"{ticker}: 전략={strat}, advisory={adv}, 합계={internal} "
                f"vs KIS={kis_qty} (차이={internal - kis_qty})"
            )

    return mismatches
