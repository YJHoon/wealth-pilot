"""add uq_asset_cash_per_currency partial unique index

Revision ID: c23ad9233cb6
Revises: c4d5e6f7a8b9
Create Date: 2026-03-16 10:18:21.836606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'c23ad9233cb6'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'uq_asset_cash_per_currency',
        'assets',
        ['user_id', 'status', 'currency'],
        unique=True,
        postgresql_where=text("type = 'cash'"),
    )


def downgrade() -> None:
    op.drop_index('uq_asset_cash_per_currency', table_name='assets')
