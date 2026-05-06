"""oneshot advisory phase1: analysis runs/items + advisory positions

Revision ID: o0m2n3o4i5j6
Revises: n9k1l2m3h4i5
Create Date: 2026-05-06

원클릭 분석·매매 (Advisory) Phase 1:
- analysis_runs: 1회 실행 단위 (mode/budget/status/expires_at, summary_json)
- analysis_run_items: 종목별 분석 결과 + 사용자 결정 + 주문 연결
- advisory_positions: 자동매매 TradingPosition과 분리된 수동 보유분
- trading_orders.analysis_run_item_id: 발주 출처 추적용 nullable FK
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "o0m2n3o4i5j6"
down_revision: Union[str, Sequence[str], None] = "n9k1l2m3h4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum value lists (Postgres native enums — 기존 trading_mode 재사용)
_RUN_STATUS = ("pending", "analyzing", "ready", "executing", "done", "failed")
_ITEM_SOURCE = ("holding", "auto_pick")
_ITEM_ACTION = ("buy", "sell", "hold")
_ITEM_DECISION = ("pending", "approved", "skipped", "rejected")


def upgrade() -> None:
    run_status = postgresql.ENUM(
        *_RUN_STATUS, name="analysis_run_status", create_type=False,
    )
    item_source = postgresql.ENUM(
        *_ITEM_SOURCE, name="analysis_item_source", create_type=False,
    )
    item_action = postgresql.ENUM(
        *_ITEM_ACTION, name="analysis_item_action", create_type=False,
    )
    item_decision = postgresql.ENUM(
        *_ITEM_DECISION, name="analysis_item_decision", create_type=False,
    )

    bind = op.get_bind()
    run_status.create(bind, checkfirst=True)
    item_source.create(bind, checkfirst=True)
    item_action.create(bind, checkfirst=True)
    item_decision.create(bind, checkfirst=True)

    # 기존에 만들어진 tradingmode enum 을 재사용 (TradingAccount.mode)
    trading_mode = postgresql.ENUM(
        "paper", "live", name="tradingmode", create_type=False,
    )

    op.create_table(
        "analysis_runs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "account_id", UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", trading_mode, nullable=False),
        sa.Column(
            "status", run_status,
            server_default=sa.text("'pending'::analysis_run_status"),
            nullable=False,
        ),
        sa.Column("budget_krw", sa.Text(), nullable=False),
        sa.Column(
            "candidate_pool_options", JSONB(),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_analysis_runs_user_started",
        "analysis_runs", ["user_id", "started_at"],
    )
    op.create_index(
        "ix_analysis_runs_user_id", "analysis_runs", ["user_id"],
    )

    op.create_table(
        "analysis_run_items",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id", UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column(
            "ticker_name", sa.String(length=200),
            server_default="", nullable=False,
        ),
        sa.Column("source", item_source, nullable=False),
        sa.Column("action", item_action, nullable=False),
        sa.Column(
            "confidence", sa.Integer(),
            server_default="0", nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ref_price", sa.Text(), nullable=True),
        sa.Column("suggested_qty", sa.Text(), nullable=True),
        sa.Column(
            "decision", item_decision,
            server_default=sa.text("'pending'::analysis_item_decision"),
            nullable=False,
        ),
        # order_id는 trading_orders가 이미 존재하므로 즉시 FK 부여 가능
        sa.Column(
            "order_id", UUID(as_uuid=True),
            sa.ForeignKey("trading_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "run_id", "ticker", name="uq_analysis_run_item_run_ticker",
        ),
    )
    op.create_index(
        "ix_analysis_run_items_run", "analysis_run_items", ["run_id"],
    )

    op.create_table(
        "advisory_positions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "account_id", UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column(
            "ticker_name", sa.String(length=200),
            server_default="", nullable=False,
        ),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("avg_buy_price", sa.Text(), nullable=False),
        sa.Column("current_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("unrealized_pnl", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "account_id", "ticker", name="uq_advisory_position_account_ticker",
        ),
    )
    op.create_index(
        "ix_advisory_positions_user_id", "advisory_positions", ["user_id"],
    )

    # trading_orders 에 출처 추적 FK 추가 (자동매매면 NULL)
    op.add_column(
        "trading_orders",
        sa.Column(
            "analysis_run_item_id", UUID(as_uuid=True), nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_trading_orders_analysis_run_item",
        source_table="trading_orders",
        referent_table="analysis_run_items",
        local_cols=["analysis_run_item_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_trading_orders_analysis_run_item",
        "trading_orders", type_="foreignkey",
    )
    op.drop_column("trading_orders", "analysis_run_item_id")

    op.drop_index(
        "ix_advisory_positions_user_id", table_name="advisory_positions",
    )
    op.drop_table("advisory_positions")

    op.drop_index(
        "ix_analysis_run_items_run", table_name="analysis_run_items",
    )
    op.drop_table("analysis_run_items")

    op.drop_index(
        "ix_analysis_runs_user_id", table_name="analysis_runs",
    )
    op.drop_index(
        "ix_analysis_runs_user_started", table_name="analysis_runs",
    )
    op.drop_table("analysis_runs")

    bind = op.get_bind()
    postgresql.ENUM(name="analysis_item_decision").drop(bind, checkfirst=True)
    postgresql.ENUM(name="analysis_item_action").drop(bind, checkfirst=True)
    postgresql.ENUM(name="analysis_item_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="analysis_run_status").drop(bind, checkfirst=True)
