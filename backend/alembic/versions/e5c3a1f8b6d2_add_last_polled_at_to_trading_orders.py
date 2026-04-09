"""add fill polling columns to trading_orders

Revision ID: e5c3a1f8b6d2
Revises: d8f4e2c1b9a7
Create Date: 2026-04-08

체결 폴링 도입:
- last_polled_at: 마지막으로 KIS에 체결조회한 시각 (grace period 판정).
- pre_apply_qty / pre_apply_avg_buy_price (AES-256 암호화):
  eager apply 직전의 (수량, 평균단가) 스냅샷.
  부분체결/거부 시 롤백 공식이 새 평균단가를 정확히 재계산하기 위해 필요.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5c3a1f8b6d2"
down_revision: Union[str, Sequence[str], None] = "d8f4e2c1b9a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_orders",
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trading_orders",
        sa.Column("pre_apply_qty", sa.Text(), nullable=True),
    )
    op.add_column(
        "trading_orders",
        sa.Column("pre_apply_avg_buy_price", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trading_orders", "pre_apply_avg_buy_price")
    op.drop_column("trading_orders", "pre_apply_qty")
    op.drop_column("trading_orders", "last_polled_at")
