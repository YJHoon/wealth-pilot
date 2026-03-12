"""create_initial_tables

Revision ID: 61ba483deeff
Revises:
Create Date: 2026-03-10 13:21:38.476575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '61ba483deeff'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# postgresql.ENUM(create_type=False): op.create_table 시 자동 생성 방지
# (아래에서 raw SQL로 먼저 생성 후 참조만 함)
assettype_enum = postgresql.ENUM('cash', 'domestic_stock', 'foreign_stock', 'crypto', 'real_estate', name='assettype', create_type=False)
assetstatus_enum = postgresql.ENUM('active', 'sold', 'delisted', name='assetstatus', create_type=False)
currency_enum = postgresql.ENUM('KRW', 'USD', 'EUR', 'JPY', 'BTC', name='currency', create_type=False)


def upgrade() -> None:
    # exchange_rates (FK 없음, 먼저 생성)
    op.create_table(
        'exchange_rates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('from_currency', sa.String(10), nullable=False),
        sa.Column('to_currency', sa.String(10), nullable=False),
        sa.Column('rate', sa.Numeric(20, 8), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exchange_rates_from_currency', 'exchange_rates', ['from_currency'])
    op.create_index('ix_exchange_rates_to_currency', 'exchange_rates', ['to_currency'])

    # users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('totp_secret', sa.String(500), nullable=True),
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # sessions
    op.create_table(
        'sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('device_info', sa.String(500), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])

    # access_logs
    op.create_table(
        'access_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('device_info', sa.String(500), nullable=False),
        sa.Column('is_suspicious', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_access_logs_user_id', 'access_logs', ['user_id'])

    # portfolio_groups
    op.create_table(
        'portfolio_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_portfolio_groups_user_id', 'portfolio_groups', ['user_id'])

    # asset_snapshots
    op.create_table(
        'asset_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('total_value_krw', sa.Text(), nullable=False),
        sa.Column('breakdown', postgresql.JSONB(), nullable=True),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_asset_snapshots_user_id', 'asset_snapshots', ['user_id'])
    op.create_index('ix_asset_snapshots_snapshot_date', 'asset_snapshots', ['snapshot_date'])

    # assets — ENUM 타입 먼저 생성 (asyncpg 호환을 위해 raw SQL 사용)
    op.execute(sa.text("CREATE TYPE assettype AS ENUM ('cash', 'domestic_stock', 'foreign_stock', 'crypto', 'real_estate')"))
    op.execute(sa.text("CREATE TYPE assetstatus AS ENUM ('active', 'sold', 'delisted')"))
    op.execute(sa.text("CREATE TYPE currency AS ENUM ('KRW', 'USD', 'EUR', 'JPY', 'BTC')"))

    op.create_table(
        'assets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=True),
        sa.Column('type', assettype_enum, nullable=False),
        sa.Column('status', assetstatus_enum, nullable=False, server_default='active'),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=True),
        sa.Column('currency', currency_enum, nullable=False, server_default='KRW'),
        sa.Column('quantity', sa.Text(), nullable=False),
        sa.Column('purchase_price', sa.Text(), nullable=False),
        sa.Column('current_price', sa.Numeric(20, 4), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('sold_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sold_price', sa.Text(), nullable=True),
        sa.Column('realized_pnl', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['portfolio_groups.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_assets_user_id', 'assets', ['user_id'])


def downgrade() -> None:
    op.drop_table('assets')
    op.execute(sa.text("DROP TYPE IF EXISTS assettype"))
    op.execute(sa.text("DROP TYPE IF EXISTS assetstatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS currency"))
    op.drop_table('asset_snapshots')
    op.drop_table('portfolio_groups')
    op.drop_table('access_logs')
    op.drop_table('sessions')
    op.drop_table('users')
    op.drop_table('exchange_rates')
