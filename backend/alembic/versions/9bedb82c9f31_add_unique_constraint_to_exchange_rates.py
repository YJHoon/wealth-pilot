"""add unique constraint to exchange_rates

Revision ID: 9bedb82c9f31
Revises: c23ad9233cb6
Create Date: 2026-03-23 23:05:48.061673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9bedb82c9f31'
down_revision: Union[str, None] = 'c23ad9233cb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_exchange_rate_pair', 'exchange_rates', ['from_currency', 'to_currency'])


def downgrade() -> None:
    op.drop_constraint('uq_exchange_rate_pair', 'exchange_rates', type_='unique')
