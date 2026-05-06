"""advisory_position 서비스 테스트 — 원클릭 매매 보유분 격리."""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import AdvisoryPosition, TradingAccount, TradingMode
from app.models.user import User
from app.services.advisory_position import (
    apply_buy_fill_advisory,
    apply_sell_fill_advisory,
    get_advisory_position,
    list_advisory_positions,
    sum_advisory_positions_by_ticker,
    update_advisory_market_data,
)
from app.services.crypto_service import decrypt_decimal, encrypt_decimal


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


@pytest.mark.asyncio
async def test_buy_creates_advisory_position(db_session, mock_user, account):
    pos = await apply_buy_fill_advisory(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        ticker="005930",
        ticker_name="삼성전자",
        fill_qty=Decimal("10"),
        fill_price=Decimal("100000"),
    )
    await db_session.commit()
    await db_session.refresh(pos)

    assert decrypt_decimal(pos.quantity) == Decimal("10")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")
    assert pos.account_id == account.id


@pytest.mark.asyncio
async def test_buy_weighted_average(db_session, mock_user, account):
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("10"),
        fill_price=Decimal("100000"),
    )
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("10"),
        fill_price=Decimal("120000"),
    )
    await db_session.commit()

    pos = await get_advisory_position(db_session, account.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("20")
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("110000")


@pytest.mark.asyncio
async def test_sell_reduces_position(db_session, mock_user, account):
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("10"),
        fill_price=Decimal("100000"),
    )
    await db_session.commit()

    pnl = await apply_sell_fill_advisory(
        db_session, account_id=account.id, ticker="005930",
        fill_qty=Decimal("4"), fill_price=Decimal("110000"),
    )
    await db_session.commit()

    assert pnl == Decimal("40000")  # (110000-100000) * 4
    pos = await get_advisory_position(db_session, account.id, "005930")
    assert decrypt_decimal(pos.quantity) == Decimal("6")
    # 평균단가는 부분 매도해도 변하지 않음
    assert decrypt_decimal(pos.avg_buy_price) == Decimal("100000")


@pytest.mark.asyncio
async def test_sell_to_zero_deletes_row(db_session, mock_user, account):
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("3"),
        fill_price=Decimal("100000"),
    )
    await db_session.commit()
    await apply_sell_fill_advisory(
        db_session, account_id=account.id, ticker="005930",
        fill_qty=Decimal("3"), fill_price=Decimal("110000"),
    )
    await db_session.commit()

    pos = await get_advisory_position(db_session, account.id, "005930")
    assert pos is None


@pytest.mark.asyncio
async def test_sell_more_than_holding_raises(db_session, mock_user, account):
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("3"),
        fill_price=Decimal("100000"),
    )
    await db_session.commit()
    with pytest.raises(ValueError, match="exceeds advisory holding"):
        await apply_sell_fill_advisory(
            db_session, account_id=account.id, ticker="005930",
            fill_qty=Decimal("5"), fill_price=Decimal("100000"),
        )


@pytest.mark.asyncio
async def test_sell_missing_position_raises(db_session, account):
    with pytest.raises(ValueError, match="missing advisory position"):
        await apply_sell_fill_advisory(
            db_session, account_id=account.id, ticker="005930",
            fill_qty=Decimal("1"), fill_price=Decimal("100000"),
        )


@pytest.mark.asyncio
async def test_update_market_data(db_session, mock_user, account):
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("10"),
        fill_price=Decimal("100000"),
    )
    await db_session.commit()

    await update_advisory_market_data(
        db_session, account_id=account.id, ticker="005930",
        current_price=120000.0,
    )
    await db_session.commit()

    pos = await get_advisory_position(db_session, account.id, "005930")
    assert pos.current_price == 120000.0
    assert decrypt_decimal(pos.unrealized_pnl) == Decimal("200000")


@pytest.mark.asyncio
async def test_sum_by_ticker(db_session, mock_user, account):
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("10"),
        fill_price=Decimal("100000"),
    )
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="000660", ticker_name="하이닉스", fill_qty=Decimal("5"),
        fill_price=Decimal("130000"),
    )
    await db_session.commit()

    sums = await sum_advisory_positions_by_ticker(db_session, account.id)
    assert sums == {"005930": Decimal("10"), "000660": Decimal("5")}


@pytest.mark.asyncio
async def test_unique_constraint_account_ticker(db_session, mock_user, account):
    """(account_id, ticker) UNIQUE — apply_buy_fill_advisory가 항상 단일 row로 누적되는지."""
    for _ in range(3):
        await apply_buy_fill_advisory(
            db_session, user_id=mock_user.id, account_id=account.id,
            ticker="005930", ticker_name="삼성", fill_qty=Decimal("1"),
            fill_price=Decimal("100000"),
        )
    await db_session.commit()
    rows = await db_session.execute(
        select(AdvisoryPosition).where(
            AdvisoryPosition.account_id == account.id,
            AdvisoryPosition.ticker == "005930",
        )
    )
    positions = list(rows.scalars().all())
    assert len(positions) == 1
    assert decrypt_decimal(positions[0].quantity) == Decimal("3")
