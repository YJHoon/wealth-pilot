"""add allow_netting to trading_accounts

Revision ID: k6h8i9j0e1f2
Revises: j5g7h8i9d0e1
Create Date: 2026-04-19

Phase 4: 주문 네팅 옵션.
- allow_netting: BOOL NOT NULL DEFAULT FALSE. Opt-in.
  같은 계좌·같은 종목의 반대 방향 PENDING/SUBMITTED 주문이 있을 때
  신규 주문을 전량 스킵해 동시 매수/매도 충돌을 차단한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k6h8i9j0e1f2"
down_revision: Union[str, Sequence[str], None] = "j5g7h8i9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_accounts",
        sa.Column(
            "allow_netting",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("trading_accounts", "allow_netting")
