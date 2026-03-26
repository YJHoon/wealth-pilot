"""투자 분석 스키마 — Pydantic v2

기본적 분석, 기술적 분석, 매매 시그널, 관심종목, 시뮬레이션 스키마 정의.
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.analysis import SimulationType
from app.services.crypto_service import decrypt_decimal_optional

if TYPE_CHECKING:
    from app.models.analysis import Watchlist as WatchlistModel


# ──────────────────────────────────────────────
# 면책 고지 상수
# ──────────────────────────────────────────────

INVESTMENT_DISCLAIMER_KO = (
    "본 서비스는 투자 자문이 아니며, 투자 판단의 책임은 사용자에게 있습니다. "
    "과거 데이터 기반 분석이며 미래 수익을 보장하지 않습니다."
)


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class ValuationSignal(str, enum.Enum):
    """적정가 대비 평가 시그널 (신호등)"""
    UNDERVALUED = "undervalued"    # 🟢 저평가
    FAIR = "fair"                  # 🟡 적정
    OVERVALUED = "overvalued"      # 🔴 고평가


class TradingSignalAction(str, enum.Enum):
    """매매 시그널 액션"""
    BUY = "buy"        # 매수
    SELL = "sell"      # 매도
    HOLD = "hold"      # 관망


class MarketType(str, enum.Enum):
    """시장 구분"""
    KRX = "KRX"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    CRYPTO = "CRYPTO"


# ──────────────────────────────────────────────
# 기본적 분석 (Fundamental)
# ──────────────────────────────────────────────

class FundamentalAnalysisResponse(BaseModel):
    ticker: str
    market: str
    company_name: str | None = None
    sector: str | None = None

    # 핵심 지표
    per: Decimal | None = None
    pbr: Decimal | None = None
    roe: Decimal | None = None
    eps: Decimal | None = None

    # 동종 업계 평균
    sector_avg_per: Decimal | None = None
    sector_avg_pbr: Decimal | None = None

    # 적정가 추정
    dcf_fair_value: Decimal | None = None
    current_price: Decimal | None = None
    price_gap_pct: Decimal | None = None  # 현재가 대비 적정가 괴리율

    # 평가 시그널
    valuation_signal: ValuationSignal | None = None

    # 메타
    data_source: str | None = None
    updated_at: datetime | None = None
    disclaimer: str = INVESTMENT_DISCLAIMER_KO


# ──────────────────────────────────────────────
# 기술적 분석 (Technical)
# ──────────────────────────────────────────────

class TechnicalAnalysisResponse(BaseModel):
    ticker: str
    market: str

    # RSI
    rsi: Decimal | None = None

    # MACD
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None

    # 볼린저밴드
    bollinger_upper: Decimal | None = None
    bollinger_middle: Decimal | None = None
    bollinger_lower: Decimal | None = None

    # 이동평균선
    sma_5: Decimal | None = None
    sma_20: Decimal | None = None
    sma_60: Decimal | None = None
    sma_120: Decimal | None = None

    # 지지/저항선
    support_level: Decimal | None = None
    resistance_level: Decimal | None = None

    current_price: Decimal | None = None

    # 메타
    data_source: str | None = None
    updated_at: datetime | None = None
    disclaimer: str = INVESTMENT_DISCLAIMER_KO


# ──────────────────────────────────────────────
# 매매 시그널
# ──────────────────────────────────────────────

class TradingSignalsResponse(BaseModel):
    ticker: str
    market: str

    action: TradingSignalAction
    confidence: Decimal = Field(ge=0, le=100)  # 신뢰도 (%)
    risk_level: str  # 상/중/하

    # 근거 요약
    reasons: list[str] = Field(default_factory=list)

    # 기본적+기술적 요약 점수
    fundamental_score: Decimal | None = None
    technical_score: Decimal | None = None

    current_price: Decimal | None = None

    # 메타
    data_source: str | None = None
    updated_at: datetime | None = None
    disclaimer: str = INVESTMENT_DISCLAIMER_KO


# ──────────────────────────────────────────────
# Watchlist (관심종목)
# ──────────────────────────────────────────────

class WatchlistCreate(BaseModel):
    ticker: str = Field(max_length=20)
    market: MarketType
    target_buy_price: Decimal | None = Field(default=None, gt=0)
    target_sell_price: Decimal | None = Field(default=None, gt=0)
    alert_threshold_pct: Decimal | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


class WatchlistUpdate(BaseModel):
    target_buy_price: Decimal | None = None
    target_sell_price: Decimal | None = None
    alert_threshold_pct: Decimal | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


class WatchlistResponse(BaseModel):
    id: UUID
    ticker: str
    market: str
    target_buy_price: Decimal | None = None
    target_sell_price: Decimal | None = None
    alert_threshold_pct: Decimal | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


def watchlist_to_response(watchlist: WatchlistModel) -> WatchlistResponse:
    """DB 모델 → Response 스키마 변환 (암호화 필드 복호화)."""
    return WatchlistResponse(
        id=watchlist.id,
        ticker=watchlist.ticker,
        market=watchlist.market,
        target_buy_price=decrypt_decimal_optional(watchlist.target_buy_price),
        target_sell_price=decrypt_decimal_optional(watchlist.target_sell_price),
        alert_threshold_pct=watchlist.alert_threshold_pct,
        notes=watchlist.notes,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


# ──────────────────────────────────────────────
# Simulation (시뮬레이션)
# ──────────────────────────────────────────────

class SimulationRequest(BaseModel):
    type: SimulationType
    params: dict = Field(default_factory=dict)


class SimulationResponse(BaseModel):
    id: UUID
    type: SimulationType
    params: dict
    result: dict
    created_at: datetime
    expires_at: datetime
