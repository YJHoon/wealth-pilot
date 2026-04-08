"""자동매매 관련 모델

KIS API 계좌, 전략, 주문, 포지션, 스케줄 실행 이력.
금액 관련 필드는 DB에 AES-256 암호화된 문자열로 저장된다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class TradingMode(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"


class StrategyType(str, enum.Enum):
    MA_CROSSOVER = "ma_crossover"
    MEAN_REVERSION = "mean_reversion"
    CUSTOM = "custom"


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ScheduleLogStatus(str, enum.Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class TradingAccount(Base):
    """매매 계좌 설정 (KIS 인증정보는 .env에서 로드)."""

    __tablename__ = "trading_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "mode", name="uq_trading_account_user_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    mode: Mapped[TradingMode] = mapped_column(
        Enum(TradingMode, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    # 초기 투자금 (AES-256 암호화)
    initial_capital: Mapped[str] = mapped_column(Text, nullable=False)

    # 현재 현금 잔고 (AES-256 암호화, KIS 잔고 동기화 시 갱신)
    cash_balance: Mapped[str | None] = mapped_column(Text, nullable=True)

    # KIS Access Token 캐시 (AES-256 암호화, 임시)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    # 관계
    user = relationship("User", backref="trading_accounts")
    strategies = relationship("TradingStrategy", back_populates="account", cascade="all, delete-orphan")
    orders = relationship("TradingOrder", back_populates="account", cascade="all, delete-orphan")
    positions = relationship("TradingPosition", back_populates="account", cascade="all, delete-orphan")


class TradingStrategy(Base):
    """전략 설정 — 타입, 파라미터, 대상 종목, 스케줄 간격."""

    __tablename__ = "trading_strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    # 전략 파라미터 (예: fast_period, slow_period, rsi_period, ...)
    params_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # 대상 종목 목록 (예: ["005930", "000660"])
    target_tickers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # 스케줄 설정
    interval_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    market_hours_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Phase 2: 전략별 자본 할당 (모델 1 - Drift 허용)
    # 생성 시점 스냅샷, 이후 비율 재계산 없음 (AES-256 암호화)
    initial_capital: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 누적 실현 손익 (AES-256 암호화). None은 0으로 해석.
    realized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    # 관계
    user = relationship("User", backref="trading_strategies")
    account = relationship("TradingAccount", back_populates="strategies")
    orders = relationship("TradingOrder", back_populates="strategy")
    schedule_logs = relationship("TradingScheduleLog", back_populates="strategy", cascade="all, delete-orphan")


class TradingOrder(Base):
    """주문 이력 — 매수/매도, 체결 상태."""

    __tablename__ = "trading_orders"
    __table_args__ = (
        Index("ix_trading_orders_user_created", "user_id", "created_at"),
        Index("ix_trading_orders_schedule_log", "schedule_log_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_strategies.id", ondelete="SET NULL"),
        nullable=True,
    )
    schedule_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_schedule_logs.id", ondelete="SET NULL"),
        nullable=True,
    )

    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    ticker_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    # 주문 수량/가격 (AES-256 암호화)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[str] = mapped_column(Text, nullable=False)

    # 체결 수량/가격 (AES-256 암호화)
    filled_quantity: Mapped[str | None] = mapped_column(Text, nullable=True)
    filled_price: Mapped[str | None] = mapped_column(Text, nullable=True)

    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, values_callable=lambda e: [x.value for x in e]),
        default=OrderType.MARKET,
        nullable=False,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, values_callable=lambda e: [x.value for x in e]),
        default=OrderStatus.PENDING,
        nullable=False,
    )

    # KIS 주문 ID
    kis_order_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    kis_order_date: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # 주문 사유 (전략 신호 설명)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    # 관계
    account = relationship("TradingAccount", back_populates="orders")
    strategy = relationship("TradingStrategy", back_populates="orders")
    schedule_log = relationship("TradingScheduleLog", back_populates="orders")


class TradingPosition(Base):
    """현재 보유 포지션 — 종목별 집계."""

    __tablename__ = "trading_positions"
    __table_args__ = (
        UniqueConstraint("account_id", "ticker", name="uq_trading_position_account_ticker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    ticker_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    # 보유 수량 / 평균 매입가 (AES-256 암호화)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)
    avg_buy_price: Mapped[str] = mapped_column(Text, nullable=False)

    # 현재가 (공개 정보, 암호화 불필요)
    current_price: Mapped[float | None] = mapped_column(Numeric(20, 4), nullable=True)

    # 평가 손익 (AES-256 암호화)
    unrealized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    # 관계
    account = relationship("TradingAccount", back_populates="positions")


class TradingScheduleLog(Base):
    """스케줄 실행 이력 — 매 cycle 결과 기록."""

    __tablename__ = "trading_schedule_logs"
    __table_args__ = (
        Index("ix_trading_schedule_logs_user_executed", "user_id", "executed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_strategies.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[ScheduleLogStatus] = mapped_column(
        Enum(ScheduleLogStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    # 실행 시각
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # 실행 결과
    tickers_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_placed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    orders_filled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 실현 손익 (AES-256 암호화)
    realized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 스킵/에러 사유
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # 관계
    strategy = relationship("TradingStrategy", back_populates="schedule_logs")
    orders = relationship("TradingOrder", back_populates="schedule_log")
