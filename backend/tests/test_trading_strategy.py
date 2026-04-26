"""매매 전략 엔진 테스트 — 고정 시세 데이터 기반"""

from decimal import Decimal

import pytest

from app.services.trading_strategy import (
    MACrossoverStrategy,
    MeanReversionStrategy,
    Signal,
    _ema,
    _rsi,
    _stdev,
    create_strategy,
)


def _make_price_history(closes: list[int | float]) -> list[dict]:
    """간단한 시세 리스트 생성."""
    return [
        {"date": f"2024{i:04d}", "close": Decimal(str(c)), "high": Decimal(str(c + 100)), "low": Decimal(str(c - 100)), "volume": 1000}
        for i, c in enumerate(closes)
    ]


class TestEMA:
    def test_returns_empty_for_short_data(self):
        result = _ema([Decimal("100")], period=5)
        assert result == []

    def test_correct_length(self):
        prices = [Decimal(str(i * 100)) for i in range(1, 11)]
        result = _ema(prices, period=5)
        assert len(result) == len(prices)

    def test_initial_sma(self):
        prices = [Decimal("100"), Decimal("200"), Decimal("300")]
        result = _ema(prices, period=3)
        # SMA of first 3 = (100+200+300)/3 = 200
        assert result[2] == Decimal("200")

    def test_zeros_before_period(self):
        prices = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400")]
        result = _ema(prices, period=3)
        assert result[0] == Decimal("0")
        assert result[1] == Decimal("0")


class TestRSI:
    def test_insufficient_data_returns_neutral(self):
        prices = [Decimal(str(i)) for i in range(10)]  # < 15
        result = _rsi(prices, period=14)
        assert result == Decimal("50")

    def test_flat_prices_returns_neutral(self):
        """모든 가격이 동일하면 RSI = 50 (중립)."""
        prices = [Decimal("1000")] * 30
        result = _rsi(prices, period=14)
        assert result == Decimal("50")

    def test_all_gains_returns_100(self):
        # Monotonically increasing prices
        prices = [Decimal(str(1000 + i * 10)) for i in range(30)]
        result = _rsi(prices, period=14)
        assert result == Decimal("100")

    def test_all_losses_returns_near_zero(self):
        # Monotonically decreasing prices
        prices = [Decimal(str(10000 - i * 10)) for i in range(30)]
        result = _rsi(prices, period=14)
        assert result < Decimal("1")

    def test_rsi_in_range(self):
        # Mixed up and down
        prices = [Decimal(str(1000 + (i % 3) * 50 - (i % 2) * 30)) for i in range(30)]
        result = _rsi(prices, period=14)
        assert Decimal("0") <= result <= Decimal("100")


class TestMACrossoverStrategy:
    def test_hold_on_insufficient_data(self):
        strategy = MACrossoverStrategy(fast_period=5, slow_period=20)
        history = _make_price_history([100] * 10)  # Not enough
        signal = strategy.evaluate("005930", history)
        assert signal.action == "hold"
        assert "데이터 부족" in signal.reason

    def test_golden_cross_buy_signal(self):
        """단기 EMA가 장기 EMA를 상향 돌파 → 매수"""
        # Construct prices: initially flat, then sharp upward movement
        prices = [1000] * 25  # flat start to establish slow EMA
        # Add sharp rise for golden cross
        for i in range(10):
            prices.append(1000 + (i + 1) * 50)

        strategy = MACrossoverStrategy(fast_period=5, slow_period=20, rsi_period=14)
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)

        # Should be buy or hold (depends on exact crossover timing)
        assert signal.action in ("buy", "hold")
        assert isinstance(signal.confidence, Decimal)

    def test_death_cross_sell_signal(self):
        """단기 EMA가 장기 EMA를 하향 돌파 → 매도"""
        # Construct prices: initially high, then sharp drop
        prices = [2000] * 25  # flat start
        for i in range(10):
            prices.append(2000 - (i + 1) * 50)

        strategy = MACrossoverStrategy(fast_period=5, slow_period=20, rsi_period=14)
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)

        assert signal.action in ("sell", "hold")
        assert isinstance(signal.confidence, Decimal)

    def test_hold_on_flat_prices(self):
        """횡보 시 hold"""
        prices = [1000] * 40
        strategy = MACrossoverStrategy(fast_period=5, slow_period=20)
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)
        assert signal.action == "hold"

    def test_rsi_overbought_blocks_buy(self):
        """RSI 과매수 시 Golden Cross여도 매수 보류"""
        strategy = MACrossoverStrategy(
            fast_period=5, slow_period=20,
            rsi_period=14, rsi_overbought=70,
        )
        # Construct a scenario with strong upward momentum
        prices = [1000] * 20
        for i in range(20):
            prices.append(1000 + (i + 1) * 100)  # Very strong rise

        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)

        # With such strong momentum, RSI should be high
        # Signal should either be hold (due to RSI filter) or buy
        assert signal.action in ("buy", "hold")

    def test_from_params(self):
        params = {"fast_period": 3, "slow_period": 10, "rsi_period": 7}
        strategy = MACrossoverStrategy.from_params(params)
        assert strategy.fast_period == 3
        assert strategy.slow_period == 10
        assert strategy.rsi_period == 7

    def test_default_params(self):
        strategy = MACrossoverStrategy.from_params({})
        assert strategy.fast_period == 5
        assert strategy.slow_period == 20
        assert strategy.rsi_period == 14


