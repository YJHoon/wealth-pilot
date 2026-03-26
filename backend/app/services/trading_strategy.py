"""매매 전략 엔진

이동평균 교차 + RSI 필터 기반 매매 신호 생성.
모든 금융 연산은 Decimal로 수행 (float 금지).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """매매 신호."""
    action: str  # "buy", "sell", "hold"
    confidence: Decimal  # 0~1
    reason: str


class BaseStrategy(ABC):
    """전략 기반 클래스."""

    @abstractmethod
    def evaluate(self, ticker: str, price_history: list[dict]) -> Signal:
        """시세 데이터를 분석하여 매매 신호 반환.

        Args:
            ticker: 종목코드
            price_history: [{"date": str, "close": Decimal, "high": Decimal, "low": Decimal, "volume": int}, ...]
                           오래된 순서 (인덱스 0이 가장 오래된 데이터)
        """
        ...


def _sma(prices: list[Decimal], period: int) -> list[Decimal]:
    """단순이동평균(SMA) 계산.

    Args:
        prices: 종가 리스트 (오래된 순)
        period: SMA 기간

    Returns:
        SMA 리스트 (prices와 동일 길이, 초기 period-1개는 Decimal(0))
    """
    if len(prices) < period:
        return []

    result: list[Decimal] = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(Decimal(0))
        else:
            window = prices[i - period + 1 : i + 1]
            result.append(sum(window) / Decimal(period))
    return result


def _ema(prices: list[Decimal], period: int) -> list[Decimal]:
    """지수이동평균(EMA) 계산.

    Args:
        prices: 종가 리스트 (오래된 순)
        period: EMA 기간

    Returns:
        EMA 리스트 (prices와 동일 길이, 초기 period-1개는 SMA 기반)
    """
    if len(prices) < period:
        return []

    multiplier = Decimal(2) / (Decimal(period) + Decimal(1))
    one_minus_mult = Decimal(1) - multiplier

    # 초기값: 첫 period개의 SMA
    sma = sum(prices[:period]) / Decimal(period)
    result: list[Decimal] = []

    # period-1까지는 계산 불가 → None 대신 빈 리스트로 처리
    for i, price in enumerate(prices):
        if i < period - 1:
            result.append(Decimal(0))
        elif i == period - 1:
            result.append(sma)
        else:
            ema_val = price * multiplier + result[-1] * one_minus_mult
            result.append(ema_val)

    return result


def _rsi(prices: list[Decimal], period: int = 14) -> Decimal:
    """RSI(상대강도지수) 계산 — 최신 값 하나만 반환.

    Wilder's smoothing method 사용.
    """
    if len(prices) < period + 1:
        return Decimal(50)  # 데이터 부족 시 중립값

    # 가격 변화량
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    # 초기 평균 상승/하락폭 (첫 period개)
    gains = [c if c > 0 else Decimal(0) for c in changes[:period]]
    losses = [abs(c) if c < 0 else Decimal(0) for c in changes[:period]]

    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)

    # Wilder's smoothing
    for c in changes[period:]:
        if c > 0:
            avg_gain = (avg_gain * (Decimal(period) - 1) + c) / Decimal(period)
            avg_loss = (avg_loss * (Decimal(period) - 1)) / Decimal(period)
        else:
            avg_gain = (avg_gain * (Decimal(period) - 1)) / Decimal(period)
            avg_loss = (avg_loss * (Decimal(period) - 1) + abs(c)) / Decimal(period)

    if avg_loss == 0:
        return Decimal(100)

    rs = avg_gain / avg_loss
    rsi = Decimal(100) - (Decimal(100) / (Decimal(1) + rs))
    return rsi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class MACrossoverStrategy(BaseStrategy):
    """이중 이동평균 교차 + RSI 필터 전략.

    - Golden Cross (단기 EMA > 장기 EMA) → 매수
    - Death Cross (단기 EMA < 장기 EMA) → 매도
    - RSI 과매수/과매도 필터로 신호 보정
    """

    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        rsi_period: int = 14,
        rsi_overbought: int = 70,
        rsi_oversold: int = 30,
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.rsi_overbought = Decimal(rsi_overbought)
        self.rsi_oversold = Decimal(rsi_oversold)

    @classmethod
    def from_params(cls, params: dict) -> MACrossoverStrategy:
        """전략 파라미터 dict에서 생성."""
        return cls(
            fast_period=params.get("fast_period", 5),
            slow_period=params.get("slow_period", 20),
            rsi_period=params.get("rsi_period", 14),
            rsi_overbought=params.get("rsi_overbought", 70),
            rsi_oversold=params.get("rsi_oversold", 30),
        )

    def evaluate(self, ticker: str, price_history: list[dict]) -> Signal:
        """시세 데이터를 분석하여 매매 신호 반환."""
        closes = [item["close"] for item in price_history]

        min_required = max(self.slow_period + 2, self.rsi_period + 2)
        if len(closes) < min_required:
            return Signal(
                action="hold",
                confidence=Decimal(0),
                reason=f"데이터 부족 ({len(closes)}/{min_required}일)",
            )

        # EMA 계산
        fast_ema = _ema(closes, self.fast_period)
        slow_ema = _ema(closes, self.slow_period)

        # RSI 계산
        rsi_value = _rsi(closes, self.rsi_period)

        # 최신 2개 EMA 비교 (교차 감지)
        curr_fast = fast_ema[-1]
        prev_fast = fast_ema[-2]
        curr_slow = slow_ema[-1]
        prev_slow = slow_ema[-2]

        # Golden Cross: 단기가 장기를 상향 돌파
        golden_cross = prev_fast <= prev_slow and curr_fast > curr_slow
        # Death Cross: 단기가 장기를 하향 돌파
        death_cross = prev_fast >= prev_slow and curr_fast < curr_slow

        # 추세 강도 (EMA 간 거리 비율)
        if curr_slow > 0:
            trend_strength = abs(curr_fast - curr_slow) / curr_slow
        else:
            trend_strength = Decimal(0)

        # 매수 신호
        if golden_cross:
            if rsi_value > self.rsi_overbought:
                return Signal(
                    action="hold",
                    confidence=Decimal("0.3"),
                    reason=f"Golden Cross 감지, RSI 과매수({rsi_value}) — 매수 보류",
                )
            confidence = min(Decimal("0.9"), Decimal("0.6") + trend_strength * 10)
            return Signal(
                action="buy",
                confidence=confidence,
                reason=f"Golden Cross (fast={curr_fast:.0f} > slow={curr_slow:.0f}), RSI={rsi_value}",
            )

        # 매도 신호
        if death_cross:
            if rsi_value < self.rsi_oversold:
                return Signal(
                    action="hold",
                    confidence=Decimal("0.3"),
                    reason=f"Death Cross 감지, RSI 과매도({rsi_value}) — 매도 보류",
                )
            confidence = min(Decimal("0.9"), Decimal("0.6") + trend_strength * 10)
            return Signal(
                action="sell",
                confidence=confidence,
                reason=f"Death Cross (fast={curr_fast:.0f} < slow={curr_slow:.0f}), RSI={rsi_value}",
            )

        # 교차 없음 → hold
        if curr_fast > curr_slow:
            trend_desc = "상승 추세 유지"
        else:
            trend_desc = "하락 추세 유지"

        return Signal(
            action="hold",
            confidence=Decimal("0.5"),
            reason=f"{trend_desc} (fast={curr_fast:.0f}, slow={curr_slow:.0f}), RSI={rsi_value}",
        )


def create_strategy(strategy_type: str, params: dict) -> BaseStrategy:
    """전략 타입에 따라 전략 인스턴스 생성."""
    if strategy_type == "ma_crossover":
        return MACrossoverStrategy.from_params(params)
    raise ValueError(f"Unknown strategy type: {strategy_type}")
