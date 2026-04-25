"""자동 종목 선정 이력 정리 크론 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.models.trading import (
    AutoTickerSelection,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.services.crypto_service import encrypt_decimal
from app.tasks.auto_ticker_cleanup import cleanup_auto_ticker_history


@pytest.mark.asyncio
async def test_cleanup_keeps_latest_n_per_strategy(db_session, mock_user):
    account = TradingAccount(
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(account)
    await db_session.flush()

    strategy_a = TradingStrategy(
        user_id=mock_user.id, account_id=account.id, name="A",
        strategy_type=StrategyType.MA_CROSSOVER, params_json={},
        target_tickers=[], auto_select_config={"enabled": True},
        initial_capital=encrypt_decimal(Decimal("1000000")),
    )
    strategy_b = TradingStrategy(
        user_id=mock_user.id, account_id=account.id, name="B",
        strategy_type=StrategyType.MA_CROSSOVER, params_json={},
        target_tickers=[], auto_select_config={"enabled": True},
        initial_capital=encrypt_decimal(Decimal("1000000")),
    )
    db_session.add_all([strategy_a, strategy_b])
    await db_session.commit()

    now = datetime.now(timezone.utc)
    # A 전략: 35건, B 전략: 5건
    rows = []
    for i in range(35):
        rows.append(AutoTickerSelection(
            strategy_id=strategy_a.id,
            generated_at=now - timedelta(minutes=i),
            rule_version="v1-volume-rank",
            selected_tickers=[{"ticker": f"a{i:03d}"}],
            excluded_sample=None,
            config_snapshot={},
            triggered_by="schedule",
        ))
    for i in range(5):
        rows.append(AutoTickerSelection(
            strategy_id=strategy_b.id,
            generated_at=now - timedelta(minutes=i),
            rule_version="v1-volume-rank",
            selected_tickers=[{"ticker": f"b{i:03d}"}],
            excluded_sample=None,
            config_snapshot={},
            triggered_by="schedule",
        ))
    db_session.add_all(rows)
    await db_session.commit()

    deleted = await cleanup_auto_ticker_history(keep_per_strategy=30)
    assert deleted == 5

    # A 는 30건만 남고 최신 30건이어야 함
    a_count = (await db_session.execute(
        select(func.count()).select_from(AutoTickerSelection).where(
            AutoTickerSelection.strategy_id == strategy_a.id,
        )
    )).scalar()
    assert a_count == 30

    # B 는 그대로 5건
    b_count = (await db_session.execute(
        select(func.count()).select_from(AutoTickerSelection).where(
            AutoTickerSelection.strategy_id == strategy_b.id,
        )
    )).scalar()
    assert b_count == 5

    # A 의 가장 오래된 5건이 삭제되었는지: 남은 최소 generated_at 이 now-29분 이상
    oldest = (await db_session.execute(
        select(func.min(AutoTickerSelection.generated_at)).where(
            AutoTickerSelection.strategy_id == strategy_a.id,
        )
    )).scalar()
    assert oldest >= now - timedelta(minutes=30)

    await db_session.execute(
        text(
            "DELETE FROM auto_ticker_selections WHERE strategy_id IN (:a, :b)"
        ),
        {"a": str(strategy_a.id), "b": str(strategy_b.id)},
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_cleanup_noop_when_under_limit(db_session, mock_user):
    account = TradingAccount(
        user_id=mock_user.id,
        mode=TradingMode.PAPER,
        initial_capital=encrypt_decimal(Decimal("10000000")),
    )
    db_session.add(account)
    await db_session.flush()
    strategy = TradingStrategy(
        user_id=mock_user.id, account_id=account.id, name="C",
        strategy_type=StrategyType.MA_CROSSOVER, params_json={},
        target_tickers=[], auto_select_config={"enabled": True},
        initial_capital=encrypt_decimal(Decimal("1000000")),
    )
    db_session.add(strategy)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    for i in range(10):
        db_session.add(AutoTickerSelection(
            strategy_id=strategy.id,
            generated_at=now - timedelta(minutes=i),
            rule_version="v1-volume-rank",
            selected_tickers=[{"ticker": f"c{i}"}],
            excluded_sample=None,
            config_snapshot={},
            triggered_by="schedule",
        ))
    await db_session.commit()

    deleted = await cleanup_auto_ticker_history(keep_per_strategy=30)
    assert deleted == 0

    await db_session.execute(
        text("DELETE FROM auto_ticker_selections WHERE strategy_id = :s"),
        {"s": str(strategy.id)},
    )
    await db_session.commit()
