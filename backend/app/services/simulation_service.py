"""시뮬레이션 서비스 — DCA / 포트폴리오 리밸런싱 / 시나리오 분석

yfinance 과거 데이터 기반. 모든 금융 연산은 Decimal로 수행 (float 금지).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Simulation, SimulationType
from app.schemas.analysis import (
    DcaSimulationParams,
    DcaSimulationResult,
    MonthlyBreakdownItem,
    PortfolioSimulationParams,
    PortfolioSimulationResult,
    RebalanceEvent,
    ScenarioSimulationParams,
    ScenarioSimulationResult,
    SimulationParams,
    SimulationResponse,
)
from app.services.stock_analysis_service import (
    _fetch_history_sync,
    _to_yfinance_ticker,
)

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 15
_SIMULATION_EXPIRY_DAYS = 30


# ──────────────────────────────────────────────
# 도메인 예외
# ──────────────────────────────────────────────

class SimulationError(Exception):
    """시뮬레이션 도메인 예외."""


# ──────────────────────────────────────────────
# 과거 데이터 fetch 헬퍼
# ──────────────────────────────────────────────

async def _fetch_monthly_prices(
    ticker: str, market: str, months: int,
) -> list[Decimal]:
    """yfinance에서 월별 종가 리스트를 가져온다 (오래된 순).

    months 기간에 맞는 period를 계산하여 fetch 후,
    월 단위로 리샘플링하여 각 월의 마지막 종가를 반환한다.
    """
    # yfinance period 문자열 결정
    years = months // 12 + 1
    period = f"{years}y" if years <= 10 else "max"

    candidates = _to_yfinance_ticker(ticker, market)
    try:
        history = await asyncio.wait_for(
            asyncio.to_thread(_fetch_history_sync, candidates, period),
            timeout=_FETCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise SimulationError(f"종목 시세 조회 시간 초과: {ticker}") from None
    except Exception as exc:
        raise SimulationError(f"종목 시세 조회 실패: {ticker}") from exc

    if not history:
        raise SimulationError(f"종목 시세 데이터 없음: {ticker}")

    # 월별 리샘플링: 같은 (year, month) 그룹의 마지막 종가
    monthly: dict[tuple[int, int], Decimal] = {}
    for row in history:
        dt: datetime = row["date"]
        key = (dt.year, dt.month)
        monthly[key] = row["close"]

    prices = list(monthly.values())

    if len(prices) < 2:
        raise SimulationError(
            f"시뮬레이션에 필요한 데이터가 부족합니다: {ticker} ({len(prices)}개월)"
        )

    # 요청 기간보다 데이터가 적으면 있는 만큼만 사용
    return prices[-months:] if len(prices) >= months else prices


# ──────────────────────────────────────────────
# DCA (월적립) 시뮬레이션
# ──────────────────────────────────────────────

async def run_dca_simulation(params: DcaSimulationParams) -> DcaSimulationResult:
    """월적립 시뮬레이션: 매월 고정 금액 투자 → 월별 breakdown + 총수익률."""
    prices = await _fetch_monthly_prices(params.ticker, params.market.value, params.months)

    monthly_amount = params.monthly_amount
    cumulative_invested = Decimal(0)
    cumulative_shares = Decimal(0)
    breakdown: list[MonthlyBreakdownItem] = []

    for i, price in enumerate(prices):
        if price <= 0:
            continue

        shares_bought = (monthly_amount / price).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP,
        )
        cumulative_invested += monthly_amount
        cumulative_shares += shares_bought
        portfolio_value = (cumulative_shares * price).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

        breakdown.append(MonthlyBreakdownItem(
            month=i + 1,
            invested=monthly_amount,
            cumulative_invested=cumulative_invested,
            shares_bought=shares_bought,
            cumulative_shares=cumulative_shares,
            price=price,
            portfolio_value=portfolio_value,
        ))

    if not breakdown:
        raise SimulationError("유효한 가격 데이터가 없어 시뮬레이션을 실행할 수 없습니다.")

    final_value = breakdown[-1].portfolio_value
    total_invested = breakdown[-1].cumulative_invested

    return_rate = Decimal(0)
    if total_invested > 0:
        return_rate = (
            (final_value - total_invested) / total_invested * Decimal(100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return DcaSimulationResult(
        total_invested=total_invested,
        final_value=final_value,
        return_rate=return_rate,
        monthly_breakdown=breakdown,
    )


# ──────────────────────────────────────────────
# Portfolio (포트폴리오 리밸런싱) 시뮬레이션
# ──────────────────────────────────────────────

async def run_portfolio_simulation(
    params: PortfolioSimulationParams,
) -> PortfolioSimulationResult:
    """다종목 포트폴리오 리밸런싱 시뮬레이션."""
    # 비중 합계 검증 (100% = 1.0)
    weight_sum = sum(params.weights)
    if weight_sum <= 0:
        raise SimulationError("비중 합계가 0 이하입니다.")

    # 정규화 (비율/퍼센트 입력 모두 대응)
    normalized_weights = [
        (w / weight_sum).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        for w in params.weights
    ]

    # 모든 종목의 월별 가격 병렬 fetch (종목 코드 형태로 시장 추론)
    price_tasks = [
        _fetch_monthly_prices(
            ticker,
            "KRX" if ticker.isdigit() and len(ticker) == 6 else "US",
            params.months,
        )
        for ticker in params.tickers
    ]
    all_prices = await asyncio.gather(*price_tasks, return_exceptions=True)

    # 에러 체크
    for i, result in enumerate(all_prices):
        if isinstance(result, Exception):
            raise SimulationError(
                f"종목 {params.tickers[i]} 데이터 조회 실패: {result}"
            )

    price_lists: list[list[Decimal]] = list(all_prices)  # type: ignore[arg-type]

    # 공통 기간 (가장 짧은 종목 기준)
    min_length = min(len(p) for p in price_lists)
    if min_length < 2:
        raise SimulationError("포트폴리오 시뮬레이션에 필요한 공통 데이터가 부족합니다.")

    for i in range(len(price_lists)):
        price_lists[i] = price_lists[i][-min_length:]

    # 초기 할당
    total_value = params.initial_amount
    num_tickers = len(params.tickers)
    # 각 종목별 보유 수량
    holdings = [Decimal(0)] * num_tickers
    for j in range(num_tickers):
        if price_lists[j][0] > 0:
            alloc = total_value * normalized_weights[j]
            holdings[j] = (alloc / price_lists[j][0]).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP,
            )

    rebalance_events: list[RebalanceEvent] = []

    for month_idx in range(1, min_length):
        # 현재 포트폴리오 가치
        current_value = sum(
            holdings[j] * price_lists[j][month_idx]
            for j in range(num_tickers)
        )

        # 리밸런싱 시점 체크
        if month_idx % params.rebalance_interval_months == 0:
            pre_value = current_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # 리밸런싱: 목표 비중으로 재분배
            allocations: dict[str, Decimal] = {}
            for j in range(num_tickers):
                alloc = current_value * normalized_weights[j]
                price = price_lists[j][month_idx]
                if price > 0:
                    holdings[j] = (alloc / price).quantize(
                        Decimal("0.000001"), rounding=ROUND_HALF_UP,
                    )
                actual_pct = Decimal(0)
                if current_value > 0:
                    actual_pct = (
                        holdings[j] * price / current_value * Decimal(100)
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                allocations[params.tickers[j]] = actual_pct

            post_value = sum(
                holdings[j] * price_lists[j][month_idx]
                for j in range(num_tickers)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            rebalance_events.append(RebalanceEvent(
                month=month_idx,
                pre_rebalance_value=pre_value,
                post_rebalance_value=post_value,
                allocations=allocations,
            ))

    # 최종 가치
    final_value = sum(
        holdings[j] * price_lists[j][-1]
        for j in range(num_tickers)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return_rate = Decimal(0)
    if params.initial_amount > 0:
        return_rate = (
            (final_value - params.initial_amount) / params.initial_amount * Decimal(100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return PortfolioSimulationResult(
        total_invested=params.initial_amount,
        final_value=final_value,
        return_rate=return_rate,
        rebalance_events=rebalance_events,
    )


# ──────────────────────────────────────────────
# Scenario (시나리오 분석)
# ──────────────────────────────────────────────

async def run_scenario_simulation(
    params: ScenarioSimulationParams,
) -> ScenarioSimulationResult:
    """진입가/수량/목표가/손절가 → 잠재 수익/손실/위험보상비."""
    entry = params.entry_price
    qty = params.quantity
    target = params.target_price
    stop_loss = params.stop_loss_price

    potential_profit = ((target - entry) * qty).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    potential_loss = ((entry - stop_loss) * qty).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )

    profit_pct = Decimal(0)
    loss_pct = Decimal(0)
    if entry > 0:
        profit_pct = (
            (target - entry) / entry * Decimal(100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        loss_pct = (
            (entry - stop_loss) / entry * Decimal(100)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    risk_reward_ratio = Decimal(0)
    if potential_loss != 0:
        risk_reward_ratio = (abs(potential_profit) / abs(potential_loss)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

    return ScenarioSimulationResult(
        potential_profit=potential_profit,
        potential_loss=potential_loss,
        risk_reward_ratio=risk_reward_ratio,
        profit_pct=profit_pct,
        loss_pct=loss_pct,
    )


# ──────────────────────────────────────────────
# 통합 실행 + DB 저장
# ──────────────────────────────────────────────

_TYPE_MAP = {
    "dca": SimulationType.DCA,
    "portfolio": SimulationType.PORTFOLIO,
    "scenario": SimulationType.SCENARIO,
}


async def run_simulation(
    db: AsyncSession,
    user_id: UUID,
    params: SimulationParams,
) -> SimulationResponse:
    """파라미터 타입에 따라 적절한 시뮬레이션을 실행하고 DB에 저장."""
    if isinstance(params, DcaSimulationParams):
        result = await run_dca_simulation(params)
    elif isinstance(params, PortfolioSimulationParams):
        result = await run_portfolio_simulation(params)
    elif isinstance(params, ScenarioSimulationParams):
        result = await run_scenario_simulation(params)
    else:
        raise SimulationError("지원하지 않는 시뮬레이션 타입입니다.")

    now = datetime.now(timezone.utc)
    sim = Simulation(
        user_id=user_id,
        type=_TYPE_MAP[params.type],
        params=params.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        expires_at=now + timedelta(days=_SIMULATION_EXPIRY_DAYS),
    )
    db.add(sim)
    await db.flush()

    return SimulationResponse(
        id=sim.id,
        type=sim.type,
        params=params,
        result=result,
        created_at=sim.created_at or now,
        expires_at=sim.expires_at,
    )
