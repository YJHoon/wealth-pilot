"""step3 safety guards — approval_status + approval_expires_at

Revision ID: g2d4e5f6a7b8
Revises: f1b9c4d27e3a
Create Date: 2026-04-09

Stage 3 Step 3:
- trading_decisions 테이블에 사용자 승인 모드 컬럼 추가
  - approval_status: pending/approved/rejected/expired/null
  - approval_expires_at: 승인 만료 시각
- 부분 인덱스: pending 상태만 빠르게 조회
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g2d4e5f6a7b8"
down_revision: Union[str, None] = "f1b9c4d27e3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_decisions",
        sa.Column("approval_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "trading_decisions",
        sa.Column(
            "approval_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_trading_decisions_approval_pending",
        "trading_decisions",
        ["user_id", "approval_status"],
        postgresql_where=sa.text("approval_status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_trading_decisions_approval_pending", table_name="trading_decisions")
    op.drop_column("trading_decisions", "approval_expires_at")
    op.drop_column("trading_decisions", "approval_status")
