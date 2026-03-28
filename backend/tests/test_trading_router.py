"""자동매매 라우터 테스트 — KIS 클라이언트 mock 기반"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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
async def trading_account(db_session: AsyncSession, mock_user: User):
    """테스트용 매매 계좌."""
    account = TradingAccount(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    yield account
    await db_session.delete(account)
    await db_session.commit()


@pytest_asyncio.fixture
async def trading_strategy(
    db_session: AsyncSession, mock_user: User, trading_account: TradingAccount,
):
    """테스트용 매매 전략."""
    strategy = TradingStrategy(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=trading_account.id,
        name="테스트 전략",
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={"fast_period": 5, "slow_period": 20},
        target_tickers=["005930"],
        interval_minutes=10,
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    yield strategy
    await db_session.delete(strategy)
    await db_session.commit()


@pytest.mark.asyncio
class TestAccountEndpoints:
    async def test_create_account(self, auth_client: AsyncClient):
        mock_balance = {
            "cash": Decimal("5000000"),
            "total_eval": Decimal("0"),
            "total_pnl": Decimal("0"),
            "holdings": [],
        }
        with patch("app.routers.trading.KISClient") as MockKIS:
            instance = AsyncMock()
            instance.get_balance = AsyncMock(return_value=mock_balance)
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.post(
                "/api/trading/accounts",
                json={"mode": "paper"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["mode"] == "paper"
        assert data["is_active"] is True
        assert float(data["initial_capital"]) == 5000000

    async def test_create_duplicate_mode_rejected(
        self, auth_client: AsyncClient, trading_account: TradingAccount,
    ):
        resp = await auth_client.post(
            "/api/trading/accounts",
            json={"mode": "paper"},
        )
        assert resp.status_code == 409

    async def test_list_accounts(
        self, auth_client: AsyncClient, trading_account: TradingAccount,
    ):
        resp = await auth_client.get("/api/trading/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_deactivate_account(
        self, auth_client: AsyncClient, trading_account: TradingAccount,
    ):
        resp = await auth_client.delete(f"/api/trading/accounts/{trading_account.id}")
        assert resp.status_code == 204


@pytest.mark.asyncio
class TestStrategyEndpoints:
    async def test_create_strategy(
        self, auth_client: AsyncClient, trading_account: TradingAccount,
    ):
        resp = await auth_client.post(
            "/api/trading/strategies",
            json={
                "account_id": str(trading_account.id),
                "name": "새 전략",
                "target_tickers": ["005930", "000660"],
                "interval_minutes": 15,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "새 전략"
        assert data["interval_minutes"] == 15
        assert data["is_scheduled"] is False

    async def test_list_strategies(
        self, auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        resp = await auth_client.get("/api/trading/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_update_strategy(
        self, auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        resp = await auth_client.put(
            f"/api/trading/strategies/{trading_strategy.id}",
            json={"name": "수정된 전략", "interval_minutes": 30},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "수정된 전략"
        assert resp.json()["interval_minutes"] == 30


@pytest.mark.asyncio
class TestScheduleEndpoints:
    @patch("app.routers.trading.trading_scheduler")
    @patch("app.routers.trading.send_telegram_message", new_callable=AsyncMock)
    async def test_start_schedule(
        self, mock_telegram, mock_scheduler,
        auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        resp = await auth_client.post(
            "/api/trading/schedule/start",
            json={"strategy_id": str(trading_strategy.id)},
        )
        assert resp.status_code == 200
        assert "시작" in resp.json()["message"]
        mock_scheduler.add_schedule.assert_called_once()

    @patch("app.routers.trading.trading_scheduler")
    @patch("app.routers.trading.send_telegram_message", new_callable=AsyncMock)
    async def test_stop_schedule(
        self, mock_telegram, mock_scheduler,
        auth_client: AsyncClient, trading_strategy: TradingStrategy, db_session: AsyncSession,
    ):
        # Set is_scheduled = True first
        trading_strategy.is_scheduled = True
        await db_session.commit()

        resp = await auth_client.post(
            "/api/trading/schedule/stop",
            json={"strategy_id": str(trading_strategy.id)},
        )
        assert resp.status_code == 200
        assert "중지" in resp.json()["message"]

    @patch("app.routers.trading.trading_scheduler")
    async def test_schedule_status(
        self, mock_scheduler,
        auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        mock_scheduler.get_next_run_time.return_value = None

        resp = await auth_client.get(
            "/api/trading/schedule/status",
            params={"strategy_id": str(trading_strategy.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "is_active" in data

    async def test_start_already_scheduled_returns_409(
        self, auth_client: AsyncClient, trading_strategy: TradingStrategy, db_session: AsyncSession,
    ):
        trading_strategy.is_scheduled = True
        await db_session.commit()

        resp = await auth_client.post(
            "/api/trading/schedule/start",
            json={"strategy_id": str(trading_strategy.id)},
        )
        assert resp.status_code == 409


@pytest.mark.asyncio
class TestOrderEndpoints:
    async def test_list_orders_empty(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/trading/orders")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
class TestPositionEndpoints:
    async def test_list_positions_empty(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/trading/positions")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
class TestPerformanceEndpoint:
    async def test_performance(
        self, auth_client: AsyncClient, trading_account: TradingAccount,
    ):
        resp = await auth_client.get(
            "/api/trading/performance",
            params={"account_id": str(trading_account.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] == 0
        assert Decimal(data["initial_capital"]) == Decimal("10000000")


@pytest.mark.asyncio
class TestOwnershipValidation:
    async def test_nonexistent_account_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(
            f"/api/trading/accounts/{uuid.uuid4()}/balance",
        )
        assert resp.status_code == 404

    async def test_nonexistent_strategy_404(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            f"/api/trading/strategies/{uuid.uuid4()}",
            json={"name": "test"},
        )
        assert resp.status_code == 404
