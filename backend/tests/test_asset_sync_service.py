"""KIS 잔고 → Asset 동기화 서비스 테스트.

`asset_sync_service.sync_kis_balance` 와 `close_kis_assets_for_account` 의
핵심 동작 — 멱등성, SOLD 마킹, manual/KIS 공존, realized_pnl 계산 — 을 검증.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetSource, AssetStatus, AssetType, Currency
from app.models.trading import TradingAccount, TradingMode
from app.models.user import User
from app.services.asset_sync_service import (
    close_kis_assets_for_account,
    sync_kis_balance,
)
from app.services.crypto_service import decrypt_decimal, encrypt_decimal


@pytest_asyncio.fixture
async def kis_account(db_session: AsyncSession, mock_user: User):
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


def _balance(holdings=None, cash="0"):
    return {
        "cash": Decimal(cash),
        "total_eval": Decimal("0"),
        "total_pnl": Decimal("0"),
        "holdings": holdings or [],
    }


def _holding(ticker, name, qty, avg, current=None):
    h = {
        "ticker": ticker,
        "name": name,
        "quantity": int(qty),
        "avg_price": Decimal(str(avg)),
    }
    if current is not None:
        h["current_price"] = Decimal(str(current))
    return h


async def _active_kis_assets(db: AsyncSession, account_id):
    result = await db.execute(
        select(Asset).where(
            Asset.trading_account_id == account_id,
            Asset.source == AssetSource.KIS,
            Asset.status == AssetStatus.ACTIVE,
        )
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_sync_creates_holdings_and_cash(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    balance = _balance(
        holdings=[_holding("005930", "삼성전자", 10, "70000", "75000")],
        cash="500000",
    )
    result = await sync_kis_balance(db_session, kis_account, balance)
    await db_session.commit()

    assert result.upserted_holdings == 1
    assert result.upserted_cash == 1
    assert result.closed == 0

    rows = await _active_kis_assets(db_session, kis_account.id)
    assert len(rows) == 2
    stock = next(a for a in rows if a.type == AssetType.DOMESTIC_STOCK)
    cash = next(a for a in rows if a.type == AssetType.CASH)
    assert stock.external_ticker == "005930"
    assert decrypt_decimal(stock.quantity) == Decimal("10")
    assert decrypt_decimal(stock.purchase_price) == Decimal("70000")
    assert stock.current_price == Decimal("75000")
    assert decrypt_decimal(cash.quantity) == Decimal("500000")
    assert cash.currency == Currency.KRW


@pytest.mark.asyncio
async def test_sync_is_idempotent(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    balance = _balance(
        holdings=[_holding("005930", "삼성전자", 10, "70000", "75000")],
        cash="500000",
    )
    await sync_kis_balance(db_session, kis_account, balance)
    await db_session.commit()
    await sync_kis_balance(db_session, kis_account, balance)
    await db_session.commit()

    rows = await _active_kis_assets(db_session, kis_account.id)
    # 같은 잔고를 두 번 sync해도 행이 늘어나지 않음 (보유종목 1 + 현금 1)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_sync_updates_existing_holding_quantity_and_price(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    first = _balance(
        holdings=[_holding("005930", "삼성전자", 10, "70000", "75000")],
        cash="500000",
    )
    await sync_kis_balance(db_session, kis_account, first)
    await db_session.commit()

    second = _balance(
        holdings=[_holding("005930", "삼성전자", 15, "71000", "80000")],
        cash="200000",
    )
    await sync_kis_balance(db_session, kis_account, second)
    await db_session.commit()

    rows = await _active_kis_assets(db_session, kis_account.id)
    stock = next(a for a in rows if a.type == AssetType.DOMESTIC_STOCK)
    cash = next(a for a in rows if a.type == AssetType.CASH)
    assert decrypt_decimal(stock.quantity) == Decimal("15")
    assert decrypt_decimal(stock.purchase_price) == Decimal("71000")
    assert stock.current_price == Decimal("80000")
    assert decrypt_decimal(cash.quantity) == Decimal("200000")


@pytest.mark.asyncio
async def test_disappeared_holding_marked_sold_with_pnl(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    initial = _balance(
        holdings=[_holding("005930", "삼성전자", 10, "70000", "75000")],
        cash="500000",
    )
    await sync_kis_balance(db_session, kis_account, initial)
    await db_session.commit()

    empty = _balance(holdings=[], cash="1250000")
    result = await sync_kis_balance(db_session, kis_account, empty)
    await db_session.commit()

    assert result.closed == 1

    sold_q = await db_session.execute(
        select(Asset).where(
            Asset.trading_account_id == kis_account.id,
            Asset.source == AssetSource.KIS,
            Asset.status == AssetStatus.SOLD,
        )
    )
    sold = sold_q.scalars().one()
    assert sold.external_ticker == "005930"
    assert sold.sold_at is not None
    # current_price=75000, avg_buy=70000, qty=10 → realized_pnl = 5000 * 10 = 50000
    assert decrypt_decimal(sold.sold_price) == Decimal("75000")
    assert decrypt_decimal(sold.realized_pnl) == Decimal("50000")


@pytest.mark.asyncio
async def test_disappeared_holding_without_current_price_keeps_pnl_null(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    # current_price 없이 등록 (sync_kis_balance에서 current_price 미전달)
    initial = _balance(
        holdings=[_holding("005930", "삼성전자", 10, "70000")],
        cash="0",
    )
    await sync_kis_balance(db_session, kis_account, initial)
    await db_session.commit()

    empty = _balance(holdings=[], cash="700000")
    await sync_kis_balance(db_session, kis_account, empty)
    await db_session.commit()

    sold_q = await db_session.execute(
        select(Asset).where(
            Asset.trading_account_id == kis_account.id,
            Asset.source == AssetSource.KIS,
            Asset.status == AssetStatus.SOLD,
        )
    )
    sold = sold_q.scalars().one()
    # current_price가 없으면 sold_price/realized_pnl은 NULL로 두어 집계에서 제외
    assert sold.sold_price is None
    assert sold.realized_pnl is None


@pytest.mark.asyncio
async def test_manual_and_kis_cash_can_coexist(
    db_session: AsyncSession, mock_user: User, kis_account: TradingAccount,
):
    # 사용자가 이미 manual KRW cash 자산을 보유한 상태
    manual_cash = Asset(
        user_id=mock_user.id,
        type=AssetType.CASH,
        status=AssetStatus.ACTIVE,
        name="기존 예금",
        currency=Currency.KRW,
        quantity=encrypt_decimal(Decimal("3000000")),
        purchase_price=encrypt_decimal(Decimal("3000000")),
        source=AssetSource.MANUAL,
    )
    db_session.add(manual_cash)
    await db_session.commit()

    # KIS 잔고 sync — 같은 user/currency지만 partial unique index가 source로 분리되어 충돌 없음
    balance = _balance(holdings=[], cash="1000000")
    await sync_kis_balance(db_session, kis_account, balance)
    await db_session.commit()

    all_q = await db_session.execute(
        select(Asset).where(
            Asset.user_id == mock_user.id,
            Asset.type == AssetType.CASH,
            Asset.status == AssetStatus.ACTIVE,
        )
    )
    cash_rows = list(all_q.scalars().all())
    assert len(cash_rows) == 2
    sources = {a.source for a in cash_rows}
    assert sources == {AssetSource.MANUAL, AssetSource.KIS}


@pytest.mark.asyncio
async def test_close_kis_assets_marks_all_sold(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    initial = _balance(
        holdings=[
            _holding("005930", "삼성전자", 10, "70000", "75000"),
            _holding("005380", "현대차", 5, "200000", "210000"),
        ],
        cash="500000",
    )
    await sync_kis_balance(db_session, kis_account, initial)
    await db_session.commit()

    closed = await close_kis_assets_for_account(db_session, kis_account.id)
    await db_session.commit()

    # 보유종목 2 + 현금 1 = 3건 모두 SOLD
    assert closed == 3
    active_after = await _active_kis_assets(db_session, kis_account.id)
    assert active_after == []


@pytest.mark.asyncio
async def test_sync_skips_holdings_with_empty_ticker(
    db_session: AsyncSession, kis_account: TradingAccount,
):
    balance = _balance(
        holdings=[
            _holding("", "이상치", 1, "1000"),
            _holding("005930", "삼성전자", 10, "70000", "75000"),
        ],
        cash="0",
    )
    result = await sync_kis_balance(db_session, kis_account, balance)
    await db_session.commit()

    # 빈 ticker는 무시, 정상 종목 1건만 집계
    assert result.upserted_holdings == 1
    rows = await _active_kis_assets(db_session, kis_account.id)
    holdings = [a for a in rows if a.type == AssetType.DOMESTIC_STOCK]
    assert len(holdings) == 1
    assert holdings[0].external_ticker == "005930"
