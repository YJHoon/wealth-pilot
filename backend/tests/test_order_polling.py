"""order_polling 서비스 테스트 — fill polling reconcile 로직."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    OrderSide,
    OrderStatus,
    OrderType,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingOrder,
    TradingStrategy,
)
from app.models.user import User
from app.services.crypto_service import decrypt_decimal, encrypt_decimal
from app.services.order_polling import poll_open_orders
from app.services.strategy_position import (
    apply_buy_fill,
    apply_sell_fill,
    get_strategy_position,
)


@pytest_asyncio.fixture
async def account(db_session: AsyncSession, mock_user: User):
    a = TradingAccount(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


@pytest_asyncio.fixture
async def strategy(db_session: AsyncSession, mock_user: User, account):
    s = TradingStrategy(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        name="S",
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={},
        target_tickers=[],
        interval_minutes=10,
        initial_capital=encrypt_decimal(Decimal("5000000")),
        realized_pnl=encrypt_decimal(Decimal("0")),
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _make_kis(orders_payload):
    kis = AsyncMock()
    kis.get_order_status = AsyncMock(return_value=orders_payload)
    return kis


def _new_buy_order(strategy, account, mock_user, qty, price, pre_qty, pre_avg, kis_id="K1"):
    return TradingOrder(
        user_id=mock_user.id,
        account_id=account.id,
        strategy_id=strategy.id,
        side=OrderSide.BUY,
        ticker="005930",
        ticker_name="삼성",
        quantity=encrypt_decimal(Decimal(qty)),
        price=encrypt_decimal(Decimal(price)),
        order_type=OrderType.MARKET,
        status=OrderStatus.SUBMITTED,
        kis_order_id=kis_id,
        pre_apply_qty=encrypt_decimal(Decimal(pre_qty)),
        pre_apply_avg_buy_price=encrypt_decimal(Decimal(pre_avg)),
    )


def _new_sell_order(strategy, account, mock_user, qty, price, pre_qty, pre_avg, kis_id="K2"):
    return TradingOrder(
        user_id=mock_user.id,
        account_id=account.id,
        strategy_id=strategy.id,
        side=OrderSide.SELL,
        ticker="005930",
        ticker_name="삼성",
        quantity=encrypt_decimal(Decimal(qty)),
        price=encrypt_decimal(Decimal(price)),
        order_type=OrderType.MARKET,
        status=OrderStatus.SUBMITTED,
        kis_order_id=kis_id,
        pre_apply_qty=encrypt_decimal(Decimal(pre_qty)),
        pre_apply_avg_buy_price=encrypt_decimal(Decimal(pre_avg)),
    )


@pytest.mark.asyncio
async def test_full_fill_no_position_change(db_session, mock_user, account, strategy):
    """완전 체결: eager apply 결과 그대로, 상태만 FILLED."""
    # Eager apply: 신규 매수 10주 @ 100,000
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    order = _new_buy_order(strategy, account, mock_user, 10, 100000, 0, 0)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([{
        "order_id": "K1", "ticker": "005930", "side": "buy",
        "quantity": 10, "filled_quantity": 10, "filled_price": 100000, "status": "filled",
    }])
    result = await poll_open_orders(db_session, account, kis)
    await db_session.commit()
    await db_session.refresh(order)

    assert result.filled == 1 and result.partial == 0 and result.cancelled == 0
    assert order.status == OrderStatus.FILLED
    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("10")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")


@pytest.mark.asyncio
async def test_partial_buy_recomputes_avg(db_session, mock_user, account, strategy):
    """매수 부분체결: 5주만 체결 → 포지션 5주, 평단가 100,000."""
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    order = _new_buy_order(strategy, account, mock_user, 10, 100000, 0, 0)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([{
        "order_id": "K1", "ticker": "005930", "side": "buy",
        "quantity": 10, "filled_quantity": 5, "filled_price": 100000, "status": "partial",
    }])
    result = await poll_open_orders(db_session, account, kis)
    await db_session.commit()

    assert result.partial == 1
    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("5")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")


@pytest.mark.asyncio
async def test_partial_buy_with_existing_position_avg(db_session, mock_user, account, strategy):
    """기존 보유 10주(@100k) 위에 10주(@120k) 매수 후 5주만 체결.
    pre = (10, 100k), filled = 5 → target qty = 15, avg = (10*100k + 5*120k) / 15 = 106666.67
    """
    # 사전 보유
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    await db_session.commit()
    # eager apply: 추가 10주 @ 120k
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("120000"))
    order = _new_buy_order(strategy, account, mock_user, 10, 120000, 10, 100000)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([{
        "order_id": "K1", "ticker": "005930", "side": "buy",
        "quantity": 10, "filled_quantity": 5, "filled_price": 120000, "status": "partial",
    }])
    await poll_open_orders(db_session, account, kis)
    await db_session.commit()

    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("15")
    expected_avg = (Decimal("10") * Decimal("100000") + Decimal("5") * Decimal("120000")) / Decimal("15")
    assert decrypt_decimal(pos.avg_buy_price) == expected_avg


@pytest.mark.asyncio
async def test_cancelled_buy_full_rollback(db_session, mock_user, account, strategy):
    """KIS에서 주문 사라짐 + grace 경과 → 전량 롤백, 신규 매수면 포지션 삭제."""
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    order = _new_buy_order(strategy, account, mock_user, 10, 100000, 0, 0)
    # grace를 넘기기 위해 created_at을 과거로
    order.last_polled_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([])  # KIS 응답 비어있음
    result = await poll_open_orders(db_session, account, kis)
    await db_session.commit()
    await db_session.refresh(order)

    assert result.cancelled == 1
    assert order.status == OrderStatus.CANCELLED
    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert pos is None


@pytest.mark.asyncio
async def test_cancelled_grace_period_first_poll_skips(db_session, mock_user, account, strategy):
    """KIS에 없어도 grace 이내면 last_polled_at만 찍고 패스."""
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    order = _new_buy_order(strategy, account, mock_user, 10, 100000, 0, 0)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([])
    result = await poll_open_orders(db_session, account, kis)
    await db_session.commit()
    await db_session.refresh(order)

    assert result.cancelled == 0
    assert order.status == OrderStatus.SUBMITTED
    assert order.last_polled_at is not None
    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("10")  # 변동 없음


@pytest.mark.asyncio
async def test_partial_sell_restores_position_and_corrects_pnl(
    db_session, mock_user, account, strategy,
):
    """매도 10주 @ 130k 중 4주만 체결.
    pre = (10, 100k). eager 후: 0주, realized += (130k-100k)*10 = 300k.
    target: (10-4=6주, 100k), realized = (130k-100k)*4 = 120k → -180k 보정.
    """
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    await db_session.commit()
    realized = await apply_sell_fill(db_session, strategy, "005930", Decimal("10"), Decimal("130000"))
    # 전략에 누적
    from app.services.strategy_capital import add_realized_pnl
    add_realized_pnl(strategy, realized)
    order = _new_sell_order(strategy, account, mock_user, 10, 130000, 10, 100000)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([{
        "order_id": "K2", "ticker": "005930", "side": "sell",
        "quantity": 10, "filled_quantity": 4, "filled_price": 130000, "status": "partial",
    }])
    await poll_open_orders(db_session, account, kis)
    await db_session.commit()
    await db_session.refresh(strategy)

    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("6")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")
    # realized: 300k - 180k(보정) = 120k
    assert decrypt_decimal(strategy.realized_pnl) == Decimal("120000")


@pytest.mark.asyncio
async def test_idempotent_repeat_polling(db_session, mock_user, account, strategy):
    """같은 주문에 대해 두 번 polling 해도 결과 동일."""
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    order = _new_buy_order(strategy, account, mock_user, 10, 100000, 0, 0)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([{
        "order_id": "K1", "ticker": "005930", "side": "buy",
        "quantity": 10, "filled_quantity": 5, "filled_price": 100000, "status": "partial",
    }])
    await poll_open_orders(db_session, account, kis)
    await db_session.commit()

    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    qty1 = decrypt_decimal(pos.quantity)

    # 두 번째 polling — 상태가 PARTIAL이라 다시 조회됨. 같은 KIS 응답.
    await poll_open_orders(db_session, account, kis)
    await db_session.commit()

    pos = await get_strategy_position(db_session, account.id, strategy.id, "005930")
    assert decrypt_decimal(pos.quantity) == qty1  # 변동 없음


@pytest.mark.asyncio
async def test_idempotent_repeat_polling_sell_pnl(
    db_session, mock_user, account, strategy,
):
    """매도 부분체결 반복 폴링 — realized_pnl 이중 차감 없음."""
    await apply_buy_fill(db_session, strategy, "005930", "삼성", Decimal("10"), Decimal("100000"))
    await db_session.commit()
    realized = await apply_sell_fill(db_session, strategy, "005930", Decimal("10"), Decimal("130000"))
    from app.services.strategy_capital import add_realized_pnl
    add_realized_pnl(strategy, realized)
    order = _new_sell_order(strategy, account, mock_user, 10, 130000, 10, 100000)
    db_session.add(order)
    await db_session.commit()

    kis = _make_kis([{
        "order_id": "K2", "ticker": "005930", "side": "sell",
        "quantity": 10, "filled_quantity": 4, "filled_price": 130000, "status": "partial",
    }])
    await poll_open_orders(db_session, account, kis)
    await db_session.commit()
    await db_session.refresh(strategy)
    pnl_after_first = decrypt_decimal(strategy.realized_pnl)

    await poll_open_orders(db_session, account, kis)
    await db_session.commit()
    await db_session.refresh(strategy)
    assert decrypt_decimal(strategy.realized_pnl) == pnl_after_first
