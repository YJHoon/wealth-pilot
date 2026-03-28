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
        TradingAccount as TradingAccountModel,
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
    is_active: bool
    token_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


def account_to_response(account: TradingAccountModel) -> TradingAccountResponse:
    return TradingAccountResponse(
        id=account.id,
        mode=account.mode,
        initial_capital=decrypt_decimal(account.initial_capital),
        is_active=account.is_active,
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
    target_tickers: list[str] = Field(min_length=1)
    interval_minutes: int = Field(default=10, ge=1, le=60)
    market_hours_only: bool = True


class TradingStrategyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    params_json: dict | None = None
    target_tickers: list[str] | None = Field(default=None, min_length=1)
    interval_minutes: int | None = Field(default=None, ge=1, le=60)
    market_hours_only: bool | None = None


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
    created_at: datetime
    updated_at: datetime


def strategy_to_response(strategy: TradingStrategyModel) -> TradingStrategyResponse:
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
