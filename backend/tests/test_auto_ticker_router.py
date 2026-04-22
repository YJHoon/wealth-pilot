"""자동 종목 선정 API 라우터 테스트."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    AutoTickerSelection,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.models.user import User
from app.services.crypto_service import encrypt_decimal
from app.services.ticker_selector import (
    ExcludedTicker,
    SelectedTicker,
    SelectionResult,
)


def _result(tickers: list[str]) -> SelectionResult:
    return SelectionResult(
        rule_version="v1-volume-rank",
        selected=[
            SelectedTicker(
                ticker=t,
                name=f"종목{i}",
                market="KOSPI",
                price=Decimal("10000"),
                volume_value=10**11 - i * 10**9,
                score=1.0 - i * 0.1,
                reason=f"거래대금 {i + 1}위",
            )
            for i, t in enumerate(tickers)
        ],
        excluded_sample=[ExcludedTicker("000001", "우선주", "preferred")],
    )


@pytest_asyncio.fixture
async def auto_account(db_session: AsyncSession, mock_user: User):
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


@pytest_asyncio.fixture
async def auto_strategy(
    db_session: AsyncSession, mock_user: User, auto_account: TradingAccount,
):
    strategy = TradingStrategy(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=auto_account.id,
        name="자동 선정 전략",
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={"max_position_pct": "0.20"},
        target_tickers=[],
        auto_select_config={
            "enabled": True,
            "top_n": 3,
            "market": "ALL",
            "min_volume_value": 0,
            "blacklist": [],
        },
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    yield strategy


@pytest.mark.asyncio
class TestAutoTickerPreview:
    async def test_preview_returns_selection(
        self, auth_client: AsyncClient, auto_strategy: TradingStrategy,
    ):
        with patch(
            "app.routers.trading.select_tickers",
            new=AsyncMock(return_value=_result(["005930", "000660", "035420"])),
        ):
            resp = await auth_client.get(
                f"/api/trading/strategies/{auto_strategy.id}/auto-tickers/preview"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_version"] == "v1-volume-rank"
        assert [s["ticker"] for s in data["selected"]] == [
            "005930", "000660", "035420",
        ]
        assert data["config_snapshot"]["top_n"] == 3
        assert Decimal(data["available_cash"]) >= 0
        assert Decimal(data["total_eval"]) > 0

    async def test_preview_other_user_404(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        other_user: User,
    ):
        # 다른 유저 소유 전략 생성
        account = TradingAccount(
            id=uuid.uuid4(),
            user_id=other_user.id,
            mode=TradingMode.PAPER,
            initial_capital=encrypt_decimal(Decimal("1000000")),
        )
        db_session.add(account)
        await db_session.flush()
        strategy = TradingStrategy(
            id=uuid.uuid4(),
            user_id=other_user.id,
            account_id=account.id,
            name="다른 유저 전략",
            strategy_type=StrategyType.MA_CROSSOVER,
            params_json={},
            target_tickers=[],
            auto_select_config={"enabled": True},
            initial_capital=encrypt_decimal(Decimal("1000000")),
        )
        db_session.add(strategy)
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/trading/strategies/{strategy.id}/auto-tickers/preview"
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestAutoTickerRefresh:
    async def test_refresh_persists_and_returns_updated(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        auto_strategy: TradingStrategy,
    ):
        async def fake_persist(db, strategy, **kwargs):
            assert kwargs["triggered_by"] == "manual"
            strategy.auto_selected_tickers = {
                "tickers": ["005930", "000660"],
                "generated_at": "2026-04-22T00:00:00+00:00",
                "rule_version": "v1-volume-rank",
                "details": [],
            }
            db.add(
                AutoTickerSelection(
                    strategy_id=strategy.id,
                    rule_version="v1-volume-rank",
                    selected_tickers=[
                        {"ticker": "005930"}, {"ticker": "000660"},
                    ],
                    excluded_sample=None,
                    config_snapshot={},
                    triggered_by="manual",
                )
            )
            return _result(["005930", "000660"])

        with patch(
            "app.routers.trading.select_and_persist",
            new=AsyncMock(side_effect=fake_persist),
        ):
            resp = await auth_client.post(
                f"/api/trading/strategies/{auto_strategy.id}/auto-tickers/refresh"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_selected_tickers"]["tickers"] == ["005930", "000660"]

        await db_session.execute(
            text(
                "DELETE FROM auto_ticker_selections WHERE strategy_id = :s"
            ),
            {"s": str(auto_strategy.id)},
        )
        await db_session.commit()

    async def test_refresh_disabled_returns_400(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        auto_account: TradingAccount,
        mock_user: User,
    ):
        strategy = TradingStrategy(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            account_id=auto_account.id,
            name="비활성",
            strategy_type=StrategyType.MA_CROSSOVER,
            params_json={},
            target_tickers=[],
            auto_select_config={"enabled": False},
            initial_capital=encrypt_decimal(Decimal("1000000")),
        )
        db_session.add(strategy)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/trading/strategies/{strategy.id}/auto-tickers/refresh"
        )
        assert resp.status_code == 400
        assert "비활성" in resp.json()["detail"]


@pytest.mark.asyncio
class TestAutoTickerHistory:
    async def test_history_returns_recent_first(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        auto_strategy: TradingStrategy,
    ):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        for i in range(3):
            db_session.add(
                AutoTickerSelection(
                    strategy_id=auto_strategy.id,
                    generated_at=now - timedelta(hours=i),
                    rule_version="v1-volume-rank",
                    selected_tickers=[{"ticker": f"00000{i}"}],
                    excluded_sample=None,
                    config_snapshot={"top_n": 3},
                    triggered_by="schedule" if i else "manual",
                )
            )
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/trading/strategies/{auto_strategy.id}/auto-tickers/history?limit=10"
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 3
        # 최신순
        assert rows[0]["triggered_by"] == "manual"
        assert rows[0]["selected_tickers"][0]["ticker"] == "000000"

        await db_session.execute(
            text(
                "DELETE FROM auto_ticker_selections WHERE strategy_id = :s"
            ),
            {"s": str(auto_strategy.id)},
        )
        await db_session.commit()
