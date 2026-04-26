"""add KIS sync columns to assets and rework cash uniqueness

source/trading_account_id/external_ticker/last_synced_at 추가.
KIS 동기화 자산과 수동 등록 자산을 분리해 관리한다.

기존 uq_asset_cash_per_currency partial index를 source별로 분리:
- manual cash: (user_id, currency)
- KIS cash: (user_id, trading_account_id, currency)
KIS 보유종목용:
- (user_id, trading_account_id, external_ticker) where source='kis' AND status='active'

Revision ID: m8j0k1l2g3h4
Revises: l7i9j0k1f2g3
Create Date: 2026-04-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = 'm8j0k1l2g3h4'
down_revision: Union[str, None] = 'l7i9j0k1f2g3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) assetsource enum 타입 생성
    asset_source = sa.Enum('manual', 'kis', name='assetsource')
    asset_source.create(op.get_bind(), checkfirst=True)

    # 2) 컬럼 추가
    op.add_column(
        'assets',
        sa.Column(
            'source',
            sa.Enum('manual', 'kis', name='assetsource', create_type=False),
            nullable=False,
            server_default='manual',
        ),
    )
    op.add_column(
        'assets',
        sa.Column(
            'trading_account_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('trading_accounts.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.add_column('assets', sa.Column('external_ticker', sa.String(length=20), nullable=True))
    op.add_column(
        'assets',
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_assets_trading_account_id', 'assets', ['trading_account_id'],
    )

    # 3) 기존 cash uniqueness drop, source별 분리된 인덱스로 교체
    op.drop_index('uq_asset_cash_per_currency', table_name='assets')

    op.create_index(
        'uq_asset_manual_cash_per_currency',
        'assets',
        ['user_id', 'currency'],
        unique=True,
        postgresql_where=text(
            "type = 'cash' AND status = 'active' AND source = 'manual'"
        ),
    )
    op.create_index(
        'uq_asset_kis_cash_per_account_currency',
        'assets',
        ['user_id', 'trading_account_id', 'currency'],
        unique=True,
        postgresql_where=text(
            "type = 'cash' AND status = 'active' AND source = 'kis'"
        ),
    )
    op.create_index(
        'uq_asset_kis_holding_per_account_ticker',
        'assets',
        ['user_id', 'trading_account_id', 'external_ticker'],
        unique=True,
        postgresql_where=text(
            "source = 'kis' AND status = 'active' AND external_ticker IS NOT NULL"
        ),
    )


def downgrade() -> None:
    # 1) 새 인덱스 drop, 기존 인덱스 복구
    op.drop_index('uq_asset_kis_holding_per_account_ticker', table_name='assets')
    op.drop_index('uq_asset_kis_cash_per_account_currency', table_name='assets')
    op.drop_index('uq_asset_manual_cash_per_currency', table_name='assets')

    op.create_index(
        'uq_asset_cash_per_currency',
        'assets',
        ['user_id', 'status', 'currency'],
        unique=True,
        postgresql_where=text("type = 'cash'"),
    )

    # 2) 컬럼 drop
    op.drop_index('ix_assets_trading_account_id', table_name='assets')
    op.drop_column('assets', 'last_synced_at')
    op.drop_column('assets', 'external_ticker')
    op.drop_column('assets', 'trading_account_id')
    op.drop_column('assets', 'source')

    # 3) enum 타입 drop
    sa.Enum(name='assetsource').drop(op.get_bind(), checkfirst=True)
