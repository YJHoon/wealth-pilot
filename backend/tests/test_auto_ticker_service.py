"""자동 종목 선정 서비스 단위 테스트 — DB 영속화 동작."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.models.trading import (
    AutoTickerSelection,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.services.auto_ticker_service import (
    STALE_AFTER,
    get_auto_tickers,
    is_enabled,
    is_stale,
    resolve_strategy_tickers,
    select_and_persist,
)
from app.services.crypto_service import encrypt_decimal
from app.services.ticker_selector import StockCandidate


def _candidate(ticker: str, name: str, *, price: int = 10_000, vol: int = 10**11):
    return StockCandidate(
        ticker=ticker,
        name=name,
        market="KOSPI",
        price=Decimal(str(price)),
        volume_value=vol,
        market_cap=10**12,
    )


async def _make_strategy(
    db_session,
    mock_user,
    *,
    auto_select_config: dict,
    auto_selected_tickers: dict | None = None,
) -> TradingStrategy:
    account = TradingAccount(
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(account)
    await db_session.flush()

    strategy = TradingStrategy(
        user_id=mock_user.id,
        account_id=account.id,
        name="test-strategy",
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={"max_position_pct": "0.20"},
        target_tickers=[],
        auto_select_config=auto_select_config,
        auto_selected_tickers=auto_selected_tickers,
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    return strategy


class TestIsEnabled:
    def test_true_when_enabled(self):
        s = TradingStrategy(auto_select_config={"enabled": True})
        assert is_enabled(s) is True

    def test_false_when_missing(self):
        s = TradingStrategy(auto_select_config={})
        assert is_enabled(s) is False

    def test_false_when_null(self):
        s = TradingStrategy(auto_select_config=None)  # type: ignore[arg-type]
        assert is_enabled(s) is False


class TestIsStale:
    def test_stale_when_empty(self):
        s = TradingStrategy(auto_selected_tickers=None)  # type: ignore[arg-type]
        assert is_stale(s) is True

    def test_fresh_within_24h(self):
        now = datetime.now(timezone.utc)
        s = TradingStrategy(
            auto_selected_tickers={
                "tickers": ["005930"],
                "generated_at": (now - timedelta(hours=1)).isoformat(),
                "rule_version": "v1-volume-rank",
            }
        )
        assert is_stale(s, now=now) is False

    def test_stale_past_threshold(self):
        now = datetime.now(timezone.utc)
        s = TradingStrategy(
            auto_selected_tickers={
                "tickers": ["005930"],
                "generated_at": (now - STALE_AFTER - timedelta(minutes=1)).isoformat(),
                "rule_version": "v1-volume-rank",
            }
        )
        assert is_stale(s, now=now) is True


@pytest.mark.asyncio
class TestSelectAndPersist:
    async def test_persists_result_and_history(self, db_session, mock_user):
        strategy = await _make_strategy(
            db_session,
            mock_user,
            auto_select_config={
                "enabled": True,
                "top_n": 3,
                "market": "KOSPI",
                "min_volume_value": 0,
            },
        )

        async def loader(_m):
            return [
                _candidate("005930", "삼성전자", vol=500 * 10**9),
                _candidate("000660", "SK하이닉스", vol=400 * 10**9),
            ]

        result = await select_and_persist(
            db_session,
            strategy,
            available_cash=Decimal("10000000"),
            total_eval=Decimal("10000000"),
            triggered_by="manual",
            loader=loader,
        )
        await db_session.commit()
        await db_session.refresh(strategy)

        assert [s.ticker for s in result.selected] == ["005930", "000660"]
        assert strategy.auto_selected_tickers is not None
        assert strategy.auto_selected_tickers["tickers"] == ["005930", "000660"]
        assert strategy.auto_selected_tickers["rule_version"] == "v1-volume-rank"

        # 이력 레코드 1건
        rows = (
            await db_session.execute(
                select(AutoTickerSelection).where(
                    AutoTickerSelection.strategy_id == strategy.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].triggered_by == "manual"
        assert len(rows[0].selected_tickers) == 2

        # cleanup
        await db_session.execute(
            text("DELETE FROM auto_ticker_selections WHERE strategy_id = :sid"),
            {"sid": str(strategy.id)},
        )
        await db_session.commit()

    async def test_empty_result_keeps_previous_but_logs_history(
        self, db_session, mock_user
    ):
        prev = {
            "tickers": ["005930"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rule_version": "v1-volume-rank",
        }
        strategy = await _make_strategy(
            db_session,
            mock_user,
            auto_select_config={"enabled": True, "top_n": 3, "min_volume_value": 0},
            auto_selected_tickers=prev,
        )

        async def loader(_m):
            # 시드 너무 작음 → 전부 제외 예정이지만 여기서는 universe 자체가 비어있어도 동일 효과
            return []

        await select_and_persist(
            db_session,
            strategy,
            available_cash=Decimal("10000000"),
            total_eval=Decimal("10000000"),
            triggered_by="lazy",
            loader=loader,
        )
        await db_session.commit()
        await db_session.refresh(strategy)

        # 기존 리스트 유지
        assert strategy.auto_selected_tickers["tickers"] == ["005930"]

        # 이력은 기록됨 (selected 빈 상태로)
        rows = (
            await db_session.execute(
                select(AutoTickerSelection).where(
                    AutoTickerSelection.strategy_id == strategy.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].selected_tickers == []

        await db_session.execute(
            text("DELETE FROM auto_ticker_selections WHERE strategy_id = :sid"),
            {"sid": str(strategy.id)},
        )
        await db_session.commit()


class TestGetAutoTickers:
    def test_returns_empty_when_missing(self):
        s = TradingStrategy(auto_selected_tickers=None)  # type: ignore[arg-type]
        assert get_auto_tickers(s) == []

    def test_returns_list(self):
        s = TradingStrategy(
            auto_selected_tickers={"tickers": ["005930", "000660"]}
        )
        assert get_auto_tickers(s) == ["005930", "000660"]


@pytest.mark.asyncio
class TestResolveStrategyTickers:
    async def test_union_manual_auto_held(self, db_session, mock_user):
        strategy = await _make_strategy(
            db_session,
            mock_user,
            auto_select_config={"enabled": True, "top_n": 3, "min_volume_value": 0},
            auto_selected_tickers={
                "tickers": ["000660", "035420"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "rule_version": "v1-volume-rank",
            },
        )
        strategy.target_tickers = ["005930", "000660"]  # 000660 겹침
        await db_session.commit()

        async def noop_loader(_m):
            return []

        result = await resolve_strategy_tickers(
            db_session,
            strategy,
            available_cash=Decimal("1000000"),
            total_eval=Decimal("1000000"),
            held_tickers={"005380", "005930"},  # 005930 겹침
            loader=noop_loader,
        )
        # 순서: 수동 먼저, 자동 다음, 보유 추가. 중복 제거.
        assert result == ["005930", "000660", "035420", "005380"]

    async def test_disabled_returns_manual_plus_held_only(
        self, db_session, mock_user
    ):
        strategy = await _make_strategy(
            db_session,
            mock_user,
            auto_select_config={"enabled": False},
            auto_selected_tickers={"tickers": ["999999"]},  # 무시돼야 함
        )
        strategy.target_tickers = ["005930"]
        await db_session.commit()

        async def noop_loader(_m):
            return []

        result = await resolve_strategy_tickers(
            db_session,
            strategy,
            available_cash=Decimal("1000000"),
            total_eval=Decimal("1000000"),
            held_tickers={"000660"},
            loader=noop_loader,
        )
        assert result == ["005930", "000660"]

    async def test_lazy_refresh_when_stale(self, db_session, mock_user):
        strategy = await _make_strategy(
            db_session,
            mock_user,
            auto_select_config={"enabled": True, "top_n": 3, "min_volume_value": 0},
            auto_selected_tickers={
                "tickers": ["old"],
                "generated_at": (
                    datetime.now(timezone.utc) - STALE_AFTER - timedelta(hours=1)
                ).isoformat(),
                "rule_version": "v1-volume-rank",
            },
        )
        strategy.target_tickers = []
        await db_session.commit()

        async def loader(_m):
            return [
                _candidate("A1", "A1", vol=500 * 10**9),
                _candidate("A2", "A2", vol=400 * 10**9),
                _candidate("A3", "A3", vol=300 * 10**9),
            ]

        result = await resolve_strategy_tickers(
            db_session,
            strategy,
            available_cash=Decimal("10000000"),
            total_eval=Decimal("10000000"),
            held_tickers=set(),
            loader=loader,
        )
        assert set(result) == {"A1", "A2", "A3"}

        await db_session.execute(
            text("DELETE FROM auto_ticker_selections WHERE strategy_id = :sid"),
            {"sid": str(strategy.id)},
        )
        await db_session.commit()

    async def test_no_refresh_when_fresh(self, db_session, mock_user):
        strategy = await _make_strategy(
            db_session,
            mock_user,
            auto_select_config={"enabled": True, "top_n": 3, "min_volume_value": 0},
            auto_selected_tickers={
                "tickers": ["cached"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "rule_version": "v1-volume-rank",
            },
        )
        strategy.target_tickers = []
        await db_session.commit()

        loader_called = False

        async def loader(_m):
            nonlocal loader_called
            loader_called = True
            return []

        result = await resolve_strategy_tickers(
            db_session,
            strategy,
            available_cash=Decimal("10000000"),
            total_eval=Decimal("10000000"),
            held_tickers=set(),
            loader=loader,
        )
        assert result == ["cached"]
        assert loader_called is False
