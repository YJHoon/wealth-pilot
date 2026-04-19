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
            instance.access_token = None
            instance.token_expires_at = None
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
            instance.access_token = None
            instance.token_expires_at = None
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
            instance.access_token = None
            instance.token_expires_at = None
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
class TestKisTokenCaching:
    """KIS 토큰 캐싱 — 재발급 최소화 검증."""

    async def test_create_account_persists_new_token(
        self, auth_client: AsyncClient, db_session: AsyncSession, mock_user: User,
    ):
        """신규 계좌 생성 시 KIS에서 받은 토큰이 DB에 암호화 저장된다."""
        from app.services.crypto_service import decrypt_value
        from sqlalchemy import select as sa_select

        mock_balance = {
            "cash": Decimal("5000000"),
            "total_eval": Decimal("0"),
            "total_pnl": Decimal("0"),
            "holdings": [],
        }
        expires = datetime(2027, 1, 1, tzinfo=timezone.utc)
        with patch("app.routers.trading.KISClient") as MockKIS:
            instance = AsyncMock()
            instance.access_token = "tok-new"
            instance.token_expires_at = expires
            instance.get_balance = AsyncMock(return_value=mock_balance)
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.post(
                "/api/trading/accounts",
                json={"mode": "paper"},
            )
        assert resp.status_code == 201

        result = await db_session.execute(
            sa_select(TradingAccount).where(TradingAccount.user_id == mock_user.id),
        )
        account = result.scalar_one()
        assert account.access_token is not None
        assert decrypt_value(account.access_token) == "tok-new"
        assert account.token_expires_at == expires

    async def test_get_balance_reuses_cached_token(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        trading_account: TradingAccount,
    ):
        """DB에 캐시된 토큰이 KISClient 생성자에 주입된다 (재발급 방지)."""
        from app.services.crypto_service import encrypt_value
        from datetime import timedelta

        # 기존 계좌에 유효 토큰 사전 저장
        trading_account.access_token = encrypt_value("tok-cached")
        trading_account.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=10)
        await db_session.commit()

        mock_balance = {
            "cash": Decimal("1000000"),
            "total_eval": Decimal("0"),
            "total_pnl": Decimal("0"),
            "holdings": [],
        }
        with patch("app.routers.trading.KISClient") as MockKIS:
            instance = AsyncMock()
            instance.access_token = "tok-cached"
            instance.token_expires_at = trading_account.token_expires_at
            instance.get_balance = AsyncMock(return_value=mock_balance)
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.get(
                f"/api/trading/accounts/{trading_account.id}/balance",
            )
        assert resp.status_code == 200
        # KISClient 생성자에 토큰이 주입되었는지 확인
        _, kwargs = MockKIS.call_args
        assert kwargs.get("access_token") == "tok-cached"
        assert kwargs.get("token_expires_at") is not None

    async def test_get_balance_persists_refreshed_token(
        self, auth_client: AsyncClient, db_session: AsyncSession,
        trading_account: TradingAccount,
    ):
        """KISClient가 토큰을 재발급하면 새 값이 DB에 저장된다."""
        from app.services.crypto_service import decrypt_value, encrypt_value
        from datetime import timedelta

        # 기존 토큰은 만료 임박 (인스턴스 내부에서 재발급했다고 가정)
        old_expires = datetime.now(timezone.utc) + timedelta(minutes=1)
        trading_account.access_token = encrypt_value("tok-old")
        trading_account.token_expires_at = old_expires
        await db_session.commit()

        new_expires = datetime.now(timezone.utc) + timedelta(hours=20)
        mock_balance = {
            "cash": Decimal("1000000"),
            "total_eval": Decimal("0"),
            "total_pnl": Decimal("0"),
            "holdings": [],
        }
        with patch("app.routers.trading.KISClient") as MockKIS:
            instance = AsyncMock()
            # 호출 후 인스턴스가 새 토큰을 보유 (authenticate 호출 시뮬레이션)
            instance.access_token = "tok-refreshed"
            instance.token_expires_at = new_expires
            instance.get_balance = AsyncMock(return_value=mock_balance)
            instance.close = AsyncMock()
            MockKIS.return_value = instance

            resp = await auth_client.get(
                f"/api/trading/accounts/{trading_account.id}/balance",
            )
        assert resp.status_code == 200

        await db_session.refresh(trading_account)
        assert decrypt_value(trading_account.access_token) == "tok-refreshed"
        assert trading_account.token_expires_at == new_expires


