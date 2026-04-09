"""주문 체결 폴링 — KIS 실제 체결과 내부 eager apply의 차이를 보정한다.

배경:
trading_cycle은 SUBMITTED 시점에 즉시(낙관적으로) 포지션과 realized_pnl을
ord_qty 기준으로 갱신한다. 실제로는 KIS가 부분체결하거나 거부할 수 있으므로,
이 서비스가 KIS `inquire-daily-ccld`로 차이를 사후 reconcile 한다.

멱등성:
- 절대 타겟 방식으로 보장한다 (델타 누적이 아님).
- _partial_rollback 은 매번 pre_apply_qty / pre_apply_avg_buy_price 스냅샷과
  ord_qty, ord_price, kis_filled 만으로 "이 주문이 kis_filled 만큼만
  체결됐다고 가정한 절대 목표 상태"를 계산해 포지션을 그 값으로 설정한다.
- 따라서 같은 KIS 응답으로 여러 번 폴링해도, 더 큰 kis_filled로 후속 폴링해도
  결과는 항상 "현재 kis_filled가 가리키는 그 상태"로 수렴한다.
- TradingOrder.filled_quantity 는 매 폴링마다 갱신되며, 매도 realized_pnl
  보정에서 "직전 폴링이 적용한 체결량(prev_applied)"의 source로 사용된다
  (감사/표시 + 매도 PnL 보정 멱등성 확보용).

롤백 공식:
매수 주문이 부분체결(kis_filled < ord_qty)된 경우:
- pre = (pre_qty, pre_avg)  ← order 생성 시 스냅샷
- target = (pre_qty + kis_filled, (pre_qty*pre_avg + kis_filled*ord_price)/(pre_qty+kis_filled))
- 현재(eager apply 후) 상태를 target으로 조정한다.

매도 주문이 부분체결된 경우:
- target = (pre_qty - kis_filled, pre_avg)
- realized_pnl 보정: -(ord_price - pre_avg) * (ord_qty - kis_filled)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    OrderSide,
    OrderStatus,
    TradingAccount,
    TradingOrder,
    TradingPosition,
    TradingStrategy,
)
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
    encrypt_decimal,
    encrypt_decimal_optional,
)
from app.services.kis_client import KISClient, KISClientError
from app.services.strategy_capital import add_realized_pnl

logger = logging.getLogger(__name__)


# 주문 후 KIS에 나타나지 않으면 거부/취소로 간주하기까지의 grace period.
# 폴링은 빠르면 같은 사이클 내에 일어나므로 너무 짧으면 정상 접수 직후 주문도
# 잘못 취소 처리될 수 있다.
CANCEL_GRACE_PERIOD = timedelta(minutes=5)


class PollResult(NamedTuple):
    polled: int
    filled: int
    partial: int
    cancelled: int
    errors: list[str]


async def poll_open_orders(
    db: AsyncSession,
    account: TradingAccount,
    kis: KISClient,
) -> PollResult:
    """이 계좌의 SUBMITTED/PARTIAL 상태 주문을 KIS와 reconcile.

    - kis_filled == ord_qty: 변동 없음, 상태 FILLED
    - kis_filled < ord_qty: 부족분 롤백, 상태 PARTIAL
    - KIS에 없음 + grace 경과: 전량 롤백, 상태 CANCELLED
    """
    result = await db.execute(
        select(TradingOrder).where(
            TradingOrder.account_id == account.id,
            TradingOrder.status.in_(
                [OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
            ),
            TradingOrder.kis_order_id.is_not(None),
        )
    )
    open_orders = list(result.scalars().all())
    if not open_orders:
        return PollResult(0, 0, 0, 0, [])

    try:
        kis_orders = await kis.get_order_status()
    except KISClientError as e:
        logger.error("Fill polling failed (KIS query): %s", e)
        return PollResult(len(open_orders), 0, 0, 0, [f"KIS 조회 실패: {e}"])

    by_id = {o["order_id"]: o for o in kis_orders if o.get("order_id")}

    filled = partial = cancelled = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc)

    for order in open_orders:
        try:
            kis_entry = by_id.get(order.kis_order_id or "")
            if kis_entry is None:
                # KIS에 안 보임 → grace period 후 취소 처리.
                # grace_anchor는 항상 order.created_at 기준 — 매 폴링에서
                # last_polled_at을 now로 갱신하면 grace가 무한 연장되어
                # 영원히 취소 처리되지 않으므로 갱신하지 않는다.
                if now - order.created_at < CANCEL_GRACE_PERIOD:
                    continue
                await _full_rollback(db, order)
                order.status = OrderStatus.CANCELLED
                order.last_polled_at = now
                cancelled += 1
                logger.warning(
                    "Order cancelled (not found in KIS after grace): "
                    "kis_order_id=%s ticker=%s",
                    order.kis_order_id, order.ticker,
                )
                continue

            ord_qty = decrypt_decimal(order.quantity)
            kis_filled = Decimal(str(kis_entry.get("filled_quantity", 0)))

            if kis_filled >= ord_qty:
                # 완전 체결
                order.filled_quantity = encrypt_decimal(ord_qty)
                order.filled_price = encrypt_decimal(
                    Decimal(str(kis_entry.get("filled_price") or 0))
                )
                order.status = OrderStatus.FILLED
                order.last_polled_at = now
                filled += 1
            else:
                # 부분 체결 — 부족분 롤백
                shortfall = ord_qty - kis_filled
                await _partial_rollback(db, order, shortfall)
                order.filled_quantity = encrypt_decimal(kis_filled)
                order.filled_price = encrypt_decimal(
                    Decimal(str(kis_entry.get("filled_price") or 0))
                )
                order.status = OrderStatus.PARTIAL
                order.last_polled_at = now
                partial += 1
        except Exception as e:
            logger.exception(
                "Polling reconcile failed for order %s", order.id
            )
            errors.append(f"{order.ticker}: {e}")

    return PollResult(
        polled=len(open_orders),
        filled=filled,
        partial=partial,
        cancelled=cancelled,
        errors=errors,
    )


async def _full_rollback(db: AsyncSession, order: TradingOrder) -> None:
    """ord_qty 전체를 롤백 (취소/거부)."""
    ord_qty = decrypt_decimal(order.quantity)
    await _partial_rollback(db, order, ord_qty)


async def _partial_rollback(
    db: AsyncSession,
    order: TradingOrder,
    shortfall: Decimal,
) -> None:
    """eager apply된 ord_qty 중 shortfall 만큼을 되돌린다.

    매수: position에서 shortfall 차감 → 잔량/평단가 재계산
    매도: position에 shortfall 복원 + realized_pnl 차감
    """
    if shortfall <= 0:
        return

    # 전략이 SET NULL로 끊긴 주문은 포지션 row를 새로 만들 수 없다
    # (TradingPosition.strategy_id NOT NULL). 이 경우 보정/롤백 자체가
    # 의미 없으므로 로깅 후 스킵 — reconcile_with_kis가 후속 사이클에서
    # 합계 불일치를 surface한다.
    if order.strategy_id is None:
        logger.warning(
            "Skip rollback: order.strategy_id is NULL (strategy deleted): "
            "order_id=%s ticker=%s",
            order.id, order.ticker,
        )
        return

    pre_qty = decrypt_decimal_optional(order.pre_apply_qty) or Decimal("0")
    pre_avg = decrypt_decimal_optional(order.pre_apply_avg_buy_price) or Decimal("0")
    ord_qty = decrypt_decimal(order.quantity)
    ord_price = decrypt_decimal(order.price)
    confirmed_filled = ord_qty - shortfall  # 폴링이 확정한 체결 수량
    # 직전 폴링이 보정한 후의 "현재 적용된 체결량". 첫 폴링이면 eager apply가
    # 전량을 적용했으므로 ord_qty.
    prev_applied = decrypt_decimal_optional(order.filled_quantity)
    if prev_applied is None:
        prev_applied = ord_qty

    # 같은 (account, strategy, ticker) 포지션 직접 조회
    pos_result = await db.execute(
        select(TradingPosition).where(
            TradingPosition.account_id == order.account_id,
            TradingPosition.strategy_id == order.strategy_id,
            TradingPosition.ticker == order.ticker,
        )
    )
    pos = pos_result.scalar_one_or_none()

    if order.side == OrderSide.BUY:
        # 목표 상태: pre_qty + confirmed_filled 주
        target_qty = pre_qty + confirmed_filled
        if target_qty <= 0:
            # 매수 전 0 + 전량 취소 → 포지션 row 삭제
            if pos is not None:
                await db.delete(pos)
            return

        # 가중평균: (pre_qty * pre_avg + confirmed_filled * ord_price) / target_qty
        target_avg = (
            (pre_qty * pre_avg + confirmed_filled * ord_price) / target_qty
        )
        if pos is None:
            # 비정상 — eager apply 후엔 반드시 존재해야 함. 복원 시도.
            pos = TradingPosition(
                user_id=order.user_id,
                account_id=order.account_id,
                strategy_id=order.strategy_id,
                ticker=order.ticker,
                ticker_name=order.ticker_name,
                quantity=encrypt_decimal(target_qty),
                avg_buy_price=encrypt_decimal(target_avg),
            )
            db.add(pos)
        else:
            pos.quantity = encrypt_decimal(target_qty)
            pos.avg_buy_price = encrypt_decimal(target_avg)
        return

    # SELL
    # 목표 상태: pre_qty - confirmed_filled 주, pre_avg 유지
    target_qty = pre_qty - confirmed_filled
    if pos is None:
        # eager apply가 0으로 만들어 row가 삭제됐을 수 있음 → 복원
        if target_qty > 0:
            pos = TradingPosition(
                user_id=order.user_id,
                account_id=order.account_id,
                strategy_id=order.strategy_id,
                ticker=order.ticker,
                ticker_name=order.ticker_name,
                quantity=encrypt_decimal(target_qty),
                avg_buy_price=encrypt_decimal(pre_avg),
            )
            db.add(pos)
    else:
        if target_qty <= 0:
            await db.delete(pos)
        else:
            pos.quantity = encrypt_decimal(target_qty)
            # avg_buy_price는 매도로 변하지 않으므로 그대로 유지

    # realized_pnl 보정: "현재 적용된 체결량(prev_applied)"을 confirmed_filled로
    # 맞추는 차이만큼만 빼거나 더한다. delta 누적이 아니라 prev_applied → confirmed_filled
    # 이행이므로, 같은 KIS 응답으로 반복 폴링해도 멱등 (delta = 0).
    if order.strategy_id is not None:
        delta = confirmed_filled - prev_applied  # 음수면 차감
        if delta != 0:
            strategy = await db.get(TradingStrategy, order.strategy_id)
            if strategy is not None:
                add_realized_pnl(strategy, (ord_price - pre_avg) * delta)
