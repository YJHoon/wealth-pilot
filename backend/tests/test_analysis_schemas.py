"""투자 분석 스키마 validation 단위 테스트."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.analysis import (
    INVESTMENT_DISCLAIMER_KO,
    DcaSimulationParams,
    DcaSimulationResult,
    FundamentalAnalysisResponse,
    MarketType,
    PortfolioSimulationParams,
    PortfolioSimulationResult,
    ScenarioSimulationParams,
    ScenarioSimulationResult,
    SimulationRequest,
    SimulationResponse,
    TechnicalAnalysisResponse,
    TradingSignalAction,
    TradingSignalsResponse,
    ValuationSignal,
    WatchlistCreate,
    WatchlistResponse,
    WatchlistUpdate,
    watchlist_to_response,
)
from app.models.analysis import SimulationType


# ──────────────────────────────────────────────
# 면책 고지 상수
# ──────────────────────────────────────────────

def test_disclaimer_not_empty():
    assert len(INVESTMENT_DISCLAIMER_KO) > 0
    assert "투자 자문이 아니며" in INVESTMENT_DISCLAIMER_KO
    assert "미래 수익을 보장하지 않습니다" in INVESTMENT_DISCLAIMER_KO


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

def test_valuation_signal_values():
    assert ValuationSignal.UNDERVALUED == "undervalued"
    assert ValuationSignal.FAIR == "fair"
    assert ValuationSignal.OVERVALUED == "overvalued"


def test_trading_signal_action_values():
    assert TradingSignalAction.BUY == "buy"
    assert TradingSignalAction.SELL == "sell"
    assert TradingSignalAction.HOLD == "hold"


def test_market_type_values():
    assert MarketType.KRX == "KRX"
    assert MarketType.NASDAQ == "NASDAQ"
    assert MarketType.NYSE == "NYSE"
    assert MarketType.CRYPTO == "CRYPTO"


def test_simulation_type_values():
    assert SimulationType.DCA == "dca"
    assert SimulationType.PORTFOLIO == "portfolio"
    assert SimulationType.SCENARIO == "scenario"


# ──────────────────────────────────────────────
# FundamentalAnalysisResponse
# ──────────────────────────────────────────────

def test_fundamental_response_minimal():
    resp = FundamentalAnalysisResponse(ticker="005930", market="KRX")
    assert resp.ticker == "005930"
    assert resp.market == "KRX"
    assert resp.disclaimer == INVESTMENT_DISCLAIMER_KO
    assert resp.per is None
    assert resp.valuation_signal is None


def test_fundamental_response_full():
    now = datetime.now(timezone.utc)
    resp = FundamentalAnalysisResponse(
        ticker="AAPL",
        market="NASDAQ",
        company_name="Apple Inc.",
        sector="Technology",
        per=Decimal("28.5"),
        pbr=Decimal("45.2"),
        roe=Decimal("160.5"),
        eps=Decimal("6.42"),
        sector_avg_per=Decimal("25.0"),
        sector_avg_pbr=Decimal("10.0"),
        dcf_fair_value=Decimal("180.00"),
        current_price=Decimal("175.50"),
        price_gap_pct=Decimal("-2.5"),
        valuation_signal=ValuationSignal.UNDERVALUED,
        data_source="yfinance",
        updated_at=now,
    )
    assert resp.valuation_signal == ValuationSignal.UNDERVALUED
    assert resp.dcf_fair_value == Decimal("180.00")


# ──────────────────────────────────────────────
# TechnicalAnalysisResponse
# ──────────────────────────────────────────────

def test_technical_response_minimal():
    resp = TechnicalAnalysisResponse(ticker="005930", market="KRX")
    assert resp.rsi is None
    assert resp.macd is None
    assert resp.disclaimer == INVESTMENT_DISCLAIMER_KO


def test_technical_response_full():
    resp = TechnicalAnalysisResponse(
        ticker="AAPL",
        market="NASDAQ",
        rsi=Decimal("65.3"),
        macd=Decimal("2.15"),
        macd_signal=Decimal("1.80"),
        macd_histogram=Decimal("0.35"),
        bollinger_upper=Decimal("185.0"),
        bollinger_middle=Decimal("175.0"),
        bollinger_lower=Decimal("165.0"),
        sma_5=Decimal("176.0"),
        sma_20=Decimal("174.0"),
        sma_60=Decimal("170.0"),
        sma_120=Decimal("165.0"),
        support_level=Decimal("168.0"),
        resistance_level=Decimal("182.0"),
        current_price=Decimal("175.50"),
        data_source="yfinance",
    )
    assert resp.rsi == Decimal("65.3")
    assert resp.sma_120 == Decimal("165.0")


def test_technical_response_rsi_out_of_range():
    """RSI는 0~100 범위만 허용."""
    with pytest.raises(ValidationError):
        TechnicalAnalysisResponse(ticker="AAPL", market="NASDAQ", rsi=Decimal("140"))

    with pytest.raises(ValidationError):
        TechnicalAnalysisResponse(ticker="AAPL", market="NASDAQ", rsi=Decimal("-5"))


def test_technical_response_rsi_boundary():
    """RSI 경계값 (0, 100) 허용."""
    resp0 = TechnicalAnalysisResponse(ticker="AAPL", market="NASDAQ", rsi=Decimal("0"))
    assert resp0.rsi == Decimal("0")

    resp100 = TechnicalAnalysisResponse(ticker="AAPL", market="NASDAQ", rsi=Decimal("100"))
    assert resp100.rsi == Decimal("100")


# ──────────────────────────────────────────────
# TradingSignalsResponse
# ──────────────────────────────────────────────

def test_trading_signals_response():
    resp = TradingSignalsResponse(
        ticker="005930",
        market="KRX",
        action=TradingSignalAction.BUY,
        confidence=Decimal("75.5"),
        risk_level="중",
        reasons=["PER 저평가", "RSI 과매도 구간"],
        fundamental_score=Decimal("80"),
        technical_score=Decimal("70"),
        current_price=Decimal("72000"),
    )
    assert resp.action == TradingSignalAction.BUY
    assert len(resp.reasons) == 2
    assert resp.disclaimer == INVESTMENT_DISCLAIMER_KO


def test_trading_signals_confidence_validation():
    """confidence는 0~100 범위만 허용."""
    with pytest.raises(ValidationError):
        TradingSignalsResponse(
            ticker="AAPL",
            market="NASDAQ",
            action=TradingSignalAction.HOLD,
            confidence=Decimal("150"),  # 초과
            risk_level="하",
        )

    with pytest.raises(ValidationError):
        TradingSignalsResponse(
            ticker="AAPL",
            market="NASDAQ",
            action=TradingSignalAction.HOLD,
            confidence=Decimal("-1"),  # 미만
            risk_level="하",
        )


# ──────────────────────────────────────────────
# WatchlistCreate
# ──────────────────────────────────────────────

def test_watchlist_create_valid():
    data = WatchlistCreate(
        ticker="005930",
        market=MarketType.KRX,
        target_buy_price=Decimal("70000"),
        target_sell_price=Decimal("90000"),
        alert_threshold_pct=Decimal("5.0"),
        notes="삼성전자 관심",
    )
    assert data.ticker == "005930"
    assert data.market == MarketType.KRX
    assert data.target_buy_price == Decimal("70000")


def test_watchlist_create_minimal():
    data = WatchlistCreate(ticker="AAPL", market=MarketType.NASDAQ)
    assert data.target_buy_price is None
    assert data.target_sell_price is None
    assert data.notes is None


def test_watchlist_create_invalid_price():
    """매수/매도 가격은 0보다 커야 함."""
    with pytest.raises(ValidationError):
        WatchlistCreate(
            ticker="AAPL",
            market=MarketType.NASDAQ,
            target_buy_price=Decimal("-100"),
        )


def test_watchlist_create_invalid_threshold():
    """alert_threshold_pct는 0~100 범위."""
    with pytest.raises(ValidationError):
        WatchlistCreate(
            ticker="AAPL",
            market=MarketType.NASDAQ,
            alert_threshold_pct=Decimal("150"),
        )


def test_watchlist_create_invalid_market():
    """잘못된 마켓 타입은 거부."""
    with pytest.raises(ValidationError):
        WatchlistCreate(ticker="AAPL", market="INVALID")


# ──────────────────────────────────────────────
# WatchlistUpdate
# ──────────────────────────────────────────────

def test_watchlist_update_partial():
    data = WatchlistUpdate(target_buy_price=Decimal("65000"))
    assert data.target_buy_price == Decimal("65000")
    assert data.target_sell_price is None


def test_watchlist_update_empty():
    """모든 필드 None도 허용 (부분 업데이트)."""
    data = WatchlistUpdate()
    assert data.target_buy_price is None


def test_watchlist_update_invalid_price():
    """Update에서도 매수/매도 가격은 0보다 커야 함."""
    with pytest.raises(ValidationError):
        WatchlistUpdate(target_buy_price=Decimal("0"))

    with pytest.raises(ValidationError):
        WatchlistUpdate(target_sell_price=Decimal("-500"))


# ──────────────────────────────────────────────
# WatchlistResponse + watchlist_to_response
# ──────────────────────────────────────────────

def test_watchlist_response():
    now = datetime.now(timezone.utc)
    resp = WatchlistResponse(
        id=uuid4(),
        ticker="005930",
        market="KRX",
        target_buy_price=Decimal("70000"),
        target_sell_price=Decimal("90000"),
        alert_threshold_pct=Decimal("5.0"),
        notes="테스트",
        created_at=now,
        updated_at=now,
    )
    assert resp.ticker == "005930"


def test_watchlist_to_response_with_encrypted_prices(monkeypatch):
    """watchlist_to_response가 암호화 필드를 복호화하여 매핑하는지 검증."""
    now = datetime.now(timezone.utc)
    wl_id = uuid4()

    # Mock Watchlist 모델 (DB에서 읽어온 상태)
    mock_wl = MagicMock()
    mock_wl.id = wl_id
    mock_wl.ticker = "005930"
    mock_wl.market = "KRX"
    mock_wl.target_buy_price = "ENCRYPTED_BUY"
    mock_wl.target_sell_price = "ENCRYPTED_SELL"
    mock_wl.alert_threshold_pct = Decimal("5.0")
    mock_wl.notes = "삼성전자"
    mock_wl.created_at = now
    mock_wl.updated_at = now

    # decrypt_decimal_optional을 모킹
    monkeypatch.setattr(
        "app.schemas.analysis.decrypt_decimal_optional",
        lambda v: Decimal("70000") if v == "ENCRYPTED_BUY"
        else Decimal("90000") if v == "ENCRYPTED_SELL"
        else None,
    )

    resp = watchlist_to_response(mock_wl)
    assert resp.id == wl_id
    assert resp.ticker == "005930"
    assert resp.market == "KRX"
    assert resp.target_buy_price == Decimal("70000")
    assert resp.target_sell_price == Decimal("90000")
    assert resp.alert_threshold_pct == Decimal("5.0")
    assert resp.notes == "삼성전자"


def test_watchlist_to_response_with_none_prices(monkeypatch):
    """목표가가 None인 경우 watchlist_to_response가 None을 반환하는지 검증."""
    now = datetime.now(timezone.utc)

    mock_wl = MagicMock()
    mock_wl.id = uuid4()
    mock_wl.ticker = "AAPL"
    mock_wl.market = "NASDAQ"
    mock_wl.target_buy_price = None
    mock_wl.target_sell_price = None
    mock_wl.alert_threshold_pct = None
    mock_wl.notes = None
    mock_wl.created_at = now
    mock_wl.updated_at = now

    monkeypatch.setattr(
        "app.schemas.analysis.decrypt_decimal_optional",
        lambda v: None,
    )

    resp = watchlist_to_response(mock_wl)
    assert resp.target_buy_price is None
    assert resp.target_sell_price is None
    assert resp.alert_threshold_pct is None
    assert resp.notes is None


# ──────────────────────────────────────────────
# SimulationRequest / SimulationResponse (타입별 모델)
# ──────────────────────────────────────────────

def test_simulation_request_dca():
    req = SimulationRequest(
        params={
            "type": "dca",
            "ticker": "AAPL",
            "market": "NASDAQ",
            "monthly_amount": 500000,
            "months": 12,
        },
    )
    assert isinstance(req.params, DcaSimulationParams)
    assert req.params.monthly_amount == Decimal("500000")
    assert req.params.months == 12


def test_simulation_request_portfolio():
    req = SimulationRequest(
        params={
            "type": "portfolio",
            "tickers": ["AAPL", "GOOGL"],
            "weights": ["0.6", "0.4"],
            "initial_amount": 10000000,
            "months": 24,
        },
    )
    assert isinstance(req.params, PortfolioSimulationParams)
    assert len(req.params.tickers) == 2


def test_simulation_request_scenario():
    req = SimulationRequest(
        params={
            "type": "scenario",
            "ticker": "005930",
            "market": "KRX",
            "entry_price": 72000,
            "quantity": 10,
            "target_price": 85000,
            "stop_loss_price": 65000,
        },
    )
    assert isinstance(req.params, ScenarioSimulationParams)
    assert req.params.entry_price == Decimal("72000")


def test_simulation_request_invalid_discriminator():
    """잘못된 type 값은 거부."""
    with pytest.raises(ValidationError):
        SimulationRequest(
            params={"type": "invalid", "ticker": "AAPL"},
        )


def test_simulation_request_dca_missing_fields():
    """DCA 필수 필드 누락 시 거부."""
    with pytest.raises(ValidationError):
        SimulationRequest(
            params={"type": "dca", "ticker": "AAPL"},
        )


def test_simulation_request_dca_invalid_amount():
    """월적립 금액은 0보다 커야 함."""
    with pytest.raises(ValidationError):
        SimulationRequest(
            params={
                "type": "dca",
                "ticker": "AAPL",
                "market": "NASDAQ",
                "monthly_amount": 0,
                "months": 12,
            },
        )


def test_simulation_response_dca():
    now = datetime.now(timezone.utc)
    resp = SimulationResponse(
        id=uuid4(),
        type=SimulationType.DCA,
        params={
            "type": "dca",
            "ticker": "AAPL",
            "market": "NASDAQ",
            "monthly_amount": 500000,
            "months": 12,
        },
        result={
            "total_invested": 6000000,
            "final_value": 7200000,
            "return_rate": 20,
        },
        created_at=now,
        expires_at=now,
    )
    assert resp.type == SimulationType.DCA
    assert isinstance(resp.params, DcaSimulationParams)
    assert isinstance(resp.result, DcaSimulationResult)
    assert resp.result.final_value == Decimal("7200000")
