"""add priority to trading_strategies

Revision ID: j5g7h8i9d0e1
Revises: i4f6g7h8c9d0
Create Date: 2026-04-19

Phase 4: 전략 처리 우선순위.
- priority: INT NOT NULL DEFAULT 0. 높을수록 우선.
  같은 종목 반대 방향 주문 네팅·충돌 해결 시 tiebreaker로 사용.
  전략 목록 정렬(priority DESC, created_at ASC)에도 활용.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j5g7h8i9d0e1"
down_revision: Union[str, Sequence[str], None] = "i4f6g7h8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_strategies",
        sa.Column(
            "priority",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("trading_strategies", "priority")
