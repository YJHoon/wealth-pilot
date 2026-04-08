"""strategy_position 서비스 테스트 — Phase 3 (전략별 포지션 격리)."""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.models.user import User
from app.services.crypto_service import decrypt_decimal, encrypt_decimal
from app.services.strategy_position import (
    apply_buy_fill,
    apply_sell_fill,
    get_strategy_position,
    list_strategy_positions,
    reconcile_with_kis,
    update_position_market_data,
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


def _new_strategy(user_id, account_id, name):
    return TradingStrategy(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        name=name,
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={},
        target_tickers=[],
        interval_minutes=10,
        initial_capital=encrypt_decimal(Decimal("5000000")),
        realized_pnl=encrypt_decimal(Decimal("0")),
    )


@pytest.mark.asyncio
async def test_buy_creates_position(db_session, mock_user, account):
    s = _new_strategy(mock_user.id, account.id, "S")
    db_session.add(s)
    await db_session.commit()

    pos = await apply_buy_fill(
        db_session, s, "005930", "삼성전자",
        Decimal("10"), Decimal("100000"),
    )
    await db_session.commit()
    await db_session.refresh(pos)

    assert decrypt_decimal(pos.quantity) == Decimal("10")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")
    assert pos.strategy_id == s.id


@pytest.mark.asyncio
async def test_buy_updates_weighted_average(db_session, mock_user, account):
    s = _new_strategy(mock_user.id, account.id, "S")
    db_session.add(s)
    await db_session.commit()

    await apply_buy_fill(
        db_session, s, "005930", "삼성전자", Decimal("10"), Decimal("100000"),
    )
    await apply_buy_fill(
        db_session, s, "005930", "삼성전자", Decimal("10"), Decimal("120000"),
    )
    await db_session.commit()

    pos = await get_strategy_position(db_session, account.id, s.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("20")
    # (10*100000 + 10*120000) / 20 = 110000
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("110000")


@pytest.mark.asyncio
async def test_two_strategies_same_ticker_isolated(db_session, mock_user, account):
    """전략 A와 B가 같은 종목을 보유해도 서로 침범하지 않는다."""
    s_a = _new_strategy(mock_user.id, account.id, "A")
    s_b = _new_strategy(mock_user.id, account.id, "B")
    db_session.add_all([s_a, s_b])
    await db_session.commit()

    await apply_buy_fill(db_session, s_a, "005930", "삼성", Decimal("10"), Decimal("100000"))
    await apply_buy_fill(db_session, s_b, "005930", "삼성", Decimal("5"), Decimal("110000"))
    await db_session.commit()

    pos_a = await get_strategy_position(db_session, account.id, s_a.id, "005930")
    pos_b = await get_strategy_position(db_session, account.id, s_b.id, "005930")
    assert decrypt_decimal(pos_a.quantity) == Decimal("10")
    assert decrypt_decimal(pos_b.quantity) == Decimal("5")
    assert pos_a.id != pos_b.id

    # B 전량 매도해도 A는 그대로
    realized = await apply_sell_fill(
        db_session, s_b, "005930", Decimal("5"), Decimal("130000"),
    )
    await db_session.commit()

    assert realized == (Decimal("130000") - Decimal("110000")) * Decimal("5")
    assert await get_strategy_position(db_session, account.id, s_b.id, "005930") is None
    pos_a_after = await get_strategy_position(db_session, account.id, s_a.id, "005930")
    assert decrypt_decimal(pos_a_after.quantity) == Decimal("10")


@pytest.mark.asyncio
async def test_sell_partial_keeps_avg_price(db_session, mock_user, account):
    s = _new_strategy(mock_user.id, account.id, "S")
    db_session.add(s)
    await db_session.commit()

    await apply_buy_fill(db_session, s, "005930", "삼성", Decimal("10"), Decimal("100000"))
    realized = await apply_sell_fill(
        db_session, s, "005930", Decimal("4"), Decimal("150000"),
    )
    await db_session.commit()

    assert realized == Decimal("200000")  # (150000-100000)*4
    pos = await get_strategy_position(db_session, account.id, s.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("6")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")


@pytest.mark.asyncio
async def test_sell_more_than_holding_raises(db_session, mock_user, account):
    s = _new_strategy(mock_user.id, account.id, "S")
    db_session.add(s)
    await db_session.commit()

    await apply_buy_fill(db_session, s, "005930", "삼성", Decimal("3"), Decimal("100000"))
    with pytest.raises(ValueError, match="exceeds holding"):
        await apply_sell_fill(db_session, s, "005930", Decimal("5"), Decimal("100000"))


@pytest.mark.asyncio
async def test_reconcile_detects_mismatch(db_session, mock_user, account):
    s_a = _new_strategy(mock_user.id, account.id, "A")
    s_b = _new_strategy(mock_user.id, account.id, "B")
    db_session.add_all([s_a, s_b])
    await db_session.commit()

    await apply_buy_fill(db_session, s_a, "005930", "삼성", Decimal("10"), Decimal("100000"))
    await apply_buy_fill(db_session, s_b, "005930", "삼성", Decimal("5"), Decimal("100000"))
    await db_session.commit()

    # KIS가 13주만 보고함 → 2주 부족
    mismatches = await reconcile_with_kis(
        db_session, account.id,
        {"005930": {"quantity": 13, "current_price": 110000}},
    )
    assert len(mismatches) == 1
    assert "005930" in mismatches[0]

    # 일치 케이스
    ok = await reconcile_with_kis(
        db_session, account.id,
        {"005930": {"quantity": 15, "current_price": 110000}},
    )
    assert ok == []


@pytest.mark.asyncio
async def test_update_market_data_applies_to_all_strategies(db_session, mock_user, account):
    s_a = _new_strategy(mock_user.id, account.id, "A")
    s_b = _new_strategy(mock_user.id, account.id, "B")
    db_session.add_all([s_a, s_b])
    await db_session.commit()

    await apply_buy_fill(db_session, s_a, "005930", "삼성", Decimal("10"), Decimal("100000"))
    await apply_buy_fill(db_session, s_b, "005930", "삼성", Decimal("5"), Decimal("120000"))
    await db_session.commit()

    await update_position_market_data(db_session, account.id, "005930", 130000.0)
    await db_session.commit()

    positions = sorted(
        await list_strategy_positions(db_session, account.id, s_a.id)
        + await list_strategy_positions(db_session, account.id, s_b.id),
        key=lambda p: decrypt_decimal(p.avg_buy_price),
    )
    assert all(p.current_price == 130000.0 for p in positions)
    # A: (130000-100000)*10 = 300000
    # B: (130000-120000)*5  = 50000
    assert decrypt_decimal(positions[0].unrealized_pnl) == Decimal("300000")
    assert decrypt_decimal(positions[1].unrealized_pnl) == Decimal("50000")
