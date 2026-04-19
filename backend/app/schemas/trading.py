"""자동매매 스키마 — Pydantic v2"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

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


class TradingStrategyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    params_json: dict | None = None
    target_tickers: list[str] | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=60)
    market_hours_only: bool | None = None
    initial_capital: Decimal | None = Field(default=None, ge=Decimal("0"))
    priority: int | None = Field(default=None, ge=0, le=100)


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
    created_at: datetime
    updated_at: datetime


def strategy_to_response(strategy: TradingStrategyModel) -> TradingStrategyResponse:
    from app.services.strategy_capital import get_initial_capital, get_realized_pnl
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
