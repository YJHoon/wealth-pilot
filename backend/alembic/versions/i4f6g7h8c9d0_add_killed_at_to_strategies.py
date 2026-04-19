"""add killed_at and killed_reason to trading_strategies

Revision ID: i4f6g7h8c9d0
Revises: h3e5f6g7b8c9
Create Date: 2026-04-16

Phase 4: 킬 스위치 발동 영속화.
- killed_at: 자동 중단(킬 스위치 발동) 시각. NULL이면 정상 또는 수동 비활성화.
- killed_reason: 자동 중단 사유 (RiskCheck.reason).

수동 비활성화(is_active=False)와 자동 중단을 운영상 구분하기 위함.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i4f6g7h8c9d0"
down_revision: Union[str, Sequence[str], None] = "h3e5f6g7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_strategies",
        sa.Column("killed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trading_strategies",
        sa.Column("killed_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trading_strategies", "killed_reason")
    op.drop_column("trading_strategies", "killed_at")
