"""자동매매 라우터 테스트 — KIS 클라이언트 mock 기반"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
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
from app.services.kis_client import KISClientError


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

    async def test_create_account_kis_failure_returns_502(self, auth_client: AsyncClient):
        with patch("app.routers.trading.KISClient") as MockKIS:
            instance = AsyncMock()
            instance.get_balance = AsyncMock(side_effect=KISClientError("connection refused"))
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.post(
                "/api/trading/accounts",
                json={"mode": "paper"},
            )
        assert resp.status_code == 502
        instance.close.assert_awaited_once()

    async def test_create_duplicate_mode_rejected(
        self, auth_client: AsyncClient, trading_account: TradingAccount,
    ):
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


@pytest.mark.asyncio
class TestKillSwitchPersistence:
    """Phase 4: 킬 스위치 발동 시 killed_at/killed_reason 영속화."""

    async def test_killed_at_field_persists(
        self, db_session: AsyncSession, mock_user: User, trading_account: TradingAccount,
    ):
        """모델 + 마이그레이션: killed_at, killed_reason 필드가 DB에 영속화됨."""
        strategy = TradingStrategy(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            account_id=trading_account.id,
            name="kill_switch persistence",
            strategy_type=StrategyType.MA_CROSSOVER,
            params_json={},
            target_tickers=[],
            killed_at=datetime(2026, 4, 16, 9, 30, tzinfo=timezone.utc),
            killed_reason="누적 손실률 35% >= 30%",
        )
        db_session.add(strategy)
        await db_session.commit()

        await db_session.refresh(strategy)
        assert strategy.killed_at == datetime(2026, 4, 16, 9, 30, tzinfo=timezone.utc)
        assert strategy.killed_reason == "누적 손실률 35% >= 30%"


@pytest.mark.asyncio
class TestStrategyDelete:
    """Phase 4 (Task 6): 전략 삭제 엔드포인트."""

    async def _create_fresh_strategy(
        self, db_session: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID,
        *, is_active: bool = True,
    ) -> TradingStrategy:
        """fixture와 격리된 새 전략 생성 — DELETE 후 fixture teardown 충돌 방지."""
        strategy = TradingStrategy(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=account_id,
            name="삭제 테스트",
            strategy_type=StrategyType.MA_CROSSOVER,
            params_json={},
            target_tickers=["005930"],
            is_active=is_active,
        )
        db_session.add(strategy)
        await db_session.commit()
        await db_session.refresh(strategy)
        return strategy

    async def test_delete_empty_strategy(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        mock_user: User, trading_account: TradingAccount,
    ):
        strategy = await self._create_fresh_strategy(
            db_session, mock_user.id, trading_account.id,
        )
        resp = await auth_client.delete(f"/api/trading/strategies/{strategy.id}")
        assert resp.status_code == 204

    async def test_delete_killed_strategy_succeeds(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        mock_user: User, trading_account: TradingAccount,
    ):
        """is_active=False(킬 스위치 발동된 전략)도 삭제 가능."""
        strategy = await self._create_fresh_strategy(
            db_session, mock_user.id, trading_account.id, is_active=False,
        )
        strategy.killed_at = datetime.now(timezone.utc)
        strategy.killed_reason = "테스트 중단"
        await db_session.commit()

        resp = await auth_client.delete(f"/api/trading/strategies/{strategy.id}")
        assert resp.status_code == 204

    async def test_delete_with_position_returns_409(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        mock_user: User, trading_account: TradingAccount,
    ):
        strategy = await self._create_fresh_strategy(
            db_session, mock_user.id, trading_account.id,
        )
        position = TradingPosition(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            account_id=trading_account.id,
            strategy_id=strategy.id,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("10")),
            avg_buy_price=encrypt_decimal(Decimal("60000")),
        )
        db_session.add(position)
        await db_session.commit()

        resp = await auth_client.delete(f"/api/trading/strategies/{strategy.id}")
        assert resp.status_code == 409
        assert "포지션" in resp.json()["detail"]

    async def test_delete_with_open_order_returns_409(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        mock_user: User, trading_account: TradingAccount,
    ):
        strategy = await self._create_fresh_strategy(
            db_session, mock_user.id, trading_account.id,
        )
        order = TradingOrder(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            account_id=trading_account.id,
            strategy_id=strategy.id,
            side=OrderSide.BUY,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("10")),
            price=encrypt_decimal(Decimal("60000")),
            order_type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
        )
        db_session.add(order)
        await db_session.commit()

        resp = await auth_client.delete(f"/api/trading/strategies/{strategy.id}")
        assert resp.status_code == 409
        assert "미체결" in resp.json()["detail"]

    async def test_delete_nonexistent_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/trading/strategies/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestStrategyLiquidate:
    """Phase 4 (Task 6): 전략 청산 엔드포인트."""

    async def _create_position(
        self, db_session: AsyncSession, user_id: uuid.UUID,
        account_id: uuid.UUID, strategy_id: uuid.UUID,
        *, ticker: str = "005930", qty: int = 10, avg: int = 60000,
    ) -> TradingPosition:
        position = TradingPosition(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=account_id,
            strategy_id=strategy_id,
            ticker=ticker,
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal(qty)),
            avg_buy_price=encrypt_decimal(Decimal(avg)),
        )
        db_session.add(position)
        await db_session.commit()
        return position

    async def test_liquidate_outside_market_hours_returns_400(
        self, auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        with (
            patch("app.routers.trading.settings") as mock_settings,
            patch("app.tasks.trading_cycle._is_market_hours", return_value=False),
        ):
            mock_settings.trading_enabled = True
            mock_settings.kis_credentials = lambda mode: {
                "app_key": "k", "app_secret": "s",
                "account_number": "1", "account_product_code": "01",
            }
            resp = await auth_client.post(
                f"/api/trading/strategies/{trading_strategy.id}/liquidate",
            )
        assert resp.status_code == 400
        assert "시장 시간" in resp.json()["detail"]

    async def test_liquidate_no_positions_returns_400(
        self, auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        with (
            patch("app.routers.trading.settings") as mock_settings,
            patch("app.tasks.trading_cycle._is_market_hours", return_value=True),
            patch("app.routers.trading.KISClient") as MockKIS,
        ):
            mock_settings.trading_enabled = True
            mock_settings.kis_credentials = lambda mode: {
                "app_key": "k", "app_secret": "s",
                "account_number": "1", "account_product_code": "01",
            }
            instance = AsyncMock()
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.post(
                f"/api/trading/strategies/{trading_strategy.id}/liquidate",
            )
        assert resp.status_code == 400
        assert "포지션" in resp.json()["detail"]

    async def test_liquidate_with_open_order_returns_409(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        mock_user: User, trading_account: TradingAccount,
        trading_strategy: TradingStrategy,
    ):
        order = TradingOrder(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            account_id=trading_account.id,
            strategy_id=trading_strategy.id,
            side=OrderSide.BUY,
            ticker="005930",
            ticker_name="삼성전자",
            quantity=encrypt_decimal(Decimal("10")),
            price=encrypt_decimal(Decimal("60000")),
            order_type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
        )
        db_session.add(order)
        await db_session.commit()

        with (
            patch("app.routers.trading.settings") as mock_settings,
            patch("app.tasks.trading_cycle._is_market_hours", return_value=True),
            patch("app.routers.trading.KISClient") as MockKIS,
        ):
            mock_settings.trading_enabled = True
            mock_settings.kis_credentials = lambda mode: {
                "app_key": "k", "app_secret": "s",
                "account_number": "1", "account_product_code": "01",
            }
            instance = AsyncMock()
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.post(
                f"/api/trading/strategies/{trading_strategy.id}/liquidate",
            )
        assert resp.status_code == 409
        assert "미체결" in resp.json()["detail"]

    async def test_liquidate_creates_sell_orders(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        mock_user: User, trading_account: TradingAccount,
        trading_strategy: TradingStrategy,
    ):
        await self._create_position(
            db_session, mock_user.id, trading_account.id, trading_strategy.id,
            ticker="005930", qty=10, avg=60000,
        )

        with (
            patch("app.routers.trading.settings") as mock_settings,
            patch("app.tasks.trading_cycle._is_market_hours", return_value=True),
            patch("app.routers.trading.KISClient") as MockKIS,
        ):
            mock_settings.trading_enabled = True
            mock_settings.kis_credentials = lambda mode: {
                "app_key": "k", "app_secret": "s",
                "account_number": "1", "account_product_code": "01",
            }
            instance = AsyncMock()
            instance.get_current_price = AsyncMock(
                return_value={"price": 65000, "name": "삼성전자"},
            )
            instance.place_order = AsyncMock(return_value={"order_id": "KIS123"})
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.post(
                f"/api/trading/strategies/{trading_strategy.id}/liquidate",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["orders_placed"] == 1
        assert len(data["order_ids"]) == 1
        instance.place_order.assert_awaited_once()

    async def test_liquidate_disabled_globally_returns_503(
        self, auth_client: AsyncClient, trading_strategy: TradingStrategy,
    ):
        with patch("app.routers.trading.settings") as mock_settings:
            mock_settings.trading_enabled = False
            resp = await auth_client.post(
                f"/api/trading/strategies/{trading_strategy.id}/liquidate",
            )
        assert resp.status_code == 503