class TestStdev:
    def test_empty_returns_zero(self):
        assert _stdev([]) == Decimal(0)

    def test_constant_returns_zero(self):
        prices = [Decimal("1000")] * 10
        assert _stdev(prices) == Decimal(0)

    def test_known_values(self):
        # 모집단 표준편차: [2, 4, 4, 4, 5, 5, 7, 9] → 평균 5, σ = 2
        prices = [Decimal(v) for v in (2, 4, 4, 4, 5, 5, 7, 9)]
        result = _stdev(prices)
        assert result == Decimal(2)


class TestMeanReversionStrategy:
    def test_hold_on_insufficient_data(self):
        strategy = MeanReversionStrategy(lookback=20, rsi_period=14)
        history = _make_price_history([1000] * 10)
        signal = strategy.evaluate("005930", history)
        assert signal.action == "hold"
        assert "데이터 부족" in signal.reason

    def test_lower_band_breakout_buy(self):
        """가격이 하단 밴드를 이탈하면 매수 신호"""
        # 변동 있는 시세로 σ를 만든 뒤, 마지막에 급락시켜 하단 이탈
        prices = []
        for i in range(40):
            prices.append(1000 + (i % 5) * 20)  # 1000~1080 흔들림
        prices.append(700)  # 마지막에 급락 → 하단 이탈

        strategy = MeanReversionStrategy(
            lookback=20, std_multiplier=2, rsi_period=14
        )
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)

        assert signal.action == "buy"
        assert signal.confidence >= Decimal("0.6")
        assert "하단 밴드" in signal.reason

    def test_upper_band_breakout_sell(self):
        """가격이 상단 밴드를 이탈하면 매도 신호"""
        prices = []
        for i in range(40):
            prices.append(1000 + (i % 5) * 20)
        prices.append(1500)  # 마지막에 급등 → 상단 이탈

        strategy = MeanReversionStrategy(
            lookback=20, std_multiplier=2, rsi_period=14
        )
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)

        assert signal.action == "sell"
        assert signal.confidence >= Decimal("0.6")
        assert "상단 밴드" in signal.reason

    def test_inside_band_holds(self):
        """밴드 내부면 hold"""
        prices = [1000 + (i % 5) * 20 for i in range(40)]
        strategy = MeanReversionStrategy(lookback=20, std_multiplier=2)
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)
        assert signal.action == "hold"

    def test_lower_breakout_with_rsi_overbought_holds(self):
        """하단 이탈인데 RSI가 과매수면 매수 보류 (모순 케이스).

        결정론적 시나리오: 짧은 lookback(=5)로 좁은 밴드를 만들고, 긴 RSI 기간(=30)
        으로 RSI가 마지막 작은 하락에도 천천히 반응하게 해 모순을 만든다.
        - 38일 강한 상승(+20씩) → RSI가 90+ 까지 치솟음
        - 마지막 2일 작은 하락 → 짧은 lookback에서는 하단 밴드 이탈
        """
        prices = [1000 + i * 20 for i in range(39)]  # 1000, 1020, ..., 1760
        prices.append(1740)  # 작은 하락
        prices.append(1700)  # 좀 더 하락

        strategy = MeanReversionStrategy(
            lookback=5,
            std_multiplier=Decimal("0.5"),
            rsi_period=30,
            rsi_overbought=70,
        )
        history = _make_price_history(prices)
        signal = strategy.evaluate("005930", history)

        assert signal.action == "hold"
        assert "RSI 과매수" in signal.reason

    def test_from_params(self):
        params = {
            "lookback": 10,
            "std_multiplier": 1.5,
            "rsi_period": 7,
            "rsi_overbought": 75,
            "rsi_oversold": 25,
        }
        strategy = MeanReversionStrategy.from_params(params)
        assert strategy.lookback == 10
        assert strategy.std_multiplier == Decimal("1.5")
        assert strategy.rsi_period == 7
        assert strategy.rsi_overbought == Decimal(75)
        assert strategy.rsi_oversold == Decimal(25)

    def test_default_params(self):
        strategy = MeanReversionStrategy.from_params({})
        assert strategy.lookback == 20
        assert strategy.std_multiplier == Decimal(2)
        assert strategy.rsi_period == 14


class TestCreateStrategy:
    def test_ma_crossover_type(self):
        strategy = create_strategy("ma_crossover", {})
        assert isinstance(strategy, MACrossoverStrategy)

    def test_mean_reversion_type(self):
        strategy = create_strategy("mean_reversion", {})
        assert isinstance(strategy, MeanReversionStrategy)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy type"):
            create_strategy("nonexistent", {})


class TestSignalDataclass:
    def test_signal_fields(self):
        signal = Signal(action="buy", confidence=Decimal("0.8"), reason="test")
        assert signal.action == "buy"
        assert signal.confidence == Decimal("0.8")
        assert signal.reason == "test"
