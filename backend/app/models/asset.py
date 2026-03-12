"""자산 모델

금액 관련 필드(quantity, purchase_price, sold_price, realized_pnl)는
DB에 AES-256 암호화된 문자열로 저장된다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AssetType(str, enum.Enum):
    CASH = "cash"
    DOMESTIC_STOCK = "domestic_stock"
    FOREIGN_STOCK = "foreign_stock"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"


class AssetStatus(str, enum.Enum):
    ACTIVE = "active"
    SOLD = "sold"
    DELISTED = "delisted"


class Currency(str, enum.Enum):
    KRW = "KRW"
    USD = "USD"
    EUR = "EUR"
    JPY = "JPY"
    BTC = "BTC"
    ETH = "ETH"  # 프론트엔드 타입과 동기화


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_groups.id", ondelete="SET NULL"), nullable=True
    )

    # 자산 기본 정보
    type: Mapped[AssetType] = mapped_column(Enum(AssetType), nullable=False)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus), default=AssetStatus.ACTIVE, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency), default=Currency.KRW, nullable=False
    )

    # 암호화 저장 필드 (문자열로 저장, 앱 레벨에서 암복호화)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)          # encrypt_decimal
    purchase_price: Mapped[str] = mapped_column(Text, nullable=False)   # encrypt_decimal

    # 현재가 (시세 API에서 갱신, 암호화 불필요 — 공개 정보)
    current_price: Mapped[str | None] = mapped_column(Numeric(20, 4), nullable=True)

    # 메타데이터 (은행명, 이율 등 유형별 추가 정보)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 매도 관련 (암호화 저장)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sold_price: Mapped[str | None] = mapped_column(Text, nullable=True)        # encrypt_decimal_optional
    realized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)      # encrypt_decimal_optional

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 관계
    user = relationship("User", back_populates="assets")
    group = relationship("PortfolioGroup", back_populates="assets")
