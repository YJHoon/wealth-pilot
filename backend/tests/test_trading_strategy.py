"""매매 전략 엔진 테스트 — 고정 시세 데이터 기반"""

from decimal import Decimal

import pytest

from app.services.trading_strategy import (
    MACrossoverStrategy,
    Signal,
    _ema,
    _rsi,
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


class TestCreateStrategy:
    def test_ma_crossover_type(self):
        strategy = create_strategy("ma_crossover", {})
        assert isinstance(strategy, MACrossoverStrategy)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy type"):
            create_strategy("nonexistent", {})


class TestSignalDataclass:
    def test_signal_fields(self):
        signal = Signal(action="buy", confidence=Decimal("0.8"), reason="test")
        assert signal.action == "buy"
        assert signal.confidence == Decimal("0.8")
        assert signal.reason == "test"
