"""싱글유저: KIS 인증정보를 DB에서 환경변수로 이동

Revision ID: 193992abc75f
Revises: 43a3029f6547
Create Date: 2026-03-26 10:15:44.453518

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '193992abc75f'
down_revision: Union[str, None] = '43a3029f6547'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('trading_accounts', 'account_number')
    op.drop_column('trading_accounts', 'app_secret')
    op.drop_column('trading_accounts', 'account_product_code')
    op.drop_column('trading_accounts', 'app_key')


def downgrade() -> None:
    op.add_column('trading_accounts', sa.Column('app_key', sa.TEXT(), autoincrement=False, nullable=False))
    op.add_column('trading_accounts', sa.Column('account_product_code', sa.VARCHAR(length=2), autoincrement=False, nullable=False))
    op.add_column('trading_accounts', sa.Column('app_secret', sa.TEXT(), autoincrement=False, nullable=False))
    op.add_column('trading_accounts', sa.Column('account_number', sa.TEXT(), autoincrement=False, nullable=False))
