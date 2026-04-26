"""계좌 자본 요약 endpoint 테스트.

`GET /api/trading/accounts/{id}/capital-summary` — 계좌 총 자본, 다른 전략에
이미 배정된 합계, 잔여 가용 자본을 반환. 편집 화면에서 자기 자신을 제외하고
잔여를 보여주기 위한 `exclude_strategy_id` 파라미터 지원.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.models.user import User
from app.services.crypto_service import encrypt_decimal


@pytest_asyncio.fixture
async def account_with_capital(db_session: AsyncSession, mock_user: User):
    a = TradingAccount(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("400000")),
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    yield a


def _make_strategy(user_id, account_id, name, capital):
    return TradingStrategy(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        name=name,
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={},
        target_tickers=[],
        interval_minutes=10,
        initial_capital=encrypt_decimal(Decimal(str(capital))),
        realized_pnl=encrypt_decimal(Decimal("0")),
    )


@pytest.mark.asyncio
async def test_summary_with_no_strategies_returns_full_capital(
    auth_client: AsyncClient,
    account_with_capital: TradingAccount,
):
    resp = await auth_client.get(
        f"/api/trading/accounts/{account_with_capital.id}/capital-summary",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["account_total"]) == Decimal("400000")
    assert Decimal(body["allocated"]) == Decimal("0")
    assert Decimal(body["available"]) == Decimal("400000")


@pytest.mark.asyncio
async def test_summary_excludes_inactive_strategies(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    account_with_capital: TradingAccount,
):
    s1 = _make_strategy(mock_user.id, account_with_capital.id, "활성", "200000")
    s2 = _make_strategy(mock_user.id, account_with_capital.id, "비활성", "100000")
    s2.is_active = False
    db_session.add_all([s1, s2])
    await db_session.commit()

    resp = await auth_client.get(
        f"/api/trading/accounts/{account_with_capital.id}/capital-summary",
    )
    assert resp.status_code == 200
    body = resp.json()
    # 비활성 전략은 합계에서 빠짐 → allocated=200000, available=200000
    assert Decimal(body["allocated"]) == Decimal("200000")
    assert Decimal(body["available"]) == Decimal("200000")


@pytest.mark.asyncio
async def test_summary_excludes_self_when_editing(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    mock_user: User,
    account_with_capital: TradingAccount,
):
    s1 = _make_strategy(mock_user.id, account_with_capital.id, "A", "200000")
    s2 = _make_strategy(mock_user.id, account_with_capital.id, "B", "100000")
    db_session.add_all([s1, s2])
    await db_session.commit()

    # 편집 모드: s1을 수정 중이라면 s1의 자본은 빼고 잔여 계산
    resp = await auth_client.get(
        f"/api/trading/accounts/{account_with_capital.id}/capital-summary",
        params={"exclude_strategy_id": str(s1.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    # allocated는 s2(100000)만 카운트, available = 400000 - 100000 = 300000
    assert Decimal(body["allocated"]) == Decimal("100000")
    assert Decimal(body["available"]) == Decimal("300000")


@pytest.mark.asyncio
async def test_summary_other_user_account_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    other_user: User,
):
    other_account = TradingAccount(
        id=uuid.uuid4(),
        user_id=other_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("1000000")),
    )
    db_session.add(other_account)
    await db_session.commit()

    resp = await auth_client.get(
        f"/api/trading/accounts/{other_account.id}/capital-summary",
    )
    assert resp.status_code == 404
