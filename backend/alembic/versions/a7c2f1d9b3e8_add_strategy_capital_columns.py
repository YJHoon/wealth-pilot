"""add initial_capital and realized_pnl to trading_strategies (Phase 2)

Revision ID: a7c2f1d9b3e8
Revises: 335dfd3e456b
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c2f1d9b3e8"
down_revision: Union[str, None] = "335dfd3e456b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 다중 전략 단일 계좌 자본 관리 — Phase 2
    # 두 컬럼 모두 AES-256 암호화 문자열로 저장 (Text)
    op.add_column(
        "trading_strategies",
        sa.Column("initial_capital", sa.Text(), nullable=True),
    )
    op.add_column(
        "trading_strategies",
        sa.Column("realized_pnl", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trading_strategies", "realized_pnl")
    op.drop_column("trading_strategies", "initial_capital")
