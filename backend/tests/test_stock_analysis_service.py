"""종목 분석 서비스 테스트 — mocked yfinance 기반 지표 계산 정확성 검증"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import asyncio
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.stock_analysis_service import (
    StockAnalysisError,
    _cache,
    _last_nonzero,
    _quantize,
    _to_decimal,
    _to_yfinance_ticker,
    get_fundamental_analysis,
    get_technical_analysis,
    get_trading_signals,
)
from app.services.trading_strategy import _sma


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_cache():
    """각 테스트 전 캐시 초기화."""
    _cache.clear()
    yield
    _cache.clear()


def _make_mock_info(overrides: dict | None = None) -> dict:
    """yfinance Ticker.info mock 데이터."""
    base = {
        "shortName": "Test Corp",
        "sector": "Technology",
        "trailingPE": 15.5,
        "priceToBook": 2.3,
        "returnOnEquity": 0.18,
        "trailingEps": 5000,
        "currentPrice": 75000,
        "regularMarketPrice": 75000,
    }
    if overrides:
        base.update(overrides)
    return base


def _make_mock_history_df(
    length: int = 120,
    start_price: float = 50000,
    trend: float = 100,
) -> pd.DataFrame:
    """yfinance Ticker.history() mock DataFrame 생성.

    단순 상승 추세 데이터.
    """
    dates = pd.date_range(end=datetime.now(), periods=length, freq="B")
    data = {
        "Open": [],
        "High": [],
        "Low": [],
        "Close": [],
        "Volume": [],
    }
    price = start_price
    for i in range(length):
        close = price + trend * i
        data["Open"].append(close - 50)
        data["High"].append(close + 500)
        data["Low"].append(close - 500)
        data["Close"].append(close)
        data["Volume"].append(1000000)

    return pd.DataFrame(data, index=dates)


# ──────────────────────────────────────────────
# 유틸 테스트
# ──────────────────────────────────────────────

class TestToDecimal:
    def test_none(self):
        assert _to_decimal(None) is None

    def test_nan_string(self):
        assert _to_decimal("nan") is None

    def test_normal_int(self):
        assert _to_decimal(15) == Decimal("15")

    def test_normal_float(self):
        assert _to_decimal(3.14) == Decimal("3.14")

    def test_invalid(self):
        assert _to_decimal("not_a_number") is None


class TestQuantize:
    def test_none(self):
        assert _quantize(None) is None

    def test_quantize_value(self):
        assert _quantize(Decimal("3.14159")) == Decimal("3.14")


class TestLastNonzero:
    def test_empty(self):
        assert _last_nonzero([]) is None

    def test_zero_last(self):
        assert _last_nonzero([Decimal("100"), Decimal("0")]) is None

    def test_nonzero_last(self):
        assert _last_nonzero([Decimal("0"), Decimal("200")]) == Decimal("200")


class TestToYfinanceTicker:
    def test_krx_6digit_returns_both_candidates(self):
        assert _to_yfinance_ticker("005930", "KRX") == ["005930.KS", "005930.KQ"]

    def test_already_has_suffix(self):
        assert _to_yfinance_ticker("005930.KS", "KRX") == ["005930.KS"]

    def test_us_ticker(self):
        assert _to_yfinance_ticker("AAPL", "NASDAQ") == ["AAPL"]


# ──────────────────────────────────────────────
# _sma 테스트
# ──────────────────────────────────────────────

class TestSMA:
    def test_returns_empty_for_short_data(self):
        result = _sma([Decimal("100")], period=5)
        assert result == []

    def test_correct_length(self):
        prices = [Decimal(str(i * 100)) for i in range(1, 11)]
        result = _sma(prices, period=5)
        assert len(result) == len(prices)

    def test_zeros_before_period(self):
        prices = [Decimal(str(i * 100)) for i in range(1, 11)]
        result = _sma(prices, period=5)
        for i in range(4):
            assert result[i] == Decimal(0)

    def test_first_sma_value(self):
        prices = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400"), Decimal("500")]
        result = _sma(prices, period=5)
        # SMA of [100, 200, 300, 400, 500] = 300
        assert result[4] == Decimal("300")

    def test_rolling_window(self):
        prices = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400"), Decimal("500"), Decimal("600")]
        result = _sma(prices, period=3)
        # index 2: (100+200+300)/3 = 200
        assert result[2] == Decimal("200")
        # index 3: (200+300+400)/3 = 300
        assert result[3] == Decimal("300")
        # index 5: (400+500+600)/3 = 500
        assert result[5] == Decimal("500")


# ──────────────────────────────────────────────
# 기본적 분석 테스트
# ──────────────────────────────────────────────

class TestFundamentalAnalysis:
    @pytest.mark.asyncio
    async def test_basic_response(self):
        mock_info = _make_mock_info()

        with patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info):
            result = await get_fundamental_analysis("005930", "KRX")

        assert result.ticker == "005930"
        assert result.market == "KRX"
        assert result.company_name == "Test Corp"
        assert result.sector == "Technology"
        assert result.per == Decimal("15.5")
        assert result.pbr == Decimal("2.3")
        assert result.roe == Decimal("18.00")
        assert result.eps == Decimal("5000")
        assert result.data_source == "yfinance"

    @pytest.mark.asyncio
    async def test_per_based_fair_value_calculation(self):
        """EPS * 기대PER(15) = 적정가"""
        mock_info = _make_mock_info({
            "trailingEps": 5000,
            "currentPrice": 50000,
        })

        with patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info):
            result = await get_fundamental_analysis("TEST", "NASDAQ")

        # EPS(5000) * PER(15) = 75000, currentPrice=50000
        assert result.per_based_fair_value == Decimal("75000.00")
        # gap = (50000 - 75000) / 75000 * 100 = -33.33%
        assert result.price_gap_pct is not None
        assert result.price_gap_pct < Decimal(-20)
        assert result.valuation_signal == "undervalued"

    @pytest.mark.asyncio
    async def test_overvalued_signal(self):
        mock_info = _make_mock_info({
            "trailingEps": 1000,
            "currentPrice": 50000,
        })

        with patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info):
            result = await get_fundamental_analysis("TEST", "NASDAQ")

        # EPS(1000) * PER(15) = 15000, currentPrice=50000
        # gap = (50000 - 15000) / 15000 * 100 = 233.33%
        assert result.valuation_signal == "overvalued"

    @pytest.mark.asyncio
    async def test_fair_signal(self):
        mock_info = _make_mock_info({
            "trailingEps": 5000,
            "currentPrice": 77000,
        })

        with patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info):
            result = await get_fundamental_analysis("TEST", "NASDAQ")

        # EPS(5000) * 15 = 75000, currentPrice=77000
        # gap = (77000-75000)/75000 * 100 = 2.67%
        assert result.valuation_signal == "fair"

    @pytest.mark.asyncio
    async def test_missing_eps(self):
        mock_info = _make_mock_info({"trailingEps": None})

        with patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info):
            result = await get_fundamental_analysis("TEST", "NASDAQ")

        assert result.per_based_fair_value is None
        assert result.valuation_signal is None

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        mock_info = _make_mock_info()

        with patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info) as mock_fetch:
            await get_fundamental_analysis("CACHE", "NASDAQ")
            await get_fundamental_analysis("CACHE", "NASDAQ")

        # 2번째 호출은 캐시 → fetch 1회만
        mock_fetch.assert_called_once()


# ──────────────────────────────────────────────
# 기술적 분석 테스트
# ──────────────────────────────────────────────

class TestTechnicalAnalysis:
    @pytest.mark.asyncio
    async def test_basic_response(self):
        mock_df = _make_mock_history_df(length=120)

        with patch("app.services.stock_analysis_service._fetch_history_sync", return_value=self._df_to_rows(mock_df)):
            result = await get_technical_analysis("005930", "KRX")

        assert result.ticker == "005930"
        assert result.rsi is not None
        assert result.macd is not None
        assert result.macd_signal is not None
        assert result.macd_histogram is not None
        assert result.bollinger_upper is not None
        assert result.bollinger_middle is not None
        assert result.bollinger_lower is not None
        assert result.sma_5 is not None
        assert result.sma_20 is not None
        assert result.sma_60 is not None
        assert result.sma_120 is not None
        assert result.support_level is not None
        assert result.resistance_level is not None
        assert result.current_price is not None
        assert result.data_source == "yfinance"

    @pytest.mark.asyncio
    async def test_insufficient_data(self):
        """데이터 25개 미만이면 빈 응답."""
        short_rows = self._df_to_rows(_make_mock_history_df(length=20))

        with patch("app.services.stock_analysis_service._fetch_history_sync", return_value=short_rows):
            result = await get_technical_analysis("TEST", "NASDAQ")

        assert result.rsi is None
        assert result.macd is None

    @pytest.mark.asyncio
    async def test_rsi_range(self):
        mock_df = _make_mock_history_df(length=120)

        with patch("app.services.stock_analysis_service._fetch_history_sync", return_value=self._df_to_rows(mock_df)):
            result = await get_technical_analysis("RSI_TEST", "NASDAQ")

        assert result.rsi is not None
        assert Decimal(0) <= result.rsi <= Decimal(100)

    @pytest.mark.asyncio
    async def test_bollinger_band_order(self):
        """볼린저밴드: lower < middle < upper."""
        mock_df = _make_mock_history_df(length=120)

        with patch("app.services.stock_analysis_service._fetch_history_sync", return_value=self._df_to_rows(mock_df)):
            result = await get_technical_analysis("BB_TEST", "NASDAQ")

        assert result.bollinger_lower is not None
        assert result.bollinger_middle is not None
        assert result.bollinger_upper is not None
        assert result.bollinger_lower < result.bollinger_middle < result.bollinger_upper

    @pytest.mark.asyncio
    async def test_support_less_than_resistance(self):
        mock_df = _make_mock_history_df(length=120)

        with patch("app.services.stock_analysis_service._fetch_history_sync", return_value=self._df_to_rows(mock_df)):
            result = await get_technical_analysis("SR_TEST", "NASDAQ")

        assert result.support_level is not None
        assert result.resistance_level is not None
        assert result.support_level < result.resistance_level

    @pytest.mark.asyncio
    async def test_sma_ordering_in_uptrend(self):
        """상승 추세에서 SMA: sma_5 > sma_20 > sma_60 > sma_120."""
        mock_df = _make_mock_history_df(length=200, trend=200)

        with patch("app.services.stock_analysis_service._fetch_history_sync", return_value=self._df_to_rows(mock_df)):
            result = await get_technical_analysis("SMA_TEST", "NASDAQ")

        assert result.sma_5 is not None
        assert result.sma_20 is not None
        assert result.sma_60 is not None
        assert result.sma_120 is not None
        assert result.sma_5 > result.sma_20 > result.sma_60 > result.sma_120

    @staticmethod
    def _df_to_rows(df: pd.DataFrame) -> list[dict]:
        """DataFrame → list[dict] (서비스 내부 포맷)."""
        rows = []
        for idx, row in df.iterrows():
            rows.append({
                "date": idx.to_pydatetime(),
                "close": Decimal(str(row["Close"])),
                "high": Decimal(str(row["High"])),
                "low": Decimal(str(row["Low"])),
                "volume": int(row["Volume"]),
            })
        return rows


# ──────────────────────────────────────────────
# 종합 매매 시그널 테스트
# ──────────────────────────────────────────────

class TestTradingSignals:
    @pytest.mark.asyncio
    async def test_basic_response_fields(self):
        mock_info = _make_mock_info()
        mock_df = _make_mock_history_df(length=120)

        with (
            patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info),
            patch("app.services.stock_analysis_service._fetch_history_sync", return_value=TestTechnicalAnalysis._df_to_rows(mock_df)),
        ):
            result = await get_trading_signals("005930", "KRX")

        assert result.ticker == "005930"
        assert result.action in ("buy", "sell", "hold")
        assert Decimal(0) <= result.confidence <= Decimal(100)
        assert result.risk_level in ("상", "중", "하")
        assert len(result.reasons) > 0
        assert result.fundamental_score is not None
        assert result.technical_score is not None
        assert result.disclaimer

    @pytest.mark.asyncio
    async def test_undervalued_oversold_gives_buy(self):
        """저평가 + RSI 과매도 → 매수 시그널 기대."""
        mock_info = _make_mock_info({
            "trailingEps": 10000,
            "currentPrice": 50000,
            "returnOnEquity": 0.25,
        })
        # 하락 추세로 RSI를 낮게
        mock_df = _make_mock_history_df(length=120, start_price=100000, trend=-500)

        with (
            patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info),
            patch("app.services.stock_analysis_service._fetch_history_sync", return_value=TestTechnicalAnalysis._df_to_rows(mock_df)),
        ):
            result = await get_trading_signals("BUY_TEST", "NASDAQ")

        assert result.action == "buy"

    @pytest.mark.asyncio
    async def test_overvalued_overbought_gives_sell(self):
        """고평가 + RSI 과매수 → 매도 시그널 기대."""
        mock_info = _make_mock_info({
            "trailingEps": 500,
            "currentPrice": 50000,
            "returnOnEquity": 0.02,
        })
        # 강한 상승 추세로 RSI를 높게
        mock_df = _make_mock_history_df(length=120, start_price=10000, trend=1000)

        with (
            patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info),
            patch("app.services.stock_analysis_service._fetch_history_sync", return_value=TestTechnicalAnalysis._df_to_rows(mock_df)),
        ):
            result = await get_trading_signals("SELL_TEST", "NASDAQ")

        assert result.action == "sell"

    @pytest.mark.asyncio
    async def test_scores_bounded_0_100(self):
        mock_info = _make_mock_info()
        mock_df = _make_mock_history_df(length=120)

        with (
            patch("app.services.stock_analysis_service._fetch_info_sync", return_value=mock_info),
            patch("app.services.stock_analysis_service._fetch_history_sync", return_value=TestTechnicalAnalysis._df_to_rows(mock_df)),
        ):
            result = await get_trading_signals("BOUND_TEST", "NASDAQ")

        assert Decimal(0) <= result.fundamental_score <= Decimal(100)
        assert Decimal(0) <= result.technical_score <= Decimal(100)
        assert Decimal(0) <= result.confidence <= Decimal(100)


# ──────────────────────────────────────────────
# 타임아웃 및 에러 핸들링 테스트
# ──────────────────────────────────────────────

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_fundamental_timeout_raises_stock_analysis_error(self):
        import time

        def _slow(*args, **kwargs):
            time.sleep(30)

        with patch("app.services.stock_analysis_service._fetch_info_sync", side_effect=_slow):
            with patch("app.services.stock_analysis_service._FETCH_TIMEOUT", 0.01):
                with pytest.raises(StockAnalysisError, match="시간 초과"):
                    await get_fundamental_analysis("TIMEOUT", "NASDAQ")

    @pytest.mark.asyncio
    async def test_technical_timeout_raises_stock_analysis_error(self):
        import time

        def _slow(*args, **kwargs):
            time.sleep(30)

        with patch("app.services.stock_analysis_service._fetch_history_sync", side_effect=_slow):
            with patch("app.services.stock_analysis_service._FETCH_TIMEOUT", 0.01):
                with pytest.raises(StockAnalysisError, match="시간 초과"):
                    await get_technical_analysis("TIMEOUT", "NASDAQ")

    @pytest.mark.asyncio
    async def test_fundamental_network_error_raises_stock_analysis_error(self):
        with patch("app.services.stock_analysis_service._fetch_info_sync", side_effect=ConnectionError("network")):
            with pytest.raises(StockAnalysisError, match="조회 실패"):
                await get_fundamental_analysis("ERR", "NASDAQ")

    @pytest.mark.asyncio
    async def test_technical_network_error_raises_stock_analysis_error(self):
        with patch("app.services.stock_analysis_service._fetch_history_sync", side_effect=ConnectionError("network")):
            with pytest.raises(StockAnalysisError, match="조회 실패"):
                await get_technical_analysis("ERR", "NASDAQ")
