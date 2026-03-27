"""사용자 모델"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 2FA (TOTP) — totp_secret은 암호화하여 저장
    totp_secret: Mapped[str | None] = mapped_column(String(500), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 2FA 재설정 시 기존 시크릿을 덮어쓰지 않고 임시 보관 (verify 전까지)
    pending_totp_secret: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 로그인 실패 추적 (5회 실패 시 15분 잠금)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 텔레그램 알림
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 온보딩
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 관계
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    access_logs = relationship("AccessLog", back_populates="user", cascade="all, delete-orphan")
    portfolio_groups = relationship("PortfolioGroup", back_populates="user", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="user", cascade="all, delete-orphan")
    asset_snapshots = relationship("AssetSnapshot", back_populates="user", cascade="all, delete-orphan")
