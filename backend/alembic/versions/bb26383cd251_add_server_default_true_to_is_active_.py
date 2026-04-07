"""add server_default true to is_active columns

Revision ID: bb26383cd251
Revises: 335dfd3e456b
Create Date: 2026-04-02 22:43:43.740279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb26383cd251'
down_revision: Union[str, None] = '335dfd3e456b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'trading_accounts', 'is_active',
        server_default=sa.text('true'),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.alter_column(
        'trading_strategies', 'is_active',
        server_default=sa.text('true'),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'trading_strategies', 'is_active',
        server_default=None,
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.alter_column(
        'trading_accounts', 'is_active',
        server_default=None,
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
