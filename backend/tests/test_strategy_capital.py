"""strategy_capital 서비스 테스트 — Phase 2."""

import uuid
from decimal import Decimal

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
    TradingPosition,
    TradingStrategy,
)
from app.models.user import User
from app.services.crypto_service import encrypt_decimal
from app.services.strategy_capital import (
    add_realized_pnl,
    get_initial_capital,
    get_realized_pnl,
    get_strategy_available_capital,
    validate_account_allocation,
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
    yield a
    await db_session.delete(a)
    await db_session.commit()


def _new_strategy(user_id, account_id, name, capital):
    return TradingStrategy(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        name=name,
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={},
        target_tickers=[],
        interval_minutes=10,
        initial_capital=encrypt_decimal(Decimal(capital)),
        realized_pnl=encrypt_decimal(Decimal("0")),
    )


@pytest.mark.asyncio
async def test_get_initial_capital_returns_zero_when_none():
    s = TradingStrategy(initial_capital=None)
    assert get_initial_capital(s) == Decimal("0")


@pytest.mark.asyncio
async def test_get_realized_pnl_returns_zero_when_none():
    s = TradingStrategy(realized_pnl=None)
    assert get_realized_pnl(s) == Decimal("0")


@pytest.mark.asyncio
async def test_add_realized_pnl_accumulates():
    s = TradingStrategy(realized_pnl=encrypt_decimal(Decimal("100")))
    total = add_realized_pnl(s, Decimal("50"))
    assert total == Decimal("150")
    assert get_realized_pnl(s) == Decimal("150")
    # 손실
    add_realized_pnl(s, Decimal("-200"))
    assert get_realized_pnl(s) == Decimal("-50")


@pytest.mark.asyncio
async def test_validate_account_allocation_within_budget(
    db_session: AsyncSession, mock_user: User, account: TradingAccount,
):
    s1 = _new_strategy(mock_user.id, account.id, "A", "3000000")
    db_session.add(s1)
    await db_session.commit()

    allowed, remaining = await validate_account_allocation(
        db_session,
        account_id=account.id,
        new_initial_capital=Decimal("4000000"),
        account_total_capital=Decimal("10000000"),
    )
    assert allowed is True
    assert remaining == Decimal("7000000")

    await db_session.delete(s1)
    await db_session.commit()


@pytest.mark.asyncio
async def test_validate_account_allocation_rejects_overflow(
    db_session: AsyncSession, mock_user: User, account: TradingAccount,
):
    s1 = _new_strategy(mock_user.id, account.id, "A", "8000000")
    db_session.add(s1)
    await db_session.commit()

    allowed, remaining = await validate_account_allocation(
        db_session,
        account_id=account.id,
        new_initial_capital=Decimal("3000000"),
        account_total_capital=Decimal("10000000"),
    )
    assert allowed is False
    assert remaining == Decimal("2000000")

    await db_session.delete(s1)
    await db_session.commit()


@pytest.mark.asyncio
async def test_validate_excludes_self_on_update(
    db_session: AsyncSession, mock_user: User, account: TradingAccount,
):
    s1 = _new_strategy(mock_user.id, account.id, "A", "8000000")
    db_session.add(s1)
    await db_session.commit()

    # 자기 자신 제외 → 계좌 전체 10M 가용
    allowed, remaining = await validate_account_allocation(
        db_session,
        account_id=account.id,
        new_initial_capital=Decimal("9000000"),
        account_total_capital=Decimal("10000000"),
        exclude_strategy_id=s1.id,
    )
    assert allowed is True
    assert remaining == Decimal("10000000")

    await db_session.delete(s1)
    await db_session.commit()


@pytest.mark.asyncio
async def test_get_strategy_available_capital_subtracts_positions_and_locked(
    db_session: AsyncSession, mock_user: User, account: TradingAccount,
):
    s = _new_strategy(mock_user.id, account.id, "S", "5000000")
    db_session.add(s)
    await db_session.commit()

    # 보유 포지션 10주 @ 100,000 = 1,000,000원 (held_cost)
    pos = TradingPosition(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        strategy_id=s.id,
        ticker="005930",
        ticker_name="삼성전자",
        quantity=encrypt_decimal(Decimal("10")),
        avg_buy_price=encrypt_decimal(Decimal("100000")),
    )
    # SUBMITTED 매수 500,000원 (locked_cash)
    o2 = TradingOrder(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        strategy_id=s.id,
        side=OrderSide.BUY,
        ticker="000660",
        ticker_name="SK하이닉스",
        quantity=encrypt_decimal(Decimal("5")),
        price=encrypt_decimal(Decimal("100000")),
        order_type=OrderType.MARKET,
        status=OrderStatus.SUBMITTED,
    )
    db_session.add_all([pos, o2])
    await db_session.commit()

    available = await get_strategy_available_capital(db_session, s)
    # 5,000,000 + 0(realized) - 500,000(locked) - 1,000,000(held) = 3,500,000
    assert available == Decimal("3500000")

    await db_session.delete(pos)
    await db_session.delete(o2)
    await db_session.delete(s)
    await db_session.commit()


@pytest.mark.asyncio
async def test_get_available_uses_position_held_cost(
    db_session: AsyncSession, mock_user: User, account: TradingAccount,
):
    """가용 자본 계산이 포지션 기반 held_cost를 정확히 반영하는지 확인."""
    s = _new_strategy(mock_user.id, account.id, "S", "5000000")
    db_session.add(s)
    await db_session.commit()

    # 매도 후 남은 보유: 6주 @ 100,000 = 600,000 (held_cost)
    pos = TradingPosition(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        strategy_id=s.id,
        ticker="005930",
        ticker_name="삼성전자",
        quantity=encrypt_decimal(Decimal("6")),
        avg_buy_price=encrypt_decimal(Decimal("100000")),
    )
    db_session.add(pos)
    await db_session.commit()

    available = await get_strategy_available_capital(db_session, s)
    # 5,000,000 + 0(realized) - 0(locked) - 600,000(held) = 4,400,000
    assert available == Decimal("4400000")

    await db_session.delete(pos)
    await db_session.delete(s)
    await db_session.commit()