@pytest.mark.asyncio
class TestRebalanceEndpoint:
    async def test_rebalance_success(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        # 활성 전략 2개 생성
        s1 = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="S1",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("3000000")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        s2 = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="S2",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("2000000")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add_all([s1, s2])
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/rebalance",
            json={
                "allocations": [
                    {"strategy_id": str(s1.id), "initial_capital": "4000000"},
                    {"strategy_id": str(s2.id), "initial_capital": "1000000"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        caps = {row["id"]: Decimal(row["initial_capital"]) for row in data}
        assert caps[str(s1.id)] == Decimal("4000000")
        assert caps[str(s2.id)] == Decimal("1000000")

    async def test_rebalance_exceeds_account_total(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        s = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="S",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("0")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add(s)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/rebalance",
            json={
                "allocations": [
                    # 계좌 총 자본은 10,000,000 — 초과
                    {"strategy_id": str(s.id), "initial_capital": "20000000"},
                ],
            },
        )
        assert resp.status_code == 400

    async def test_rebalance_foreign_strategy_rejected(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        # 다른 계좌 소속 전략 ID로 시도
        other_account = TradingAccount(
            user_id=mock_user.id,
            mode=TradingMode.LIVE,
            initial_capital=encrypt_decimal(Decimal("5000000")),
        )
        db_session.add(other_account)
        await db_session.commit()
        await db_session.refresh(other_account)

        foreign = TradingStrategy(
            user_id=mock_user.id, account_id=other_account.id, name="Foreign",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("0")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add(foreign)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/rebalance",
            json={
                "allocations": [
                    {"strategy_id": str(foreign.id), "initial_capital": "100000"},
                ],
            },
        )
        assert resp.status_code == 400

    async def test_rebalance_empty_allocations_rejected(
        self,
        auth_client: AsyncClient,
        trading_account: TradingAccount,
    ):
        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/rebalance",
            json={"allocations": []},
        )
        assert resp.status_code == 400

    async def test_rebalance_duplicate_strategy_id_rejected(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        s = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="Sdup",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("0")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add(s)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/rebalance",
            json={
                "allocations": [
                    {"strategy_id": str(s.id), "initial_capital": "100000"},
                    {"strategy_id": str(s.id), "initial_capital": "200000"},
                ],
            },
        )
        assert resp.status_code == 400

    async def test_rebalance_preserves_realized_pnl(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        from app.services.crypto_service import decrypt_decimal
        s = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="Sp",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("1000000")),
            realized_pnl=encrypt_decimal(Decimal("500000")),
        )
        db_session.add(s)
        await db_session.commit()
        sid = s.id

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/rebalance",
            json={
                "allocations": [
                    {"strategy_id": str(sid), "initial_capital": "2000000"},
                ],
            },
        )
        assert resp.status_code == 200

        # 응답으로 검증 (세션 expire_all은 fixture teardown과 충돌)
        rows = resp.json()
        row = next(r for r in rows if r["id"] == str(sid))
        assert Decimal(row["initial_capital"]) == Decimal("2000000")
        assert Decimal(row["realized_pnl"]) == Decimal("500000")


@pytest.mark.asyncio
class TestDepositEndpoint:
    async def test_deposit_manual_success(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        s1 = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="S1",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("3000000")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        s2 = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="S2",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("2000000")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add_all([s1, s2])
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/deposit",
            json={
                "amount": "1000000",
                "mode": "manual",
                "allocations": [
                    {"strategy_id": str(s1.id), "amount": "700000"},
                    {"strategy_id": str(s2.id), "amount": "300000"},
                ],
            },
        )
        assert resp.status_code == 200
        # 계좌 총액 11,000,000으로 증액
        assert Decimal(resp.json()["initial_capital"]) == Decimal("11000000")

    async def test_deposit_manual_sum_mismatch_rejected(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        s = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="S",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("0")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add(s)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/deposit",
            json={
                "amount": "1000000",
                "mode": "manual",
                "allocations": [
                    {"strategy_id": str(s.id), "amount": "500000"},
                ],
            },
        )
        assert resp.status_code == 400

    async def test_deposit_pro_rata_distributes_by_ratio(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        # 3:2 비율 → 입금 1,000,000을 600,000 / 400,000로 분배
        s1 = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="P1",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("3000000")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        s2 = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="P2",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("2000000")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add_all([s1, s2])
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/deposit",
            json={"amount": "1000000", "mode": "pro_rata"},
        )
        assert resp.status_code == 200

        list_resp = await auth_client.get("/api/trading/strategies")
        assert list_resp.status_code == 200
        data = {row["id"]: Decimal(row["initial_capital"]) for row in list_resp.json()}
        assert data[str(s1.id)] == Decimal("3600000")
        assert data[str(s2.id)] == Decimal("2400000")

    async def test_deposit_pro_rata_all_zero_rejected(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        mock_user: User,
        trading_account: TradingAccount,
    ):
        s = TradingStrategy(
            user_id=mock_user.id, account_id=trading_account.id, name="Z",
            strategy_type=StrategyType.MA_CROSSOVER, params_json={}, target_tickers=[],
            interval_minutes=10,
            initial_capital=encrypt_decimal(Decimal("0")),
            realized_pnl=encrypt_decimal(Decimal("0")),
        )
        db_session.add(s)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/deposit",
            json={"amount": "1000000", "mode": "pro_rata"},
        )
        assert resp.status_code == 400

    async def test_deposit_reserve_bumps_account_only(
        self,
        auth_client: AsyncClient,
        trading_account: TradingAccount,
    ):
        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/deposit",
            json={"amount": "500000", "mode": "reserve"},
        )
        assert resp.status_code == 200
        assert Decimal(resp.json()["initial_capital"]) == Decimal("10500000")

    async def test_deposit_zero_amount_rejected(
        self,
        auth_client: AsyncClient,
        trading_account: TradingAccount,
    ):
        resp = await auth_client.post(
            f"/api/trading/accounts/{trading_account.id}/deposit",
            json={"amount": "0", "mode": "reserve"},
        )
        # Pydantic gt=0 검증 실패
        assert resp.status_code == 422


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
            instance.access_token = None
            instance.token_expires_at = None
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
            instance.access_token = None
            instance.token_expires_at = None
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
            instance.access_token = None
            instance.token_expires_at = None
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
