"""원클릭 분석·매매 발주 실행기.

승인된 `AnalysisRunItem` 리스트를 받아 종목별 주문을 만들고,
paper/live 모드에 따라 발주 → AdvisoryPosition 갱신 → AnalysisRunItem.order_id
태깅까지 수행한다.

부분 실패 허용 — 한 종목이 실패해도 다음 항목 발주를 시도하고,
결과는 `ExecuteOutcome` 리스트로 반환.

**트랜잭션 경계**:
- 종목별로 독립된 트랜잭션을 commit 한다. 한 종목이 실패해 rollback 되어도
  다른 종목의 영속화에 영향을 주지 않으며, 외부 broker 호출(KIS)의 부수효과가
  먼 미래의 commit 실패로 사라지지 않는다.
- 종목당 commit 지점:
  1) PENDING `TradingOrder` 영속화 후 (broker 호출 전 durability 확보)
  2) broker 호출 결과 + `AdvisoryPosition` 적용 + `AnalysisRunItem.order_id`
     태깅 완료 후
- 라우터는 `run.status` / `completed_at` / 액세스 로그만 별도 commit.

자동매매(`trading_cycle.py`)와 분리된 도메인이므로 TradingPosition은 절대 건드리지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    AnalysisItemAction,
    AnalysisItemDecision,
    AnalysisRunItem,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingAccount,
    TradingMode,
    TradingOrder,
)
from app.services.advisory_position import (
    apply_buy_fill_advisory,
    apply_sell_fill_advisory,
)
from app.services.crypto_service import (
    decrypt_decimal_optional,
    encrypt_decimal,
)

logger = logging.getLogger(__name__)


# (side, ticker, quantity_int, price_int) -> {"order_id": str, "order_date": str}
LiveOrderPlacer = Callable[..., Awaitable[dict]]


@dataclass(slots=True)
class ExecuteOutcome:
    """발주 결과 1건."""

    item_id: UUID
    ticker: str
    action: AnalysisItemAction
    success: bool
    order_id: UUID | None = None
    error_message: str | None = None


def _action_to_side(action: AnalysisItemAction) -> OrderSide:
    if action == AnalysisItemAction.BUY:
        return OrderSide.BUY
    if action == AnalysisItemAction.SELL:
        return OrderSide.SELL
    raise ValueError(f"발주 불가능한 action: {action}")


async def execute_approved_items(
    db: AsyncSession,
    *,
    user_id: UUID,
    account: TradingAccount,
    items: list[AnalysisRunItem],
    place_order: LiveOrderPlacer | None = None,
) -> list[ExecuteOutcome]:
    """승인 항목 발주.

    Args:
        items: APPROVED 상태이며 BUY/SELL action 인 항목만 전달해야 한다.
            HOLD/PENDING/SKIPPED/REJECTED 는 호출자가 사전 필터링.
        place_order: live 모드에서 호출할 KIS 발주 함수. paper 모드면 None 가능.
            테스트에서는 stub 주입.

    동작:
        - 종목별로 독립 트랜잭션 commit. 한 종목 실패가 다음 종목을 막지 않는다.
        - paper 모드: KIS 미호출. ref_price 를 즉시 체결가로 가정해
          AdvisoryPosition 적용 (eager apply 패턴).
        - live 모드: KIS place_order 호출. broker 호출 *전* 에 PENDING 주문을
          commit 해서 후속 commit 실패가 broker fill 을 잃게 만들지 않는다
          (체결 정합성은 fill polling 에서 보정 — trading_cycle 패턴과 동일).
        - AnalysisRunItem.order_id 에 신규 TradingOrder.id 태깅.

    Returns:
        ExecuteOutcome 리스트. 종목별 commit 완료된 상태로 반환된다.
    """
    outcomes: list[ExecuteOutcome] = []
    is_live = account.mode == TradingMode.LIVE

    if is_live and place_order is None:
        raise RuntimeError("live 모드 발주는 place_order 콜백이 필요합니다.")

    for item in items:
        outcome = await _execute_one_item(
            db,
            user_id=user_id,
            account=account,
            item=item,
            is_live=is_live,
            place_order=place_order,
        )
        outcomes.append(outcome)

    return outcomes


async def _execute_one_item(
    db: AsyncSession,
    *,
    user_id: UUID,
    account: TradingAccount,
    item: AnalysisRunItem,
    is_live: bool,
    place_order: LiveOrderPlacer | None,
) -> ExecuteOutcome:
    """종목 1건 발주 — 자체 트랜잭션 commit.

    트랜잭션 분리로:
    - flush 실패 시 세션이 rollback-only 상태가 되어 다음 종목 발주가 깨지는
      문제를 막는다 (rollback 후 새 트랜잭션 자동 시작).
    - broker 호출 직후 결과를 별도 commit 으로 영속화 — 라우터의 후속 commit
      실패가 broker fill 을 미반영 상태로 남기지 않게 한다.
    """
    if item.decision != AnalysisItemDecision.APPROVED:
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, error_message="승인 상태가 아닌 항목입니다.",
        )
    if item.action not in (AnalysisItemAction.BUY, AnalysisItemAction.SELL):
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False,
            error_message=f"발주 불가능한 action: {item.action.value}",
        )

    try:
        ref_price = decrypt_decimal_optional(item.ref_price)
        qty = decrypt_decimal_optional(item.suggested_qty)
    except Exception as e:  # noqa: BLE001
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False,
            error_message=f"가격/수량 복호화 실패: {type(e).__name__}",
        )

    if ref_price is None or ref_price <= 0:
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, error_message="참조 가격이 없습니다.",
        )
    if qty is None or qty <= 0:
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, error_message="제안 수량이 없습니다.",
        )

    # KIS 는 정수 주식만 지원 — 분수 수량은 silent 절사 대신 명시적으로 reject.
    if qty != qty.to_integral_value():
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False,
            error_message=(
                f"분수 수량({qty}) 은 발주할 수 없습니다 (KIS 는 정수 주식만 지원)."
            ),
        )
    int_qty = int(qty)
    if int_qty <= 0:
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, error_message="수량이 1주 미만입니다.",
        )

    side = _action_to_side(item.action)

    # ── (1) PENDING 주문 영속화 + commit (broker 호출 전 durability) ──
    order = TradingOrder(
        user_id=user_id,
        account_id=account.id,
        strategy_id=None,  # advisory 발주는 전략 미연결
        schedule_log_id=None,
        analysis_run_item_id=item.id,
        side=side,
        ticker=item.ticker,
        ticker_name=item.ticker_name,
        quantity=encrypt_decimal(Decimal(int_qty)),
        price=encrypt_decimal(ref_price),
        order_type=OrderType.MARKET,
        status=OrderStatus.PENDING,
        reason=f"[Advisory] {item.reason or ''}"[:1000],
    )
    db.add(order)
    try:
        await db.commit()
    except SQLAlchemyError as e:
        # commit 실패 시 세션은 자동 rollback 상태이지만 명시적으로 호출.
        # 다음 종목 처리 시 새 트랜잭션이 시작된다.
        await db.rollback()
        logger.exception(
            "advisory order persist failed: item=%s ticker=%s",
            item.id, item.ticker,
        )
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False,
            error_message=f"주문 영속화 실패: {type(e).__name__}",
        )

    order_id = order.id  # 이후 commit 실패 경로에서도 보존

    # ── (2) broker 호출 (live) 또는 paper fill ──
    if is_live:
        try:
            kis_result = await place_order(
                side=side.value,
                ticker=item.ticker,
                quantity=int_qty,
                price=0,
                order_type="market",
            )
        except Exception as e:  # noqa: BLE001
            # KIS 발주 실패 — 주문은 REJECTED 로 마킹하고 commit.
            # AdvisoryPosition 은 손대지 않는다.
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)[:1000]
            try:
                await db.commit()
            except SQLAlchemyError:
                await db.rollback()
                logger.exception(
                    "REJECTED commit failed: item=%s ticker=%s",
                    item.id, item.ticker,
                )
            logger.error(
                "advisory live order failed: item=%s ticker=%s err=%s",
                item.id, item.ticker, e,
            )
            return ExecuteOutcome(
                item_id=item.id, ticker=item.ticker, action=item.action,
                success=False, order_id=order_id,
                error_message=f"KIS 발주 실패: {e}",
            )
        order.status = OrderStatus.SUBMITTED
        order.kis_order_id = kis_result.get("order_id")
        order.kis_order_date = kis_result.get("order_date")
    else:
        # paper 모드 — KIS 미호출, 즉시 체결 가정
        order.status = OrderStatus.FILLED
        order.filled_quantity = encrypt_decimal(Decimal(int_qty))
        order.filled_price = encrypt_decimal(ref_price)

    # ── (3) AdvisoryPosition 갱신 (eager apply) + item.order_id 태깅 ──
    try:
        if side == OrderSide.BUY:
            await apply_buy_fill_advisory(
                db,
                user_id=user_id,
                account_id=account.id,
                ticker=item.ticker,
                ticker_name=item.ticker_name,
                fill_qty=Decimal(int_qty),
                fill_price=ref_price,
            )
        else:
            await apply_sell_fill_advisory(
                db,
                account_id=account.id,
                ticker=item.ticker,
                fill_qty=Decimal(int_qty),
                fill_price=ref_price,
            )
    except ValueError as e:
        # 보유분 부족 등 도메인 에러 — 주문은 REJECTED 로 별도 commit.
        await db.rollback()
        order = await db.get(TradingOrder, order_id)
        if order is not None:
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)[:1000]
            try:
                await db.commit()
            except SQLAlchemyError:
                await db.rollback()
        logger.warning(
            "advisory position apply failed: item=%s ticker=%s err=%s",
            item.id, item.ticker, e,
        )
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, order_id=order_id,
            error_message=f"포지션 반영 실패: {e}",
        )
    except Exception as e:  # noqa: BLE001
        # broker 호출 후 포지션 반영이 깨졌다면 회계 어긋남 위험.
        # 후속 reconcile 로 보정하도록 critical 로깅하고 rollback.
        # 주문 자체는 (1) commit 으로 PENDING 상태가 이미 영속화되어 있다.
        await db.rollback()
        logger.critical(
            "advisory position apply unexpected error: "
            "item=%s ticker=%s err=%s",
            item.id, item.ticker, e,
        )
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, order_id=order_id,
            error_message=f"포지션 반영 예외: {type(e).__name__}",
        )

    item.order_id = order_id

    try:
        await db.commit()
    except SQLAlchemyError as e:
        # broker 는 이미 발주 완료. 우리 DB 는 PENDING 만 남고 SUBMITTED/포지션
        # 미반영. fill polling 으로 보정 가능하도록 critical 로깅.
        await db.rollback()
        logger.critical(
            "advisory order/position commit failed: item=%s ticker=%s err=%s",
            item.id, item.ticker, e,
        )
        return ExecuteOutcome(
            item_id=item.id, ticker=item.ticker, action=item.action,
            success=False, order_id=order_id,
            error_message=f"체결 영속화 실패: {type(e).__name__}",
        )

    return ExecuteOutcome(
        item_id=item.id, ticker=item.ticker, action=item.action,
        success=True, order_id=order_id,
    )
