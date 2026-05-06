"""자동매매 관련 모델

KIS API 계좌, 전략, 주문, 포지션, 스케줄 실행 이력.
금액 관련 필드는 DB에 AES-256 암호화된 문자열로 저장된다.
"""

import enum
import uuid

import sqlalchemy as sa
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
from pgvector.sqlalchemy import Vector
from sqlalchemy.sql import expression
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
    # Stage 3: LLM 어드바이저
    LLM_ADVISOR = "llm_advisor"


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

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=expression.true(), nullable=False,
    )

    # Phase 4: 주문 네팅 옵션 (opt-in).
    # True면 같은 계좌·같은 종목의 반대 방향 PENDING/SUBMITTED 주문이 있을 때
    # 신규 주문을 전량 스킵해 동시 매수/매도 충돌을 차단한다.
    allow_netting: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=expression.false(), nullable=False,
    )

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

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=expression.true(), nullable=False,
    )

    # Phase 2: 전략별 자본 할당 (모델 1 - Drift 허용)
    # 생성 시점 스냅샷, 이후 비율 재계산 없음 (AES-256 암호화)
    initial_capital: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 누적 실현 손익 (AES-256 암호화). None은 0으로 해석.
    realized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 4: 킬 스위치 발동 기록 (수동 비활성화와 구분)
    # killed_at이 NULL이면 정상, 값이 있으면 자동 중단된 전략.
    killed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    killed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 4: 전략 처리 우선순위 (높을수록 우선).
    # 같은 종목 반대 방향 주문 네팅·충돌 해결 시 tiebreaker로 사용.
    priority: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )

    # 자동 종목 선정 설정.
    # {enabled, top_n, market, min_volume_value, blacklist, include_holdings}
    auto_select_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb"),
    )
    # 마지막 자동 선정 결과. {tickers: [...], generated_at: iso, rule_version}
    auto_selected_tickers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )

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
    positions = relationship("TradingPosition", back_populates="strategy")
    schedule_logs = relationship("TradingScheduleLog", back_populates="strategy", cascade="all, delete-orphan")
    auto_ticker_selections = relationship(
        "AutoTickerSelection", back_populates="strategy", cascade="all, delete-orphan",
    )


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
    # 원클릭 분석·매매에서 발주된 주문이면 출처 항목 ID. 자동매매면 NULL.
    analysis_run_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_run_items.id", ondelete="SET NULL"),
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

    # 체결 폴링: 마지막으로 KIS에 체결조회한 시각 (grace period 판정용)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # 체결 폴링: eager apply 직전의 포지션 (수량/평균단가) 스냅샷 (AES-256 암호화)
    # 부분체결/거부 롤백 시 새 평균단가 재계산에 사용.
    pre_apply_qty: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_apply_avg_buy_price: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        UniqueConstraint(
            "account_id", "strategy_id", "ticker",
            name="uq_trading_position_account_strategy_ticker",
        ),
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
    # Phase 3: 전략별 포지션 격리
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_strategies.id", ondelete="RESTRICT"),
        nullable=False, index=True,
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
    strategy = relationship("TradingStrategy", back_populates="positions")


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


# ──────────────────────────────────────────────
# Stage 3: LLM 어드바이저
# ──────────────────────────────────────────────

