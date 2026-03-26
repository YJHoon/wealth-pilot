"""시뮬레이션 서비스 + 라우터 통합 테스트

DCA 계산 정확성, 시나리오 분석, 포트폴리오 시뮬레이션,
라우터 POST /simulate 엔드포인트 검증.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.schemas.analysis import (
    DcaSimulationParams,
    MarketType,
    PortfolioSimulationParams,
    ScenarioSimulationParams,
)
from app.services.simulation_service import (
    SimulationError,
    run_dca_simulation,
    run_portfolio_simulation,
    run_scenario_simulation,
)


# ──────────────────────────────────────────────
# Mock 데이터 헬퍼
# ──────────────────────────────────────────────

def _make_monthly_prices(base: Decimal, count: int, trend: Decimal = Decimal("0")) -> list[Decimal]:
    """월별 가격 리스트 생성 (base부터 trend 만큼 증가)."""
    return [base + trend * i for i in range(count)]


def _make_history_rows(prices: list[Decimal]) -> list[dict]:
    """_fetch_history_sync 반환 형태의 row 리스트 생성."""
    from datetime import datetime, timezone
    rows = []
    for i, price in enumerate(prices):
        # 매월 15일로 설정
        dt = datetime(2023, 1 + (i % 12), 15, tzinfo=timezone.utc)
        if i >= 12:
            dt = dt.replace(year=2023 + i // 12)
        rows.append({
            "date": dt,
            "close": price,
            "high": price + Decimal("100"),
            "low": price - Decimal("100"),
            "volume": 1000000,
        })
    return rows


# ──────────────────────────────────────────────
# DCA 시뮬레이션 단위 테스트
# ──────────────────────────────────────────────

class TestDcaSimulation:
    """DCA(월적립) 시뮬레이션 계산 정확성 테스트."""

    @pytest.mark.asyncio
    async def test_dca_constant_price(self):
        """가격이 일정할 때: 수익률 0%, 총 투자 = 최종 가치."""
        prices = _make_monthly_prices(Decimal("10000"), 12)
        history = _make_history_rows(prices)

        params = DcaSimulationParams(
            ticker="005930", market=MarketType.KRX,
            monthly_amount=Decimal("100000"), months=12,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            result = await run_dca_simulation(params)

        assert result.return_rate == Decimal("0.00")
        assert result.total_invested == Decimal("1200000")
        assert result.final_value == result.total_invested
        assert len(result.monthly_breakdown) == 12

    @pytest.mark.asyncio
    async def test_dca_rising_price(self):
        """가격이 상승할 때: 양의 수익률."""
        prices = _make_monthly_prices(Decimal("10000"), 6, Decimal("1000"))
        history = _make_history_rows(prices)

        params = DcaSimulationParams(
            ticker="005930", market=MarketType.KRX,
            monthly_amount=Decimal("100000"), months=6,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            result = await run_dca_simulation(params)

        assert result.return_rate > 0
        assert result.final_value > result.total_invested

    @pytest.mark.asyncio
    async def test_dca_falling_price(self):
        """가격이 하락할 때: 음의 수익률."""
        prices = _make_monthly_prices(Decimal("15000"), 6, Decimal("-1000"))
        history = _make_history_rows(prices)

        params = DcaSimulationParams(
            ticker="005930", market=MarketType.KRX,
            monthly_amount=Decimal("100000"), months=6,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            result = await run_dca_simulation(params)

        assert result.return_rate < 0
        assert result.final_value < result.total_invested

    @pytest.mark.asyncio
    async def test_dca_breakdown_accumulation(self):
        """월별 breakdown의 누적 투자/주식 수가 올바른지 확인."""
        prices = _make_monthly_prices(Decimal("50000"), 3)
        history = _make_history_rows(prices)

        params = DcaSimulationParams(
            ticker="005930", market=MarketType.KRX,
            monthly_amount=Decimal("100000"), months=3,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            result = await run_dca_simulation(params)

        assert len(result.monthly_breakdown) == 3
        # 누적 투자금 확인
        assert result.monthly_breakdown[0].cumulative_invested == Decimal("100000")
        assert result.monthly_breakdown[1].cumulative_invested == Decimal("200000")
        assert result.monthly_breakdown[2].cumulative_invested == Decimal("300000")

    @pytest.mark.asyncio
    async def test_dca_no_data_raises(self):
        """데이터 없으면 SimulationError."""
        params = DcaSimulationParams(
            ticker="INVALID", market=MarketType.KRX,
            monthly_amount=Decimal("100000"), months=12,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=[],
        ), pytest.raises(SimulationError):
            await run_dca_simulation(params)


# ──────────────────────────────────────────────
# Scenario 시뮬레이션 단위 테스트
# ──────────────────────────────────────────────

class TestScenarioSimulation:
    """시나리오 분석 계산 정확성 테스트."""

    @pytest.mark.asyncio
    async def test_scenario_basic(self):
        """기본 시나리오: 진입 10000, 목표 12000, 손절 9000, 수량 10."""
        params = ScenarioSimulationParams(
            ticker="005930", market=MarketType.KRX,
            entry_price=Decimal("10000"),
            quantity=Decimal("10"),
            target_price=Decimal("12000"),
            stop_loss_price=Decimal("9000"),
        )

        result = await run_scenario_simulation(params)

        assert result.potential_profit == Decimal("20000.00")
        assert result.potential_loss == Decimal("10000.00")
        assert result.risk_reward_ratio == Decimal("2.00")
        assert result.profit_pct == Decimal("20.00")
        assert result.loss_pct == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_scenario_risk_reward_ratio(self):
        """위험보상비 계산이 정확한지."""
        params = ScenarioSimulationParams(
            ticker="AAPL", market=MarketType.NASDAQ,
            entry_price=Decimal("150"),
            quantity=Decimal("100"),
            target_price=Decimal("180"),
            stop_loss_price=Decimal("140"),
        )

        result = await run_scenario_simulation(params)

        # profit: (180-150)*100 = 3000, loss: (150-140)*100 = 1000
        assert result.potential_profit == Decimal("3000.00")
        assert result.potential_loss == Decimal("1000.00")
        assert result.risk_reward_ratio == Decimal("3.00")

    @pytest.mark.asyncio
    async def test_scenario_negative_target(self):
        """목표가가 진입가보다 낮은 경우 (숏 포지션)."""
        params = ScenarioSimulationParams(
            ticker="005930", market=MarketType.KRX,
            entry_price=Decimal("10000"),
            quantity=Decimal("5"),
            target_price=Decimal("8000"),
            stop_loss_price=Decimal("11000"),
        )

        result = await run_scenario_simulation(params)

        assert result.potential_profit == Decimal("-10000.00")
        assert result.potential_loss == Decimal("-5000.00")


# ──────────────────────────────────────────────
# Portfolio 시뮬레이션 단위 테스트
# ──────────────────────────────────────────────

class TestPortfolioSimulation:
    """포트폴리오 리밸런싱 시뮬레이션 테스트."""

    @pytest.mark.asyncio
    async def test_portfolio_single_ticker_constant(self):
        """단일 종목 + 일정 가격 → 수익률 0%."""
        prices = _make_monthly_prices(Decimal("50000"), 6)
        history = _make_history_rows(prices)

        params = PortfolioSimulationParams(
            tickers=["005930"],
            weights=[Decimal("1.0")],
            initial_amount=Decimal("1000000"),
            months=6,
            rebalance_interval_months=3,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            result = await run_portfolio_simulation(params)

        assert result.return_rate == Decimal("0.00")
        assert result.total_invested == Decimal("1000000")

    @pytest.mark.asyncio
    async def test_portfolio_rebalance_events(self):
        """리밸런싱 이벤트가 올바른 간격으로 생성되는지."""
        prices = _make_monthly_prices(Decimal("50000"), 12)
        history = _make_history_rows(prices)

        params = PortfolioSimulationParams(
            tickers=["005930"],
            weights=[Decimal("1.0")],
            initial_amount=Decimal("1000000"),
            months=12,
            rebalance_interval_months=3,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            result = await run_portfolio_simulation(params)

        # 12개월, 3개월 간격 → month 3, 6, 9 에 리밸런싱 (총 3회)
        assert len(result.rebalance_events) == 3
        assert [e.month for e in result.rebalance_events] == [3, 6, 9]

    @pytest.mark.asyncio
    async def test_portfolio_weight_normalization(self):
        """비중을 퍼센트(60, 40)로 입력해도 정상 동작."""
        prices_a = _make_monthly_prices(Decimal("50000"), 6)
        prices_b = _make_monthly_prices(Decimal("30000"), 6)
        history_a = _make_history_rows(prices_a)
        history_b = _make_history_rows(prices_b)

        params = PortfolioSimulationParams(
            tickers=["005930", "000660"],
            weights=[Decimal("60"), Decimal("40")],
            initial_amount=Decimal("1000000"),
            months=6,
            rebalance_interval_months=3,
        )

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            side_effect=[history_a, history_b],
        ):
            result = await run_portfolio_simulation(params)

        # 일정 가격이므로 수익률은 약 0%
        assert result.return_rate == Decimal("0.00")


# ──────────────────────────────────────────────
# 라우터 통합 테스트
# ──────────────────────────────────────────────

class TestSimulateEndpoint:
    """POST /api/analysis/simulate 라우터 테스트."""

    @pytest.mark.asyncio
    async def test_simulate_scenario(
        self, auth_client: AsyncClient, mock_user: User,
    ):
        """시나리오 시뮬레이션 201 응답."""
        resp = await auth_client.post("/api/analysis/simulate", json={
            "params": {
                "type": "scenario",
                "ticker": "005930",
                "market": "KRX",
                "entry_price": "10000",
                "quantity": "10",
                "target_price": "12000",
                "stop_loss_price": "9000",
            },
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "scenario"
        assert Decimal(data["result"]["potential_profit"]) == Decimal("20000")
        assert Decimal(data["result"]["risk_reward_ratio"]) == Decimal("2")

    @pytest.mark.asyncio
    async def test_simulate_dca(
        self, auth_client: AsyncClient, mock_user: User,
    ):
        """DCA 시뮬레이션 mock + 201 응답."""
        prices = _make_monthly_prices(Decimal("10000"), 6)
        history = _make_history_rows(prices)

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            resp = await auth_client.post("/api/analysis/simulate", json={
                "params": {
                    "type": "dca",
                    "ticker": "005930",
                    "market": "KRX",
                    "monthly_amount": "100000",
                    "months": 6,
                },
            })

        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "dca"
        assert Decimal(data["result"]["return_rate"]) == Decimal("0")

    @pytest.mark.asyncio
    async def test_simulate_invalid_type(
        self, auth_client: AsyncClient, mock_user: User,
    ):
        """잘못된 시뮬레이션 타입 → 422."""
        resp = await auth_client.post("/api/analysis/simulate", json={
            "params": {
                "type": "invalid",
                "ticker": "005930",
            },
        })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_simulate_dca_invalid_months(
        self, auth_client: AsyncClient, mock_user: User,
    ):
        """DCA months=0 → 422 (Pydantic validation)."""
        resp = await auth_client.post("/api/analysis/simulate", json={
            "params": {
                "type": "dca",
                "ticker": "005930",
                "market": "KRX",
                "monthly_amount": "100000",
                "months": 0,
            },
        })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_simulate_portfolio(
        self, auth_client: AsyncClient, mock_user: User,
    ):
        """포트폴리오 시뮬레이션 mock + 201 응답."""
        prices = _make_monthly_prices(Decimal("50000"), 6)
        history = _make_history_rows(prices)

        with patch(
            "app.services.simulation_service._fetch_history_sync",
            return_value=history,
        ):
            resp = await auth_client.post("/api/analysis/simulate", json={
                "params": {
                    "type": "portfolio",
                    "tickers": ["005930"],
                    "weights": ["1.0"],
                    "initial_amount": "1000000",
                    "months": 6,
                    "rebalance_interval_months": 3,
                },
            })

        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "portfolio"
