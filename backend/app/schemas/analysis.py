"""투자 분석 스키마 — Pydantic v2

기본적 분석, 기술적 분석, 매매 시그널, 관심종목, 시뮬레이션 스키마 정의.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, TYPE_CHECKING, Union
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.analysis import SimulationType
from app.services.crypto_service import decrypt_decimal_optional

logger = logging.getLogger(__name__)

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

    # PER 기반 적정가 추정 (EPS × 기대 PER)
    per_based_fair_value: Decimal | None = None
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

    # RSI (0~100)
    rsi: Decimal | None = Field(default=None, ge=0, le=100)

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
    risk_level: Literal["상", "중", "하"]

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
    target_buy_price: Decimal | None = Field(default=None, gt=0)
    target_sell_price: Decimal | None = Field(default=None, gt=0)
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


def _safe_decrypt(encrypted: str | None, *, watchlist_id: UUID, field: str) -> Decimal | None:
    """복호화 시도, 실패 시 None 반환 + 로그."""
    try:
        return decrypt_decimal_optional(encrypted)
    except Exception:
        logger.exception(
            "Failed to decrypt %s for watchlist %s", field, watchlist_id,
        )
        return None


def watchlist_to_response(watchlist: WatchlistModel) -> WatchlistResponse:
    """DB 모델 → Response 스키마 변환 (암호화 필드 복호화)."""
    return WatchlistResponse(
        id=watchlist.id,
        ticker=watchlist.ticker,
        market=watchlist.market,
        target_buy_price=_safe_decrypt(
            watchlist.target_buy_price,
            watchlist_id=watchlist.id, field="target_buy_price",
        ),
        target_sell_price=_safe_decrypt(
            watchlist.target_sell_price,
            watchlist_id=watchlist.id, field="target_sell_price",
        ),
        alert_threshold_pct=watchlist.alert_threshold_pct,
        notes=watchlist.notes,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


# ──────────────────────────────────────────────
# Simulation — 타입별 Params / Result
# ──────────────────────────────────────────────

# --- DCA (월적립 시뮬레이션) ---

class DcaSimulationParams(BaseModel):
    type: Literal["dca"] = "dca"
    ticker: str
    market: MarketType
    monthly_amount: Decimal = Field(gt=0)
    months: int = Field(gt=0, le=600)


class MonthlyBreakdownItem(BaseModel):
    month: int
    invested: Decimal
    cumulative_invested: Decimal
    shares_bought: Decimal
    cumulative_shares: Decimal
    price: Decimal
    portfolio_value: Decimal


class DcaSimulationResult(BaseModel):
    total_invested: Decimal
    final_value: Decimal
    return_rate: Decimal
    monthly_breakdown: list[MonthlyBreakdownItem] = Field(default_factory=list)


# --- Portfolio (포트폴리오 리밸런싱 시뮬레이션) ---

class PortfolioSimulationParams(BaseModel):
    type: Literal["portfolio"] = "portfolio"
    tickers: list[str] = Field(min_length=1)
    weights: list[Decimal] = Field(min_length=1)
    initial_amount: Decimal = Field(gt=0)
    months: int = Field(gt=0, le=600)
    rebalance_interval_months: int = Field(default=3, ge=1, le=12)

    @model_validator(mode="after")
    def _check_tickers_weights_length(self) -> PortfolioSimulationParams:
        if len(self.tickers) != len(self.weights):
            msg = f"tickers({len(self.tickers)})와 weights({len(self.weights)})의 길이가 일치해야 합니다"
            raise ValueError(msg)
        return self


class RebalanceEvent(BaseModel):
    month: int
    pre_rebalance_value: Decimal
    post_rebalance_value: Decimal
    allocations: dict[str, Decimal]  # ticker → 비중


class PortfolioSimulationResult(BaseModel):
    total_invested: Decimal
    final_value: Decimal
    return_rate: Decimal
    rebalance_events: list[RebalanceEvent] = Field(default_factory=list)


# --- Scenario (시나리오 분석) ---

class ScenarioSimulationParams(BaseModel):
    type: Literal["scenario"] = "scenario"
    ticker: str
    market: MarketType
    entry_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    target_price: Decimal = Field(gt=0)
    stop_loss_price: Decimal = Field(gt=0)


class ScenarioSimulationResult(BaseModel):
    potential_profit: Decimal
    potential_loss: Decimal
    risk_reward_ratio: Decimal
    profit_pct: Decimal
    loss_pct: Decimal


# --- Discriminated Union ---

SimulationParams = Annotated[
    Union[DcaSimulationParams, PortfolioSimulationParams, ScenarioSimulationParams],
    Field(discriminator="type"),
]

SimulationResult = Union[DcaSimulationResult, PortfolioSimulationResult, ScenarioSimulationResult]


class SimulationRequest(BaseModel):
    params: SimulationParams


class SimulationResponse(BaseModel):
    id: UUID
    type: SimulationType
    params: SimulationParams
    result: SimulationResult
    created_at: datetime
    expires_at: datetime
