"""advisory_run 오케스트레이터 — 부분 실패, min_confidence, 예산 컷, SELL cap."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    AnalysisItemAction,
    AnalysisItemDecision,
    AnalysisItemSource,
    AnalysisRun,
    AnalysisRunItem,
    AnalysisRunStatus,
    TradingAccount,
    TradingMode,
)
from app.models.user import User
from app.services.advisory_candidate import CandidateItem, CandidatePool
from app.services.advisory_run import run_analysis
from app.services.crypto_service import decrypt_decimal, encrypt_decimal
from app.services.llm_advisor import LLMDecision, PortfolioContext


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


@pytest_asyncio.fixture
async def run(db_session: AsyncSession, mock_user: User, account: TradingAccount):
    r = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("10000000")),
        candidate_pool_options={},
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


def _portfolio() -> PortfolioContext:
    return PortfolioContext(
        cash=Decimal("10000000"),
        total_eval=Decimal("10000000"),
        holdings=[],
    )


def _candidate_pool(items: list[CandidateItem]) -> CandidatePool:
    return CandidatePool(items=items, excluded_by_active_strategy=[])


async def _stub_price(_ticker: str) -> list[dict]:
    return [{"date": "20260501", "close": "50000", "volume": "1000"}]


def _llm_stub(per_ticker: dict[str, LLMDecision]):
    async def _caller(*, ticker, ticker_name, price_history, portfolio):  # noqa: ARG001
        if ticker in per_ticker:
            return per_ticker[ticker]
        return LLMDecision(action="hold", confidence=0, reason="default")
    return _caller


async def _items_for_run(db: AsyncSession, run_id) -> list[AnalysisRunItem]:
    rows = await db.execute(
        select(AnalysisRunItem).where(AnalysisRunItem.run_id == run_id)
    )
    return list(rows.scalars().all())


@pytest.mark.asyncio
async def test_empty_pool_marks_run_ready(db_session, run):
    pool = _candidate_pool([])
    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=_llm_stub({}),
    )
    await db_session.commit()
    await db_session.refresh(run)
    assert run.status == AnalysisRunStatus.READY
    assert run.expires_at is not None
    assert run.summary_json["total"] == 0


@pytest.mark.asyncio
async def test_buy_candidate_passes_min_confidence(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="buy", confidence=85, reason="강한 추세",
            suggested_quantity=10,
        ),
    })
    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, min_confidence=70,
    )
    await db_session.commit()

    items = await _items_for_run(db_session, run.id)
    assert len(items) == 1
    it = items[0]
    assert it.action == AnalysisItemAction.BUY
    assert it.decision == AnalysisItemDecision.PENDING
    assert it.confidence == 85
    assert decrypt_decimal(it.suggested_qty) == Decimal("10")


@pytest.mark.asyncio
async def test_low_confidence_marked_skipped(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="buy", confidence=50, reason="애매",
            suggested_quantity=10,
        ),
    })
    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, min_confidence=70,
    )
    await db_session.commit()

    items = await _items_for_run(db_session, run.id)
    it = items[0]
    assert it.decision == AnalysisItemDecision.SKIPPED
    assert "신뢰도" in (it.blocked_reason or "")


@pytest.mark.asyncio
async def test_budget_cap_skips_lower_confidence_buys(db_session, mock_user, account):
    """예산 1,000,000 — BUY 두 건 중 confidence 높은 것 우선."""
    r = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("1000000")),  # 1M
        candidate_pool_options={},
    )
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401
    db_session.add(r)
    await db_session.commit()

    pool = _candidate_pool([
        CandidateItem(
            ticker="HIGH", ticker_name="High",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("100000"),
        ),
        CandidateItem(
            ticker="LOW", ticker_name="Low",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("100000"),
        ),
    ])
    llm = _llm_stub({
        "HIGH": LLMDecision(
            action="buy", confidence=90, reason="우선",
            suggested_quantity=8,  # cost = 800,000
        ),
        "LOW": LLMDecision(
            action="buy", confidence=75, reason="후순위",
            suggested_quantity=5,  # cost = 500,000 → 합치면 1,300,000 > 1M
        ),
    })
    await run_analysis(
        db_session, r, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, min_confidence=70,
    )
    await db_session.commit()

    items = await _items_for_run(db_session, r.id)
    by_ticker = {i.ticker: i for i in items}
    assert by_ticker["HIGH"].decision == AnalysisItemDecision.PENDING
    assert by_ticker["LOW"].decision == AnalysisItemDecision.SKIPPED
    assert "예산" in (by_ticker["LOW"].blocked_reason or "")
    assert r.summary_json["skipped_over_budget"] == 1


@pytest.mark.asyncio
async def test_sell_qty_capped_to_advisory_holding(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.HOLDING,
            ref_price=Decimal("70000"),
            held_qty=Decimal("3"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="sell", confidence=80, reason="익절",
            suggested_quantity=100,  # 보유량 초과
        ),
    })
    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, min_confidence=70,
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, run.id))[0]
    assert it.action == AnalysisItemAction.SELL
    assert it.decision == AnalysisItemDecision.PENDING
    assert decrypt_decimal(it.suggested_qty) == Decimal("3")


@pytest.mark.asyncio
async def test_sell_on_non_holding_source_skipped(db_session, run):
    """AUTO_PICK source 인데 LLM이 SELL 을 제안하면 보유분 없으므로 skip."""
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="sell", confidence=90, reason="이상한 신호",
            suggested_quantity=5,
        ),
    })
    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, min_confidence=70,
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, run.id))[0]
    assert it.decision == AnalysisItemDecision.SKIPPED
    assert "advisory 미보유" in (it.blocked_reason or "")


@pytest.mark.asyncio
async def test_price_fetch_failure_falls_back_to_hold(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])

    async def failing_fetcher(_ticker):
        raise RuntimeError("KIS down")

    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=failing_fetcher, llm_caller=_llm_stub({}),
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, run.id))[0]
    assert it.action == AnalysisItemAction.HOLD
    assert "시세" in (it.blocked_reason or "")
    assert run.summary_json["failed"] >= 1


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_hold(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])

    async def failing_llm(*, ticker, ticker_name, price_history, portfolio):  # noqa: ARG001
        raise RuntimeError("API 5xx")

    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=failing_llm,
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, run.id))[0]
    assert it.action == AnalysisItemAction.HOLD
    assert "LLM" in (it.blocked_reason or "")


@pytest.mark.asyncio
async def test_run_status_and_expiry_set(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(action="hold", confidence=50, reason="대기"),
    })
    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, ttl_minutes=5,
    )
    await db_session.commit()
    await db_session.refresh(run)
    assert run.status == AnalysisRunStatus.READY
    assert run.completed_at is not None
    assert run.expires_at is not None
    delta = run.expires_at - run.completed_at
    assert 4 * 60 <= delta.total_seconds() <= 6 * 60


@pytest.mark.asyncio
async def test_budget_decrypt_failure_marks_run_failed(db_session, mock_user, account):
    """예산 복호화 실패는 fatal — 폴백으로 0 처리해 모든 BUY가 통과되면 안 됨."""
    r = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        mode=TradingMode.PAPER,
        budget_krw="garbage-not-valid-ciphertext",
        candidate_pool_options={},
    )
    db_session.add(r)
    await db_session.commit()

    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="buy", confidence=99, reason="강한 신호",
            suggested_quantity=10,
        ),
    })
    await run_analysis(
        db_session, r, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=llm, min_confidence=70,
    )
    await db_session.commit()
    await db_session.refresh(r)

    assert r.status == AnalysisRunStatus.FAILED
    assert r.error_message and "예산" in r.error_message


@pytest.mark.asyncio
async def test_per_ticker_pct_caps_quantity(db_session, mock_user, account):
    """종목당 비중 상한이 BUY 수량을 줄인다 — 예산은 충분."""
    r = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("100000000")),  # 1억 — 비중 cap 만 작동
        candidate_pool_options={},
    )
    db_session.add(r)
    await db_session.commit()

    # total_eval 1,000,000, max_position_pct 0.20 → 종목당 한도 = 200,000원.
    # ref_price=100,000, suggested_qty=5 → cost 500,000 (한도 초과)
    # 새 qty = floor(200,000 / 100,000) = 2
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("100000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="buy", confidence=90, reason="강한 추세",
            suggested_quantity=5,
        ),
    })
    await run_analysis(
        db_session, r, candidates=pool,
        portfolio=PortfolioContext(
            cash=Decimal("1000000"), total_eval=Decimal("1000000"), holdings=[],
        ),
        price_fetcher=_stub_price, llm_caller=llm,
        min_confidence=70, max_position_pct=Decimal("0.20"),
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, r.id))[0]
    assert it.decision == AnalysisItemDecision.PENDING
    assert decrypt_decimal(it.suggested_qty) == Decimal("2")
    assert "비중" in (it.blocked_reason or "")
    assert r.summary_json["capped_per_ticker_pct"] == 1
    assert r.summary_json["skipped_per_ticker_pct"] == 0


@pytest.mark.asyncio
async def test_per_ticker_pct_skips_when_under_one_share(
    db_session, mock_user, account,
):
    """비중 한도로 1주 미만이면 SKIPPED 마킹."""
    r = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("100000000")),
        candidate_pool_options={},
    )
    db_session.add(r)
    await db_session.commit()

    # total_eval 1,000,000 * 0.20 = 200,000 한도
    # ref_price = 500,000 → 한도 안에서 살 수 있는 정수 주식 0주 → SKIPPED
    pool = _candidate_pool([
        CandidateItem(
            ticker="EXPENSIVE", ticker_name="고가",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("500000"),
        ),
    ])
    llm = _llm_stub({
        "EXPENSIVE": LLMDecision(
            action="buy", confidence=95, reason="강함",
            suggested_quantity=1,
        ),
    })
    await run_analysis(
        db_session, r, candidates=pool,
        portfolio=PortfolioContext(
            cash=Decimal("1000000"), total_eval=Decimal("1000000"), holdings=[],
        ),
        price_fetcher=_stub_price, llm_caller=llm,
        min_confidence=70, max_position_pct=Decimal("0.20"),
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, r.id))[0]
    assert it.decision == AnalysisItemDecision.SKIPPED
    assert "1주 미만" in (it.blocked_reason or "")
    assert r.summary_json["skipped_per_ticker_pct"] == 1


@pytest.mark.asyncio
async def test_per_ticker_pct_within_limit_unchanged(
    db_session, mock_user, account,
):
    """이미 한도 내인 BUY 는 수량 변경 없음."""
    r = AnalysisRun(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        account_id=account.id,
        mode=TradingMode.PAPER,
        budget_krw=encrypt_decimal(Decimal("100000000")),
        candidate_pool_options={},
    )
    db_session.add(r)
    await db_session.commit()

    # total_eval 10,000,000 * 0.20 = 2,000,000 한도
    # cost = 70,000 * 10 = 700,000 — 한도 내
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])
    llm = _llm_stub({
        "005930": LLMDecision(
            action="buy", confidence=88, reason="추세",
            suggested_quantity=10,
        ),
    })
    await run_analysis(
        db_session, r, candidates=pool,
        portfolio=PortfolioContext(
            cash=Decimal("10000000"), total_eval=Decimal("10000000"), holdings=[],
        ),
        price_fetcher=_stub_price, llm_caller=llm,
        min_confidence=70, max_position_pct=Decimal("0.20"),
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, r.id))[0]
    assert decrypt_decimal(it.suggested_qty) == Decimal("10")
    assert r.summary_json["capped_per_ticker_pct"] == 0


@pytest.mark.asyncio
async def test_llm_timeout_falls_back_to_hold(db_session, run):
    pool = _candidate_pool([
        CandidateItem(
            ticker="005930", ticker_name="삼성",
            source=AnalysisItemSource.AUTO_PICK,
            ref_price=Decimal("70000"),
        ),
    ])

    async def slow_llm(*, ticker, ticker_name, price_history, portfolio):  # noqa: ARG001
        await asyncio.sleep(2)
        return LLMDecision(action="buy", confidence=99, reason="late")

    await run_analysis(
        db_session, run, candidates=pool, portfolio=_portfolio(),
        price_fetcher=_stub_price, llm_caller=slow_llm,
        llm_timeout=0.1,
    )
    await db_session.commit()

    it = (await _items_for_run(db_session, run.id))[0]
    assert it.action == AnalysisItemAction.HOLD
    assert "타임아웃" in (it.blocked_reason or "")
