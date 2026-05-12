"""자산 화면 통합 — 종목별 전략/수동/KIS 잔고 분해 & mismatch 경고 테스트."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetSource, AssetStatus, AssetType, Currency
from app.models.trading import (
    AdvisoryPosition,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingPosition,
    TradingStrategy,
)
from app.models.user import User
from app.services.crypto_service import encrypt_decimal
from app.services.holding_breakdown import build_user_holding_breakdown


@pytest_asyncio.fixture
async def account(db_session: AsyncSession, mock_user: User) -> TradingAccount:
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
async def strategy(
    db_session: AsyncSession, mock_user: User, account: TradingAccount
) -> TradingStrategy:
    s = TradingStrategy(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        name="테스트 전략",
        strategy_type=StrategyType.MA_CROSSOVER,
        target_tickers=["005930"],
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _make_kis_asset(
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    ticker: str,
    quantity: Decimal,
    name: str = "",
) -> Asset:
    return Asset(
        user_id=user_id,
        type=AssetType.DOMESTIC_STOCK,
        status=AssetStatus.ACTIVE,
        name=name or ticker,
        ticker=ticker,
        currency=Currency.KRW,
        quantity=encrypt_decimal(quantity),
        purchase_price=encrypt_decimal(Decimal("100000")),
        current_price=Decimal("100000"),
        source=AssetSource.KIS,
        trading_account_id=account_id,
        external_ticker=ticker,
        last_synced_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_breakdown_combines_strategy_advisory_and_kis(
    db_session: AsyncSession,
    mock_user: User,
    account: TradingAccount,
    strategy: TradingStrategy,
):
    """전략 N주 + 수동 M주 = KIS 실잔고: mismatch 없음."""
    db_session.add(
        TradingPosition(
            user_id=mock_user.id,
            account_id=account.id,
            strategy_id=strategy.id,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("7")),
            avg_buy_price=encrypt_decimal(Decimal("70000")),
        )
    )
    db_session.add(
        AdvisoryPosition(
            user_id=mock_user.id,
            account_id=account.id,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("3")),
            avg_buy_price=encrypt_decimal(Decimal("80000")),
        )
    )
    db_session.add(
        _make_kis_asset(mock_user.id, account.id, "005930", Decimal("10"), "삼성전자")
    )
    await db_session.commit()

    result = await build_user_holding_breakdown(db_session, mock_user.id)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.ticker == "005930"
    assert item.strategy_qty == Decimal("7")
    assert item.advisory_qty == Decimal("3")
    assert item.kis_qty == Decimal("10")
    assert item.mismatch_qty == Decimal("0")
    assert item.has_mismatch is False
    assert result.mismatches == []


@pytest.mark.asyncio
async def test_breakdown_flags_mismatch(
    db_session: AsyncSession,
    mock_user: User,
    account: TradingAccount,
    strategy: TradingStrategy,
):
    """내부 합계가 KIS 잔고와 다르면 has_mismatch=True, 메시지 생성."""
    db_session.add(
        TradingPosition(
            user_id=mock_user.id,
            account_id=account.id,
            strategy_id=strategy.id,
            ticker="000660",
            ticker_name="SK하이닉스",
            quantity=encrypt_decimal(Decimal("5")),
            avg_buy_price=encrypt_decimal(Decimal("200000")),
        )
    )
    # advisory 없음, KIS는 5 외에 1주 더 있음 (4 표기) → 차이 발생
    db_session.add(
        _make_kis_asset(mock_user.id, account.id, "000660", Decimal("4"), "SK하이닉스")
    )
    await db_session.commit()

    result = await build_user_holding_breakdown(db_session, mock_user.id)

    item = next(i for i in result.items if i.ticker == "000660")
    assert item.strategy_qty == Decimal("5")
    assert item.advisory_qty == Decimal("0")
    assert item.kis_qty == Decimal("4")
    assert item.mismatch_qty == Decimal("1")
    assert item.has_mismatch is True
    assert len(result.mismatches) == 1
    assert "000660" in result.mismatches[0]


@pytest.mark.asyncio
async def test_breakdown_missing_kis_does_not_flag_mismatch(
    db_session: AsyncSession,
    mock_user: User,
    account: TradingAccount,
    strategy: TradingStrategy,
):
    """KIS Asset 없으면 mismatch 판정 보류 (자산 미동기화 상태)."""
    db_session.add(
        TradingPosition(
            user_id=mock_user.id,
            account_id=account.id,
            strategy_id=strategy.id,
            ticker="035720",
            ticker_name="카카오",
            quantity=encrypt_decimal(Decimal("2")),
            avg_buy_price=encrypt_decimal(Decimal("50000")),
        )
    )
    await db_session.commit()

    result = await build_user_holding_breakdown(db_session, mock_user.id)

    item = next(i for i in result.items if i.ticker == "035720")
    assert item.kis_qty is None
    assert item.has_mismatch is False
    assert result.mismatches == []


@pytest.mark.asyncio
async def test_breakdown_ignores_inactive_account(
    db_session: AsyncSession,
    mock_user: User,
    account: TradingAccount,
    strategy: TradingStrategy,
):
    """비활성 계좌의 포지션은 분해 결과에서 제외된다."""
    account.is_active = False
    db_session.add(
        TradingPosition(
            user_id=mock_user.id,
            account_id=account.id,
            strategy_id=strategy.id,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("3")),
            avg_buy_price=encrypt_decimal(Decimal("70000")),
        )
    )
    await db_session.commit()

    result = await build_user_holding_breakdown(db_session, mock_user.id)
    assert result.items == []


@pytest.mark.asyncio
async def test_endpoint_returns_breakdown(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    account: TradingAccount,
    strategy: TradingStrategy,
):
    """GET /api/assets/holdings/breakdown 가 분해 결과를 직렬화해 반환한다."""
    db_session.add(
        TradingPosition(
            user_id=mock_user.id,
            account_id=account.id,
            strategy_id=strategy.id,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("4")),
            avg_buy_price=encrypt_decimal(Decimal("70000")),
        )
    )
    db_session.add(
        AdvisoryPosition(
            user_id=mock_user.id,
            account_id=account.id,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("1")),
            avg_buy_price=encrypt_decimal(Decimal("80000")),
        )
    )
    # KIS 잔고가 6 → 내부 합계 5와 1주 차이
    db_session.add(
        _make_kis_asset(mock_user.id, account.id, "005930", Decimal("6"), "삼성전자")
    )
    await db_session.commit()

    resp = await auth_client.get("/api/assets/holdings/breakdown")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["ticker"] == "005930"
    assert Decimal(item["strategy_qty"]) == Decimal("4")
    assert Decimal(item["advisory_qty"]) == Decimal("1")
    assert Decimal(item["kis_qty"]) == Decimal("6")
    assert item["has_mismatch"] is True
    assert Decimal(item["mismatch_qty"]) == Decimal("-1")
    assert len(data["mismatches"]) == 1
