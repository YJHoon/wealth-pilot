"""투자 분석 관련 모델

관심종목(Watchlist)과 시뮬레이션(Simulation).
목표 매수/매도 가격은 DB에 AES-256 암호화된 문자열로 저장된다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
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

class SimulationType(str, enum.Enum):
    DCA = "dca"
    PORTFOLIO = "portfolio"
    SCENARIO = "scenario"


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class Watchlist(Base):
    """관심종목 — 목표 매수/매도 가격은 AES-256 암호화."""

    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", "market", name="uq_watchlist_user_ticker_market"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)

    # 목표 매수/매도 가격 (AES-256 암호화)
    target_buy_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_sell_price: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 알림 기준 (%, 비암호화)
    alert_threshold_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    # 관계
    user = relationship("User", backref="watchlists")


class Simulation(Base):
    """시뮬레이션 결과 — 30일 후 만료."""

    __tablename__ = "simulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    type: Mapped[SimulationType] = mapped_column(
        Enum(SimulationType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    # 관계
    user = relationship("User", backref="simulations")
