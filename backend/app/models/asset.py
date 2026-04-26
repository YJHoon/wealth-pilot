"""자산 모델

금액 관련 필드(quantity, purchase_price, sold_price, realized_pnl)는
DB에 AES-256 암호화된 문자열로 저장된다.

source 필드로 수동 등록(manual)과 KIS 동기화(kis) 자산을 구분한다.
KIS 자산은 잔고 새로고침으로만 변동되며, API 레벨에서 수정/매도/삭제가 차단된다.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func, text
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


class AssetSource(str, enum.Enum):
    MANUAL = "manual"
    KIS = "kis"


class Currency(str, enum.Enum):
    KRW = "KRW"
    USD = "USD"
    EUR = "EUR"
    JPY = "JPY"


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index(
            'uq_asset_manual_cash_per_currency',
            'user_id', 'currency',
            unique=True,
            postgresql_where=text(
                "type = 'cash' AND status = 'active' AND source = 'manual'"
            ),
        ),
        Index(
            'uq_asset_kis_cash_per_account_currency',
            'user_id', 'trading_account_id', 'currency',
            unique=True,
            postgresql_where=text(
                "type = 'cash' AND status = 'active' AND source = 'kis'"
            ),
        ),
        Index(
            'uq_asset_kis_holding_per_account_ticker',
            'user_id', 'trading_account_id', 'external_ticker',
            unique=True,
            postgresql_where=text(
                "source = 'kis' AND status = 'active' AND external_ticker IS NOT NULL"
            ),
        ),
    )

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
    type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, values_callable=lambda e: [x.value for x in e]),
        default=AssetStatus.ACTIVE,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, values_callable=lambda e: [x.value for x in e]),
        default=Currency.KRW,
        nullable=False,
    )

    # 암호화 저장 필드 (문자열로 저장, 앱 레벨에서 암복호화)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)          # encrypt_decimal
    purchase_price: Mapped[str] = mapped_column(Text, nullable=False)   # encrypt_decimal

    # 현재가 (시세 API에서 갱신, 암호화 불필요 — 공개 정보)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)

    # 메타데이터 (은행명, 이율 등 유형별 추가 정보)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 매도 관련 (암호화 저장)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sold_price: Mapped[str | None] = mapped_column(Text, nullable=True)        # encrypt_decimal_optional
    realized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)      # encrypt_decimal_optional

    # 동기화 출처 (manual: 사용자 수동 등록, kis: KIS 잔고 자동 동기화)
    source: Mapped[AssetSource] = mapped_column(
        Enum(AssetSource, values_callable=lambda e: [x.value for x in e]),
        default=AssetSource.MANUAL,
        nullable=False,
    )
    # KIS 동기화 자산일 때만 채워짐. 사용자가 계좌를 비활성화해도 자산 이력은 보존.
    trading_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trading_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # KIS pdno (종목코드). DOMESTIC_STOCK용. CASH는 NULL.
    external_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 마지막 KIS 동기화 시각
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 관계
    user = relationship("User", back_populates="assets")
    group = relationship("PortfolioGroup", back_populates="assets")
    trading_account = relationship("TradingAccount")
