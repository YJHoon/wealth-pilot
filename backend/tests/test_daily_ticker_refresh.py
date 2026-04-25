"""일일 자동 종목 갱신 크론 통합 테스트."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.trading import (
    AutoTickerSelection,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.services.crypto_service import encrypt_decimal
from app.services.ticker_selector import StockCandidate
from app.tasks.daily_ticker_refresh import execute_daily_ticker_refresh


def _candidate(ticker: str, name: str = "n", *, vol: int = 10**11):
    return StockCandidate(
        ticker=ticker, name=name, market="KOSPI",
        price=Decimal("10000"), volume_value=vol, market_cap=10**12,
    )


@pytest.mark.asyncio
async def test_refresh_only_enabled_strategies(db_session, mock_user):
    account = TradingAccount(
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(account)
    await db_session.flush()

    enabled = TradingStrategy(
        user_id=mock_user.id, account_id=account.id, name="auto-on",
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={"max_position_pct": "0.20"},
        target_tickers=[],
        auto_select_config={
            "enabled": True, "top_n": 3, "min_volume_value": 0,
        },
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    disabled = TradingStrategy(
        user_id=mock_user.id, account_id=account.id, name="auto-off",
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={},
        target_tickers=[],
        auto_select_config={"enabled": False},
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add_all([enabled, disabled])
    await db_session.commit()

    async def fake_loader(_m):
        return [
            _candidate("005930", vol=500 * 10**9),
            _candidate("000660", vol=400 * 10**9),
            _candidate("035420", vol=300 * 10**9),
        ]

    await execute_daily_ticker_refresh(loader=fake_loader)

    await db_session.refresh(enabled)
    await db_session.refresh(disabled)

    # enabled 만 갱신됨
    assert enabled.auto_selected_tickers is not None
    assert enabled.auto_selected_tickers["tickers"] == ["005930", "000660", "035420"]
    assert disabled.auto_selected_tickers is None

    # 이력은 enabled 만
    rows = (
        await db_session.execute(
            select(AutoTickerSelection).where(
                AutoTickerSelection.strategy_id.in_([enabled.id, disabled.id])
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].strategy_id == enabled.id
    assert rows[0].triggered_by == "schedule"

    await db_session.execute(
        text(
            "DELETE FROM auto_ticker_selections "
            "WHERE strategy_id IN (:e, :d)"
        ),
        {"e": str(enabled.id), "d": str(disabled.id)},
    )
    await db_session.commit()
