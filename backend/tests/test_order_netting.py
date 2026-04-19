"""order_netting 서비스 테스트."""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradingAccount,
    TradingMode,
    TradingOrder,
)
from app.models.user import User
from app.services.crypto_service import encrypt_decimal
from app.services.order_netting import find_opposite_open_order


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


async def _place_order(
    db: AsyncSession,
    account_id,
    user_id,
    ticker: str,
    side: OrderSide,
    status: OrderStatus,
):
    order = TradingOrder(
        user_id=user_id,
        account_id=account_id,
        strategy_id=None,
        side=side,
        ticker=ticker,
        ticker_name="",
        quantity=encrypt_decimal(Decimal("1")),
        price=encrypt_decimal(Decimal("1000")),
        order_type=OrderType.MARKET,
        status=status,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@pytest.mark.asyncio
async def test_finds_opposite_pending_sell_for_new_buy(
    db_session, mock_user, account,
):
    await _place_order(
        db_session, account.id, mock_user.id, "005930",
        OrderSide.SELL, OrderStatus.PENDING,
    )
    found = await find_opposite_open_order(
        db_session, account.id, "005930", OrderSide.BUY,
    )
    assert found is not None
    assert found.side == OrderSide.SELL


@pytest.mark.asyncio
async def test_finds_opposite_submitted_buy_for_new_sell(
    db_session, mock_user, account,
):
    await _place_order(
        db_session, account.id, mock_user.id, "005930",
        OrderSide.BUY, OrderStatus.SUBMITTED,
    )
    found = await find_opposite_open_order(
        db_session, account.id, "005930", OrderSide.SELL,
    )
    assert found is not None
    assert found.side == OrderSide.BUY


@pytest.mark.asyncio
async def test_ignores_same_direction_order(db_session, mock_user, account):
    await _place_order(
        db_session, account.id, mock_user.id, "005930",
        OrderSide.BUY, OrderStatus.PENDING,
    )
    found = await find_opposite_open_order(
        db_session, account.id, "005930", OrderSide.BUY,
    )
    assert found is None


@pytest.mark.asyncio
async def test_ignores_filled_or_cancelled(db_session, mock_user, account):
    await _place_order(
        db_session, account.id, mock_user.id, "005930",
        OrderSide.SELL, OrderStatus.FILLED,
    )
    await _place_order(
        db_session, account.id, mock_user.id, "005930",
        OrderSide.SELL, OrderStatus.CANCELLED,
    )
    found = await find_opposite_open_order(
        db_session, account.id, "005930", OrderSide.BUY,
    )
    assert found is None


@pytest.mark.asyncio
async def test_scope_by_ticker(db_session, mock_user, account):
    await _place_order(
        db_session, account.id, mock_user.id, "005930",
        OrderSide.SELL, OrderStatus.PENDING,
    )
    found = await find_opposite_open_order(
        db_session, account.id, "000660", OrderSide.BUY,
    )
    assert found is None


@pytest.mark.asyncio
async def test_account_default_allow_netting_false(db_session, mock_user, account):
    assert account.allow_netting is False
