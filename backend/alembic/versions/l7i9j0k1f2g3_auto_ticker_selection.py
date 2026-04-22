"""auto ticker selection: strategy columns + selection history

Revision ID: l7i9j0k1f2g3
Revises: k6h8i9j0e1f2
Create Date: 2026-04-22

자동 종목 선정:
- trading_strategies.auto_select_config: JSONB (enabled, top_n, market,
  min_volume_value, blacklist 등). 기본값은 빈 객체.
- trading_strategies.auto_selected_tickers: JSONB (tickers, generated_at,
  rule_version). NULL 허용 — 아직 갱신 안 된 전략.
- auto_ticker_selections: 선정 이력 테이블. 전략당 최신 30건 유지 cron.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "l7i9j0k1f2g3"
down_revision: Union[str, Sequence[str], None] = "k6h8i9j0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trading_strategies",
        sa.Column(
            "auto_select_config",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "trading_strategies",
        sa.Column(
            "auto_selected_tickers",
            JSONB(),
            nullable=True,
        ),
    )

    op.create_table(
        "auto_ticker_selections",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "strategy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("trading_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("selected_tickers", JSONB(), nullable=False),
        sa.Column("excluded_sample", JSONB(), nullable=True),
        sa.Column("config_snapshot", JSONB(), nullable=False),
        sa.Column("triggered_by", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_auto_ticker_selections_strategy_generated",
        "auto_ticker_selections",
        ["strategy_id", sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auto_ticker_selections_strategy_generated",
        table_name="auto_ticker_selections",
    )
    op.drop_table("auto_ticker_selections")
    op.drop_column("trading_strategies", "auto_selected_tickers")
    op.drop_column("trading_strategies", "auto_select_config")
