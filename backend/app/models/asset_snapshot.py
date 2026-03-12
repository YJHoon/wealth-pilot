"""자산 스냅샷 모델 — 일별 자산 상태 기록"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AssetSnapshot(Base):
    __tablename__ = "asset_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 총 자산 (암호화)
    total_value_krw: Mapped[str] = mapped_column(Text, nullable=False)  # encrypt_decimal

    # 유형별/그룹별 내역 (JSONB — 비암호화, 비중(%)만 저장)
    breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 관계
    user = relationship("User", back_populates="asset_snapshots")
