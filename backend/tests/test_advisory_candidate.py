"""advisory_candidate 빌더 — 자동매매 충돌 격리 검증."""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    AnalysisItemSource,
    StrategyType,
    TradingAccount,
    TradingMode,
    TradingStrategy,
)
from app.models.user import User
from app.services.advisory_candidate import build_candidate_pool
from app.services.advisory_position import apply_buy_fill_advisory
from app.services.crypto_service import encrypt_decimal
from app.services.strategy_position import apply_buy_fill
from app.services.ticker_selector import StockCandidate


def _stock(ticker: str, name: str, price: int = 50000, vol_value: int = 10_000_000_000):
    return StockCandidate(
        ticker=ticker,
        name=name,
        market="KOSPI",
        price=Decimal(price),
        volume_value=vol_value,
        market_cap=vol_value * 100,
    )


async def _empty_universe(market):  # noqa: ARG001
    return []


def _fixed_universe(stocks: list[StockCandidate]):
    async def loader(market):  # noqa: ARG001
        return list(stocks)
    return loader


@pytest_asyncio.fixture
async def account(db_session: AsyncSession, mock_user: User):
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


def _new_strategy(user_id, account_id, name: str = "S", *, is_active: bool = True):
    return TradingStrategy(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        name=name,
        strategy_type=StrategyType.MA_CROSSOVER,
        params_json={},
        target_tickers=[],
        interval_minutes=10,
        is_active=is_active,
        initial_capital=encrypt_decimal(Decimal("5000000")),
        realized_pnl=encrypt_decimal(Decimal("0")),
    )


@pytest.mark.asyncio
async def test_active_strategy_holding_excluded_from_pool(
    db_session, mock_user, account,
):
    """활성 전략이 보유한 ticker는 BUY 후보에서 제외돼야 한다."""
    s = _new_strategy(mock_user.id, account.id, "active")
    db_session.add(s)
    await db_session.commit()
    # 활성 전략이 005930 5주 보유
    await apply_buy_fill(
        db_session, s, "005930", "삼성전자", Decimal("5"), Decimal("70000"),
    )
    await db_session.commit()

    universe = [
        _stock("005930", "삼성전자"),
        _stock("000660", "SK하이닉스"),
    ]
    pool = await build_candidate_pool(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        options={"top_n": 5, "market": "KOSPI", "min_volume_value": 0},
        available_cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        max_position_pct=Decimal("1.0"),
        loader=_fixed_universe(universe),
    )

    tickers = [i.ticker for i in pool.items]
    assert "005930" not in tickers
    assert "000660" in tickers
    assert "005930" in pool.excluded_by_active_strategy


@pytest.mark.asyncio
async def test_inactive_strategy_holding_not_excluded(
    db_session, mock_user, account,
):
    """비활성 전략이 보유한 ticker는 후보에서 제외하지 않는다."""
    s = _new_strategy(mock_user.id, account.id, "inactive", is_active=False)
    db_session.add(s)
    await db_session.commit()
    await apply_buy_fill(
        db_session, s, "005930", "삼성", Decimal("5"), Decimal("70000"),
    )
    await db_session.commit()

    universe = [_stock("005930", "삼성전자")]
    pool = await build_candidate_pool(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        options={"top_n": 5, "market": "KOSPI", "min_volume_value": 0},
        available_cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        max_position_pct=Decimal("1.0"),
        loader=_fixed_universe(universe),
    )
    tickers = [i.ticker for i in pool.items]
    assert "005930" in tickers
    assert pool.excluded_by_active_strategy == []


@pytest.mark.asyncio
async def test_advisory_holding_appears_as_holding_source(
    db_session, mock_user, account,
):
    """AdvisoryPosition 보유분은 HOLDING source 로 후보에 들어간다."""
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("3"),
        fill_price=Decimal("70000"),
    )
    await db_session.commit()

    pool = await build_candidate_pool(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        options={"top_n": 5, "market": "KOSPI", "min_volume_value": 0},
        available_cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        max_position_pct=Decimal("1.0"),
        loader=_empty_universe,
    )
    by_ticker = {i.ticker: i for i in pool.items}
    assert "005930" in by_ticker
    assert by_ticker["005930"].source == AnalysisItemSource.HOLDING
    assert by_ticker["005930"].held_qty == Decimal("3")


@pytest.mark.asyncio
async def test_holding_takes_precedence_over_auto_pick(
    db_session, mock_user, account,
):
    """같은 ticker가 보유중 + auto_pick 후보에 모두 있어도 1번만, HOLDING source 로 들어간다."""
    await apply_buy_fill_advisory(
        db_session, user_id=mock_user.id, account_id=account.id,
        ticker="005930", ticker_name="삼성", fill_qty=Decimal("2"),
        fill_price=Decimal("70000"),
    )
    await db_session.commit()

    universe = [_stock("005930", "삼성전자"), _stock("000660", "SK")]
    pool = await build_candidate_pool(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        options={"top_n": 5, "market": "KOSPI", "min_volume_value": 0},
        available_cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        max_position_pct=Decimal("1.0"),
        loader=_fixed_universe(universe),
    )
    tickers = [i.ticker for i in pool.items]
    # 005930은 1번만 등장
    assert tickers.count("005930") == 1
    by_ticker = {i.ticker: i for i in pool.items}
    assert by_ticker["005930"].source == AnalysisItemSource.HOLDING


@pytest.mark.asyncio
async def test_max_candidates_caps_pool(
    db_session, mock_user, account,
):
    universe = [_stock(f"00000{i}", f"S{i}") for i in range(1, 10)]
    pool = await build_candidate_pool(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        options={"top_n": 9, "market": "KOSPI", "min_volume_value": 0},
        available_cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        max_position_pct=Decimal("1.0"),
        max_candidates=3,
        loader=_fixed_universe(universe),
    )
    assert len(pool.items) == 3


@pytest.mark.asyncio
async def test_extra_blocked_tickers_excluded(
    db_session, mock_user, account,
):
    universe = [_stock("005930", "삼성"), _stock("000660", "SK")]
    pool = await build_candidate_pool(
        db_session,
        user_id=mock_user.id,
        account_id=account.id,
        options={"top_n": 5, "market": "KOSPI", "min_volume_value": 0},
        available_cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        max_position_pct=Decimal("1.0"),
        extra_blocked_tickers={"005930"},
        loader=_fixed_universe(universe),
    )
    tickers = [i.ticker for i in pool.items]
    assert "005930" not in tickers
    assert "000660" in tickers
