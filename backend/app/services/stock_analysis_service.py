"""종목 분석 서비스 — 기본적 분석 + 기술적 분석 + 종합 매매 시그널

yfinance 기반 비동기 래핑, 15분 TTL 인메모리 캐시.
모든 금융 연산은 Decimal로 수행 (float 금지).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

import yfinance as yf

from app.schemas.analysis import (
    FundamentalAnalysisResponse,
    TechnicalAnalysisResponse,
    TradingSignalAction,
    TradingSignalsResponse,
    ValuationSignal,
)
from app.services.trading_strategy import _ema, _rsi, _sma

logger = logging.getLogger(__name__)

# 캐시 TTL (초)
_CACHE_TTL = 900  # 15분


# ──────────────────────────────────────────────
# 인메모리 캐시
# ──────────────────────────────────────────────

@dataclass
class _CacheEntry:
    data: Any
    fetched_at: datetime


_cache: dict[str, _CacheEntry] = {}


def _get_cached(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    elapsed = (datetime.now(timezone.utc) - entry.fetched_at).total_seconds()
    if elapsed >= _CACHE_TTL:
        del _cache[key]
        return None
    return entry.data


def _set_cached(key: str, data: Any) -> None:
    _cache[key] = _CacheEntry(data=data, fetched_at=datetime.now(timezone.utc))


# ──────────────────────────────────────────────
# yfinance ticker 변환
# ──────────────────────────────────────────────

def _to_yfinance_ticker(ticker: str, market: str) -> str:
    """ticker + market → yfinance 심볼."""
    if "." in ticker:
        return ticker
    if market == "KRX":
        # 6자리 숫자 → .KS (KOSPI 우선)
        if ticker.isdigit() and len(ticker) == 6:
            return f"{ticker}.KS"
    return ticker


# ──────────────────────────────────────────────
# yfinance 데이터 fetch (동기 → asyncio.to_thread)
# ──────────────────────────────────────────────

def _fetch_info_sync(yf_ticker: str) -> dict:
    """yfinance Ticker.info 동기 호출."""
    tk = yf.Ticker(yf_ticker)
    return tk.info or {}


def _fetch_history_sync(yf_ticker: str, period: str = "1y") -> list[dict]:
    """yfinance Ticker.history → list[dict] 동기 호출.

    Returns:
        [{"date": datetime, "close": Decimal, "high": Decimal, "low": Decimal, "volume": int}, ...]
        오래된 순 정렬.
    """
    tk = yf.Ticker(yf_ticker)
    df = tk.history(period=period)

    if df.empty:
        return []

    rows: list[dict] = []
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
# 기본적 분석
# ──────────────────────────────────────────────

async def get_fundamental_analysis(
    ticker: str, market: str,
) -> FundamentalAnalysisResponse:
    """기본적 분석: PER, PBR, ROE, EPS, 섹터 평균, DCF 적정가, 평가 시그널."""
    cache_key = f"fundamental:{ticker}:{market}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    yf_ticker = _to_yfinance_ticker(ticker, market)
    info = await asyncio.to_thread(_fetch_info_sync, yf_ticker)

    # 핵심 지표 추출
    per = _to_decimal(info.get("trailingPE"))
    pbr = _to_decimal(info.get("priceToBook"))
    roe = _to_decimal(info.get("returnOnEquity"))
    if roe is not None:
        roe = (roe * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    eps = _to_decimal(info.get("trailingEps"))

    current_price = _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice"))

    # 섹터 평균 (yfinance에서 직접 제공하는 경우)
    sector_avg_per = _to_decimal(info.get("sectorPE"))
    sector_avg_pbr = _to_decimal(info.get("sectorPB"))

    # DCF 적정가 간이 추정: EPS * 기대 PER(15)
    dcf_fair_value: Decimal | None = None
    price_gap_pct: Decimal | None = None
    valuation_signal: ValuationSignal | None = None

    if eps is not None and eps > 0:
        expected_per = sector_avg_per if sector_avg_per and sector_avg_per > 0 else Decimal(15)
        dcf_fair_value = (eps * expected_per).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if current_price and current_price > 0 and dcf_fair_value > 0:
            price_gap_pct = (
                (current_price - dcf_fair_value) / dcf_fair_value * Decimal(100)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if price_gap_pct < Decimal(-20):
                valuation_signal = ValuationSignal.UNDERVALUED
            elif price_gap_pct > Decimal(20):
                valuation_signal = ValuationSignal.OVERVALUED
            else:
                valuation_signal = ValuationSignal.FAIR

    result = FundamentalAnalysisResponse(
        ticker=ticker,
        market=market,
        company_name=info.get("shortName") or info.get("longName"),
        sector=info.get("sector"),
        per=per,
        pbr=pbr,
        roe=roe,
        eps=eps,
        sector_avg_per=sector_avg_per,
        sector_avg_pbr=sector_avg_pbr,
        dcf_fair_value=dcf_fair_value,
        current_price=current_price,
        price_gap_pct=price_gap_pct,
        valuation_signal=valuation_signal,
        data_source="yfinance",
        updated_at=datetime.now(timezone.utc),
    )

    _set_cached(cache_key, result)
    return result


# ──────────────────────────────────────────────
# 기술적 분석
# ──────────────────────────────────────────────

async def get_technical_analysis(
    ticker: str, market: str,
) -> TechnicalAnalysisResponse:
    """기술적 분석: RSI, MACD, 볼린저밴드, SMA, 지지/저항선."""
    cache_key = f"technical:{ticker}:{market}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    yf_ticker = _to_yfinance_ticker(ticker, market)
    history = await asyncio.to_thread(_fetch_history_sync, yf_ticker)

    if len(history) < 26:
        # 최소 데이터 부족 시 빈 응답
        return TechnicalAnalysisResponse(
            ticker=ticker,
            market=market,
            data_source="yfinance",
            updated_at=datetime.now(timezone.utc),
        )

    closes = [row["close"] for row in history]
    highs = [row["high"] for row in history]
    lows = [row["low"] for row in history]
    current_price = closes[-1]

    # RSI (14일)
    rsi_value = _rsi(closes, 14)

    # MACD (12, 26, 9)
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema_12, ema_26)]
    macd_signal_line = _ema(macd_line[25:], 9)  # 26번째부터 유효

    macd_val = macd_line[-1] if macd_line else None
    macd_signal_val = macd_signal_line[-1] if macd_signal_line else None
    macd_histogram = None
    if macd_val is not None and macd_signal_val is not None:
        macd_histogram = macd_val - macd_signal_val

    # 볼린저밴드 (20일, 2σ)
    sma_20_list = _sma(closes, 20)
    bb_middle = sma_20_list[-1] if sma_20_list else None
    bb_upper: Decimal | None = None
    bb_lower: Decimal | None = None
    if bb_middle and len(closes) >= 20:
        window = closes[-20:]
        mean = sum(window) / Decimal(20)
        variance = sum((p - mean) ** 2 for p in window) / Decimal(20)
        std_dev = variance.sqrt()
        bb_upper = (bb_middle + Decimal(2) * std_dev).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        bb_lower = (bb_middle - Decimal(2) * std_dev).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        bb_middle = bb_middle.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # SMA (5, 20, 60, 120)
    sma_5_list = _sma(closes, 5)
    sma_60_list = _sma(closes, 60)
    sma_120_list = _sma(closes, 120)

    sma_5 = _last_nonzero(sma_5_list)
    sma_20 = _last_nonzero(sma_20_list)
    sma_60 = _last_nonzero(sma_60_list)
    sma_120 = _last_nonzero(sma_120_list)

    # 지지/저항선 (최근 60일 저가/고가)
    recent_lows = lows[-60:] if len(lows) >= 60 else lows
    recent_highs = highs[-60:] if len(highs) >= 60 else highs
    support_level = min(recent_lows)
    resistance_level = max(recent_highs)

    result = TechnicalAnalysisResponse(
        ticker=ticker,
        market=market,
        rsi=rsi_value,
        macd=_quantize(macd_val),
        macd_signal=_quantize(macd_signal_val),
        macd_histogram=_quantize(macd_histogram),
        bollinger_upper=bb_upper,
        bollinger_middle=bb_middle,
        bollinger_lower=bb_lower,
        sma_5=_quantize(sma_5),
        sma_20=_quantize(sma_20),
        sma_60=_quantize(sma_60),
        sma_120=_quantize(sma_120),
        support_level=_quantize(support_level),
        resistance_level=_quantize(resistance_level),
        current_price=_quantize(current_price),
        data_source="yfinance",
        updated_at=datetime.now(timezone.utc),
    )

    _set_cached(cache_key, result)
    return result


# ──────────────────────────────────────────────
# 종합 매매 시그널
# ──────────────────────────────────────────────

async def get_trading_signals(
    ticker: str, market: str,
) -> TradingSignalsResponse:
    """기본적 + 기술적 분석 종합 → 매수/매도/관망, 신뢰도, 리스크 레벨."""
    cache_key = f"signals:{ticker}:{market}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    fundamental, technical = await asyncio.gather(
        get_fundamental_analysis(ticker, market),
        get_technical_analysis(ticker, market),
    )

    reasons: list[str] = []
    fundamental_score = Decimal(50)  # 중립 기본값
    technical_score = Decimal(50)

    # --- 기본적 분석 점수 ---
    if fundamental.valuation_signal == ValuationSignal.UNDERVALUED:
        fundamental_score = Decimal(75)
        reasons.append(f"저평가 (괴리율 {fundamental.price_gap_pct}%)")
    elif fundamental.valuation_signal == ValuationSignal.OVERVALUED:
        fundamental_score = Decimal(25)
        reasons.append(f"고평가 (괴리율 {fundamental.price_gap_pct}%)")
    elif fundamental.valuation_signal == ValuationSignal.FAIR:
        fundamental_score = Decimal(50)
        reasons.append("적정 가치 범위")

    if fundamental.roe is not None:
        if fundamental.roe > Decimal(15):
            fundamental_score += Decimal(10)
            reasons.append(f"높은 ROE ({fundamental.roe}%)")
        elif fundamental.roe < Decimal(5):
            fundamental_score -= Decimal(10)
            reasons.append(f"낮은 ROE ({fundamental.roe}%)")

    # --- 기술적 분석 점수 ---
    if technical.rsi is not None:
        if technical.rsi < Decimal(30):
            technical_score = Decimal(75)
            reasons.append(f"RSI 과매도 ({technical.rsi})")
        elif technical.rsi > Decimal(70):
            technical_score = Decimal(25)
            reasons.append(f"RSI 과매수 ({technical.rsi})")
        else:
            reasons.append(f"RSI 중립 ({technical.rsi})")

    if technical.macd_histogram is not None:
        if technical.macd_histogram > 0:
            technical_score += Decimal(10)
            reasons.append("MACD 양전환")
        else:
            technical_score -= Decimal(10)
            reasons.append("MACD 음전환")

    # 볼린저밴드 위치
    if (
        technical.current_price is not None
        and technical.bollinger_lower is not None
        and technical.bollinger_upper is not None
    ):
        if technical.current_price <= technical.bollinger_lower:
            technical_score += Decimal(10)
            reasons.append("볼린저밴드 하단 접근")
        elif technical.current_price >= technical.bollinger_upper:
            technical_score -= Decimal(10)
            reasons.append("볼린저밴드 상단 접근")

    # --- 종합 ---
    # 기본적 40% + 기술적 60%
    combined = fundamental_score * Decimal("0.4") + technical_score * Decimal("0.6")
    combined = combined.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 점수 범위 clamp (0~100)
    fundamental_score = max(Decimal(0), min(Decimal(100), fundamental_score))
    technical_score = max(Decimal(0), min(Decimal(100), technical_score))
    combined = max(Decimal(0), min(Decimal(100), combined))

    if combined >= Decimal(60):
        action = TradingSignalAction.BUY
    elif combined <= Decimal(40):
        action = TradingSignalAction.SELL
    else:
        action = TradingSignalAction.HOLD

    # 리스크 레벨
    if technical.rsi is not None and (technical.rsi > Decimal(80) or technical.rsi < Decimal(20)):
        risk_level: Literal["상", "중", "하"] = "상"
    elif combined >= Decimal(45) and combined <= Decimal(55):
        risk_level = "하"
    else:
        risk_level = "중"

    result = TradingSignalsResponse(
        ticker=ticker,
        market=market,
        action=action,
        confidence=combined,
        risk_level=risk_level,
        reasons=reasons,
        fundamental_score=fundamental_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        technical_score=technical_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        current_price=technical.current_price,
        data_source="yfinance",
        updated_at=datetime.now(timezone.utc),
    )

    _set_cached(cache_key, result)
    return result


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────

def _to_decimal(value: Any) -> Decimal | None:
    """숫자형 → Decimal 변환. None/NaN 처리."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        if d != d:  # NaN check
            return None
        return d
    except Exception:
        return None


def _quantize(value: Decimal | None) -> Decimal | None:
    """소수점 2자리로 반올림."""
    if value is None:
        return None
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _last_nonzero(values: list[Decimal]) -> Decimal | None:
    """리스트의 마지막 0이 아닌 값 반환."""
    if not values:
        return None
    val = values[-1]
    return val if val != Decimal(0) else None
