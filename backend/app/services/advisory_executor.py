"""원클릭 분석·매매 발주 실행기.

승인된 `AnalysisRunItem` 리스트를 받아 종목별 주문을 만들고,
paper/live 모드에 따라 발주 → AdvisoryPosition 갱신 → AnalysisRunItem.order_id
태깅까지 수행한다.

호출자는 라우터(`/execute`)이며, run.status, error_message, completed_at은
이 함수가 갱신하지 않는다(라우터 책임). 부분 실패 허용 — 한 종목이
실패해도 다음 항목 발주를 시도하고, 결과는 `ExecuteOutcome` 리스트로 반환.

자동매매(`trading_cycle.py`)와 분리된 도메인이므로 TradingPosition은 절대 건드리지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable
from uuid import UUID

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
    decrypt_decimal,
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
        - 각 항목을 독립 트랜잭션 단위로 처리. 종목 실패가 다른 종목을 막지 않게
          per-item 에서 발생한 ValueError/Exception은 outcome.success=False 로
          마킹하고 계속 진행한다.
        - paper 모드: KIS 미호출. ref_price 를 즉시 체결가로 가정해
          AdvisoryPosition 적용 (eager apply 패턴).
        - live 모드: KIS place_order 호출 → 즉시 ref_price 로 AdvisoryPosition
          적용 (체결 폴링은 별도 워크플랜에서 advisory 도메인에 연결 예정).
        - AnalysisRunItem.order_id 에 신규 TradingOrder.id 태깅.

    Returns:
        ExecuteOutcome 리스트. 호출자가 commit 책임을 진다.
    """
    outcomes: list[ExecuteOutcome] = []
    is_live = account.mode == TradingMode.LIVE

    if is_live and place_order is None:
        raise RuntimeError("live 모드 발주는 place_order 콜백이 필요합니다.")

    for item in items:
        if item.decision != AnalysisItemDecision.APPROVED:
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message="승인 상태가 아닌 항목입니다.",
            ))
            continue
        if item.action not in (AnalysisItemAction.BUY, AnalysisItemAction.SELL):
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message=f"발주 불가능한 action: {item.action.value}",
            ))
            continue

        try:
            ref_price = decrypt_decimal_optional(item.ref_price)
            qty = decrypt_decimal_optional(item.suggested_qty)
        except Exception as e:  # noqa: BLE001
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message=f"가격/수량 복호화 실패: {type(e).__name__}",
            ))
            continue

        if ref_price is None or ref_price <= 0:
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message="참조 가격이 없습니다.",
            ))
            continue
        if qty is None or qty <= 0:
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message="제안 수량이 없습니다.",
            ))
            continue

        # 정수 주식 수량으로 변환 (KIS는 정수만 지원)
        int_qty = int(qty)
        if int_qty <= 0:
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message="수량이 정수 1주 미만입니다.",
            ))
            continue

        side = _action_to_side(item.action)

        # 1) DB 에 PENDING 주문 먼저 — 고아 주문 방지
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
            await db.flush()
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "advisory order persist failed: item=%s ticker=%s",
                item.id, item.ticker,
            )
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                error_message=f"주문 기록 실패: {type(e).__name__}",
            ))
            continue

        # 2) 발주 (live 만 KIS 호출, paper 는 즉시 fill 가정)
        if is_live:
            try:
                kis_result = await place_order(
                    side=side.value,
                    ticker=item.ticker,
                    quantity=int_qty,
                    price=0,
                    order_type="market",
                )
                order.status = OrderStatus.SUBMITTED
                order.kis_order_id = kis_result.get("order_id")
                order.kis_order_date = kis_result.get("order_date")
            except Exception as e:  # noqa: BLE001
                # KIS 발주 실패 — 주문은 REJECTED로 마킹하고 outcome 실패.
                # AdvisoryPosition 은 손대지 않는다.
                order.status = OrderStatus.REJECTED
                order.error_message = str(e)[:1000]
                logger.error(
                    "advisory live order failed: item=%s ticker=%s err=%s",
                    item.id, item.ticker, e,
                )
                outcomes.append(ExecuteOutcome(
                    item_id=item.id,
                    ticker=item.ticker,
                    action=item.action,
                    success=False,
                    order_id=order.id,
                    error_message=f"KIS 발주 실패: {e}",
                ))
                continue
        else:
            # paper 모드 — KIS 미호출, 즉시 체결 가정
            order.status = OrderStatus.FILLED
            order.filled_quantity = encrypt_decimal(Decimal(int_qty))
            order.filled_price = encrypt_decimal(ref_price)

        # 3) AdvisoryPosition 갱신 (eager apply)
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
            # 체결 적용에 성공했고 paper 면 이미 FILLED, live 면 SUBMITTED 유지.
        except ValueError as e:
            # 보유분 부족 등 정상적인 도메인 에러 — 주문은 REJECTED.
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)[:1000]
            logger.warning(
                "advisory position apply failed: item=%s ticker=%s err=%s",
                item.id, item.ticker, e,
            )
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                order_id=order.id,
                error_message=f"포지션 반영 실패: {e}",
            ))
            continue
        except Exception as e:  # noqa: BLE001
            # KIS 호출 후 포지션 반영이 실패한 시점은 위험 — live 모드에선 회계 어긋남.
            # 호출자가 reconcile 로 보정하도록 critical 로깅.
            order.error_message = (
                f"포지션 반영 예외 (회계 점검 필요): {type(e).__name__}: {e}"
            )[:1000]
            logger.critical(
                "advisory position apply unexpected error: "
                "item=%s ticker=%s err=%s",
                item.id, item.ticker, e,
            )
            outcomes.append(ExecuteOutcome(
                item_id=item.id,
                ticker=item.ticker,
                action=item.action,
                success=False,
                order_id=order.id,
                error_message=f"포지션 반영 예외: {type(e).__name__}",
            ))
            continue

        # 4) item 에 order_id 태깅
        item.order_id = order.id

        outcomes.append(ExecuteOutcome(
            item_id=item.id,
            ticker=item.ticker,
            action=item.action,
            success=True,
            order_id=order.id,
        ))

    return outcomes
