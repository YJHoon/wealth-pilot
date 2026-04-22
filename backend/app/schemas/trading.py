"""자동매매 스키마 — Pydantic v2"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.trading import (
    OrderSide,
    OrderStatus,
    OrderType,
    ScheduleLogStatus,
    StrategyType,
    TradingMode,
)
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
)

if TYPE_CHECKING:
    from app.models.trading import (
        AdaptiveRule as AdaptiveRuleModel,
        TradingAccount as TradingAccountModel,
        TradingDecision as TradingDecisionModel,
        TradingOrder as TradingOrderModel,
        TradingPosition as TradingPositionModel,
        TradingScheduleLog as TradingScheduleLogModel,
        TradingStrategy as TradingStrategyModel,
    )


# ──────────────────────────────────────────────
# TradingAccount
# ──────────────────────────────────────────────

class TradingAccountCreate(BaseModel):
    mode: TradingMode = TradingMode.PAPER


class TradingAccountResponse(BaseModel):
    id: UUID
    mode: TradingMode
    initial_capital: Decimal
    cash_balance: Decimal | None
    is_active: bool
    allow_netting: bool
    token_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TradingAccountUpdate(BaseModel):
    allow_netting: bool | None = None


class RebalanceAllocationItem(BaseModel):
    """리밸런싱: 전략별 신규 initial_capital."""
    strategy_id: UUID
    initial_capital: Decimal = Field(ge=Decimal("0"))


class AccountRebalanceRequest(BaseModel):
    """계좌 내 활성 전략들의 initial_capital 일괄 재배분."""
    allocations: list[RebalanceAllocationItem]


class DepositAllocationMode(str, Enum):
    """입금 할당 방식."""
    MANUAL = "manual"       # 사용자가 전략별 금액을 직접 지정
    PRO_RATA = "pro_rata"   # 기존 전략 initial_capital 비율대로 자동 분배
    RESERVE = "reserve"     # 계좌 총액만 증액, 전략에는 배분하지 않음


class DepositAllocationItem(BaseModel):
    """수동 입금 분배: 전략별 추가 금액."""
    strategy_id: UUID
    amount: Decimal = Field(ge=Decimal("0"))


class AccountDepositRequest(BaseModel):
    """계좌 신규 입금 반영 + 전략 할당."""
    amount: Decimal = Field(gt=Decimal("0"))
    mode: DepositAllocationMode
    # mode=manual일 때만 사용
    allocations: list[DepositAllocationItem] | None = None

    @model_validator(mode="after")
    def _check_mode_consistency(self) -> "AccountDepositRequest":
        if self.mode == DepositAllocationMode.MANUAL:
            # MANUAL은 반드시 비어있지 않은 allocations를 요구
            if self.allocations is None or len(self.allocations) == 0:
                raise ValueError(
                    "manual 모드에서는 allocations가 비어있을 수 없습니다.",
                )
        elif self.mode in (DepositAllocationMode.PRO_RATA, DepositAllocationMode.RESERVE):
            # PRO_RATA/RESERVE는 allocations 필드 자체를 지정해서는 안 됨
            # (빈 리스트 []도 부적절한 입력으로 취급)
            if self.allocations is not None:
                raise ValueError(
                    f"{self.mode.value} 모드에서는 allocations를 지정할 수 없습니다.",
                )
        return self


def account_to_response(account: TradingAccountModel) -> TradingAccountResponse:
    return TradingAccountResponse(
        id=account.id,
        mode=account.mode,
        initial_capital=decrypt_decimal(account.initial_capital),
        cash_balance=decrypt_decimal_optional(account.cash_balance),
        is_active=account.is_active,
        allow_netting=account.allow_netting,
        token_expires_at=account.token_expires_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


# ──────────────────────────────────────────────
# TradingStrategy
# ──────────────────────────────────────────────

_DEFAULT_MA_PARAMS = {
    "fast_period": 5,
    "slow_period": 20,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
}


TickerCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class AutoSelectConfig(BaseModel):
    """자동 종목 선정 설정 — 전략에 내장."""
    enabled: bool = False
    top_n: int = Field(default=10, ge=3, le=30)
    market: str = Field(default="ALL", pattern="^(KOSPI|KOSDAQ|ALL)$")
    min_volume_value: int = Field(default=10_000_000_000, ge=0)
    blacklist: list[TickerCode] = Field(default_factory=list, max_length=50)


class AutoSelectedTickersInfo(BaseModel):
    """전략에 저장된 마지막 자동 선정 결과."""
    tickers: list[str]
    generated_at: datetime
    rule_version: str
    details: list[dict] | None = None


class AutoTickerSelectionHistory(BaseModel):
    id: UUID
    generated_at: datetime
    rule_version: str
    triggered_by: str
    selected_tickers: list[dict]
    excluded_sample: list[dict] | None = None
    config_snapshot: dict


class AutoTickerPreviewResponse(BaseModel):
    """미저장 미리보기 — 현재 설정대로 돌렸을 때의 결과."""
    rule_version: str
    selected: list[dict]
    excluded_sample: list[dict]
    config_snapshot: dict
    available_cash: Decimal
    total_eval: Decimal
    max_position_pct: Decimal


class TradingStrategyCreate(BaseModel):
    account_id: UUID
    name: str = Field(max_length=100)
    strategy_type: StrategyType = StrategyType.MA_CROSSOVER
    params_json: dict = Field(default_factory=lambda: _DEFAULT_MA_PARAMS.copy())
    target_tickers: list[str] = Field(default_factory=list)
    interval_minutes: int = Field(default=10, ge=1, le=60)
    market_hours_only: bool = True
    # Phase 2: 전략별 초기 할당 자본 (필수). 0이면 매수 불가.
    initial_capital: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    # Phase 4: 처리 우선순위 (높을수록 우선). 0~100.
    priority: int = Field(default=0, ge=0, le=100)
    auto_select_config: AutoSelectConfig = Field(default_factory=AutoSelectConfig)


class TradingStrategyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    params_json: dict | None = None
    target_tickers: list[str] | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=60)
    market_hours_only: bool | None = None
    initial_capital: Decimal | None = Field(default=None, ge=Decimal("0"))
    priority: int | None = Field(default=None, ge=0, le=100)
    auto_select_config: AutoSelectConfig | None = None


class TradingStrategyResponse(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    strategy_type: StrategyType
    params_json: dict
    target_tickers: list[str]
    interval_minutes: int
    is_scheduled: bool
    market_hours_only: bool
    is_active: bool
    initial_capital: Decimal
    realized_pnl: Decimal
    priority: int
    auto_select_config: AutoSelectConfig
    auto_selected_tickers: AutoSelectedTickersInfo | None = None
    created_at: datetime
    updated_at: datetime


def strategy_to_response(strategy: TradingStrategyModel) -> TradingStrategyResponse:
    from app.services.strategy_capital import get_initial_capital, get_realized_pnl
    cfg_raw = strategy.auto_select_config or {}
    info: AutoSelectedTickersInfo | None = None
    stored = strategy.auto_selected_tickers or None
    if stored and stored.get("generated_at"):
        try:
            info = AutoSelectedTickersInfo.model_validate(stored)
        except Exception:  # noqa: BLE001 — 스키마 불일치 레코드 방어
            info = None
    return TradingStrategyResponse(
        id=strategy.id,
        account_id=strategy.account_id,
        name=strategy.name,
        strategy_type=strategy.strategy_type,
        params_json=strategy.params_json,
        target_tickers=strategy.target_tickers,
        interval_minutes=strategy.interval_minutes,
        is_scheduled=strategy.is_scheduled,
        market_hours_only=strategy.market_hours_only,
        is_active=strategy.is_active,
        initial_capital=get_initial_capital(strategy),
        realized_pnl=get_realized_pnl(strategy),
        priority=strategy.priority,
        auto_select_config=AutoSelectConfig.model_validate(
            {
                "enabled": cfg_raw.get("enabled", False),
                "top_n": cfg_raw.get("top_n", 10),
                "market": cfg_raw.get("market", "ALL"),
                "min_volume_value": cfg_raw.get("min_volume_value", 10_000_000_000),
                "blacklist": cfg_raw.get("blacklist", []),
            }
        ),
        auto_selected_tickers=info,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


# ──────────────────────────────────────────────
# TradingOrder
# ──────────────────────────────────────────────

class TradingOrderResponse(BaseModel):
    id: UUID
    account_id: UUID
    strategy_id: UUID | None
    side: OrderSide
    ticker: str
    ticker_name: str
    quantity: Decimal
    price: Decimal
    filled_quantity: Decimal | None
    filled_price: Decimal | None
    order_type: OrderType
    status: OrderStatus
    kis_order_id: str | None
    reason: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


def order_to_response(order: TradingOrderModel) -> TradingOrderResponse:
    return TradingOrderResponse(
        id=order.id,
        account_id=order.account_id,
        strategy_id=order.strategy_id,
        side=order.side,
        ticker=order.ticker,
        ticker_name=order.ticker_name,
        quantity=decrypt_decimal(order.quantity),
        price=decrypt_decimal(order.price),
        filled_quantity=decrypt_decimal_optional(order.filled_quantity),
        filled_price=decrypt_decimal_optional(order.filled_price),
        order_type=order.order_type,
        status=order.status,
        kis_order_id=order.kis_order_id,
        reason=order.reason,
        error_message=order.error_message,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


# ──────────────────────────────────────────────
# TradingPosition
# ──────────────────────────────────────────────

class TradingPositionResponse(BaseModel):
    id: UUID
    account_id: UUID
    strategy_id: UUID
    ticker: str
    ticker_name: str
    quantity: Decimal
    avg_buy_price: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    created_at: datetime
    updated_at: datetime


def position_to_response(position: TradingPositionModel) -> TradingPositionResponse:
    return TradingPositionResponse(
        id=position.id,
        account_id=position.account_id,
        strategy_id=position.strategy_id,
        ticker=position.ticker,
        ticker_name=position.ticker_name,
        quantity=decrypt_decimal(position.quantity),
        avg_buy_price=decrypt_decimal(position.avg_buy_price),
        current_price=Decimal(str(position.current_price)) if position.current_price else None,
        unrealized_pnl=decrypt_decimal_optional(position.unrealized_pnl),
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


# ──────────────────────────────────────────────
# Schedule
# ──────────────────────────────────────────────

class ScheduleStartRequest(BaseModel):
    strategy_id: UUID


class ScheduleStatusResponse(BaseModel):
    is_active: bool
    strategy_id: UUID | None = None
    interval_minutes: int | None = None
    next_run_at: datetime | None = None
    last_run: ScheduleLogSummary | None = None


class ScheduleLogSummary(BaseModel):
    id: UUID
    status: ScheduleLogStatus
    executed_at: datetime
    completed_at: datetime | None
    tickers_evaluated: int
    orders_placed: int
    orders_filled: int
    skip_reason: str | None
    error_message: str | None


def schedule_log_to_summary(log: TradingScheduleLogModel) -> ScheduleLogSummary:
    return ScheduleLogSummary(
        id=log.id,
        status=log.status,
        executed_at=log.executed_at,
        completed_at=log.completed_at,
        tickers_evaluated=log.tickers_evaluated,
        orders_placed=log.orders_placed,
        orders_filled=log.orders_filled,
        skip_reason=log.skip_reason,
        error_message=log.error_message,
    )


# ──────────────────────────────────────────────
# Performance
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# TradingDecision (Step 3: 승인 모드)
# ──────────────────────────────────────────────

class TradingDecisionResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    account_id: UUID
    ticker: str
    action: str
    confidence: int
    reason: str
    suggested_quantity: Decimal | None
    executed: bool
    blocked_reason: str | None
    approval_status: str | None
    approval_expires_at: datetime | None
    created_at: datetime


def decision_to_response(decision: TradingDecisionModel) -> TradingDecisionResponse:
    return TradingDecisionResponse(
        id=decision.id,
        strategy_id=decision.strategy_id,
        account_id=decision.account_id,
        ticker=decision.ticker,
        action=decision.action,
        confidence=decision.confidence,
        reason=decision.reason,
        suggested_quantity=decrypt_decimal_optional(decision.suggested_quantity),
        executed=decision.executed,
        blocked_reason=decision.blocked_reason,
        approval_status=decision.approval_status,
        approval_expires_at=decision.approval_expires_at,
        created_at=decision.created_at,
    )


# ──────────────────────────────────────────────
# Performance
# ──────────────────────────────────────────────

class TradingPerformanceResponse(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    total_realized_pnl: Decimal
    total_unrealized_pnl: Decimal
    initial_capital: Decimal
    current_value: Decimal
    return_rate: Decimal


# ──────────────────────────────────────────────
# AdaptiveRule (Step 4: 모듈 C)
# ──────────────────────────────────────────────

class AdaptiveRuleResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    version: int
    rule_text: str
    rationale: str | None
    generated_from: str | None
    is_active: bool
    created_at: datetime
    expires_at: datetime | None


class AdaptiveRuleUpdate(BaseModel):
    is_active: bool


def adaptive_rule_to_response(rule: AdaptiveRuleModel) -> AdaptiveRuleResponse:
    return AdaptiveRuleResponse(
        id=rule.id,
        strategy_id=rule.strategy_id,
        version=rule.version,
        rule_text=rule.rule_text,
        rationale=rule.rationale,
        generated_from=rule.generated_from,
        is_active=rule.is_active,
        created_at=rule.created_at,
        expires_at=rule.expires_at,
    )