class TradingDecision(Base):
    """LLM 어드바이저 의사결정 로그.

    매 LLM 호출마다 한 행을 남긴다. 발주 여부와 무관하게 기록되며
    (executed=False면 confidence 미달/검증 실패 등으로 차단됨), 후속 모듈
    (B: 메모리 컨텍스트, C: 메타분석)이 이 테이블을 학습 데이터로 사용한다.

    금액/수량 필드는 AES-256 암호화된 문자열로 저장한다.
    """

    __tablename__ = "trading_decisions"
    __table_args__ = (
        Index("ix_trading_decisions_strategy_created", "strategy_id", "created_at"),
        Index("ix_trading_decisions_user_created", "user_id", "created_at"),
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
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    schedule_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_schedule_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 발주가 실제로 일어난 경우 연결되는 주문
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # buy/sell/hold
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)  # 0~100
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # LLM이 제안한 수량/금액 (AES-256 암호화). hold면 None.
    suggested_quantity: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_amount: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 검증/발주 결과
    executed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.false(), nullable=False,
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 결과 (체결 후 갱신 — 모듈 B/C에서 사용)
    realized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)
    holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_price: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 메타
    market_regime: Mapped[str | None] = mapped_column(String(30), nullable=True)
    used_indicators: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 호출 비용 추적용 (선택)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Step 3: 사용자 승인 모드
    # "pending" | "approved" | "rejected" | "expired" | None(기존 즉시 실행)
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class AdaptiveRule(Base):
    """모듈 C(주간 메타 분석)가 생성한 자동 진화 규칙.

    Step 1에서는 스키마만 정의한다. 모듈 C 구현 후 실제 INSERT가 시작된다.
    """

    __tablename__ = "adaptive_rules"
    __table_args__ = (
        Index("ix_adaptive_rules_strategy_active", "strategy_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_from: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=expression.true(), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class DecisionEmbedding(Base):
    """모듈 D(RAG 유사 케이스 회상)용 의사결정 벡터 임베딩.

    TradingDecision과 1:1로 매핑되며, 유사한 과거 매매 상황을
    코사인 유사도로 검색해 LLM 프롬프트에 주입한다.
    """

    __tablename__ = "decision_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_decisions.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    # 384차원 벡터 (intfloat/multilingual-e5-small)
    embedding = mapped_column(Vector(384), nullable=False)
    # 임베딩 원본 텍스트 (디버그/모델 교체 시 재임베딩용)
    context_text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # 관계 (1:1 — decision_id UNIQUE)
    decision = relationship(
        "TradingDecision",
        backref=sa.orm.backref("embedding_row", uselist=False),
    )


class AutoTickerSelection(Base):
    """자동 종목 선정 이력 (audit + UI 표시용).

    전략당 최신 30건 유지 cron으로 정리한다.
    """

    __tablename__ = "auto_ticker_selections"
    __table_args__ = (
        Index(
            "ix_auto_ticker_selections_strategy_generated",
            "strategy_id", sa.text("generated_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        default=uuid.uuid4,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    # 'v1-volume-rank' 등 룰 버전 태그
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    # [{ticker, name, score, reason}]
    selected_tickers: Mapped[list] = mapped_column(JSONB, nullable=False)
    # 디버깅용 — 제외된 후보 상위 N개와 사유
    excluded_sample: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 'schedule' | 'lazy' | 'manual'
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)

    strategy = relationship(
        "TradingStrategy", back_populates="auto_ticker_selections",
    )


# ──────────────────────────────────────────────
# 원클릭 분석·매매 (Advisory) — 자동매매와 분리된 도메인
# ──────────────────────────────────────────────

class AnalysisRunStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    READY = "ready"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"


class AnalysisItemSource(str, enum.Enum):
    HOLDING = "holding"
    AUTO_PICK = "auto_pick"


class AnalysisItemAction(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class AnalysisItemDecision(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SKIPPED = "skipped"
    REJECTED = "rejected"


class AnalysisRun(Base):
    """원클릭 분석·매매 1회 실행 단위.

    사용자가 버튼 클릭 → 보유 + 자동선정 후보를 LLM으로 분석.
    종목별 결과는 AnalysisRunItem에, 발주는 TradingOrder에 기록되며
    체결분은 자동매매 TradingPosition과 분리된 AdvisoryPosition에 누적된다.
    """

    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_runs_user_started", "user_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[TradingMode] = mapped_column(
        Enum(TradingMode, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[AnalysisRunStatus] = mapped_column(
        Enum(AnalysisRunStatus, values_callable=lambda e: [x.value for x in e]),
        default=AnalysisRunStatus.PENDING,
        nullable=False,
    )

    # 사용자가 1회 run에 할당한 예산 (AES-256 암호화)
    budget_krw: Mapped[str] = mapped_column(Text, nullable=False)

    # 후보풀 옵션 스냅샷: {top_n, market, min_volume_value, blacklist, include_holdings, ...}
    candidate_pool_options: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # 결과 TTL — 경과 시 /execute 거절, 재분석 강제
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # 진행/요약 정보 (분석 종목 수, 차단 사유 카운트 등)
    summary_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    items = relationship(
        "AnalysisRunItem", back_populates="run", cascade="all, delete-orphan",
    )


class AnalysisRunItem(Base):
    """원클릭 분석 결과 — 종목 1건."""

    __tablename__ = "analysis_run_items"
    __table_args__ = (
        Index("ix_analysis_run_items_run", "run_id"),
        UniqueConstraint(
            "run_id", "ticker", name="uq_analysis_run_item_run_ticker",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    ticker_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    source: Mapped[AnalysisItemSource] = mapped_column(
        Enum(AnalysisItemSource, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    action: Mapped[AnalysisItemAction] = mapped_column(
        Enum(AnalysisItemAction, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 분석 시점 참조 가격 / 제안 수량 (AES-256 암호화)
    ref_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_qty: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision: Mapped[AnalysisItemDecision] = mapped_column(
        Enum(AnalysisItemDecision, values_callable=lambda e: [x.value for x in e]),
        default=AnalysisItemDecision.PENDING,
        nullable=False,
    )
    # 발주 시 연결되는 주문 (1:1, 부분체결 등은 order 레벨에서 관리)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    # confidence 미달/리스크 차단 사유
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    run = relationship("AnalysisRun", back_populates="items")


class AdvisoryPosition(Base):
    """원클릭 매매로 매수한 수동 보유분 — 자동매매 TradingPosition과 완전 분리.

    정합성 식: KIS실잔고(ticker) = Σ TradingPosition(ticker) + AdvisoryPosition(ticker)
    """

    __tablename__ = "advisory_positions"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "ticker", name="uq_advisory_position_account_ticker",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
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

    # 현재가 (공개 정보)
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
