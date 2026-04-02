"""add cash_balance to trading_accounts

Revision ID: 335dfd3e456b
Revises: aabb3fbb826b
Create Date: 2026-04-02 13:54:56.774367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '335dfd3e456b'
down_revision: Union[str, None] = 'aabb3fbb826b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trading_accounts', sa.Column('cash_balance', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('trading_accounts', 'cash_balance')
