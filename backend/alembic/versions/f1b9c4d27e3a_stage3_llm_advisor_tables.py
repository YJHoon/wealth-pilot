"""stage3 llm advisor — strategytype enum + trading_decisions + adaptive_rules

Revision ID: f1b9c4d27e3a
Revises: e5c3a1f8b6d2
Create Date: 2026-04-09

Stage 3 Step 1:
- StrategyType enum에 'llm_advisor' 추가 (paper 모드 전용, live 차단은 코드)
- trading_decisions: LLM 의사결정 로그 (모듈 B/C 학습 데이터)
- adaptive_rules: 모듈 C가 생성하는 자동 진화 규칙 (스키마만 선반영)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1b9c4d27e3a"
down_revision: Union[str, Sequence[str], None] = "e5c3a1f8b6d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. enum 값 추가 — Postgres는 ALTER TYPE ... ADD VALUE를 트랜잭션 외부에서 실행해야 한다.
    #    Alembic은 기본적으로 마이그레이션을 트랜잭션으로 감싸므로 commit 후 실행.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE strategytype ADD VALUE IF NOT EXISTS 'llm_advisor'")

    # 2. trading_decisions
    op.create_table(
        "trading_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "strategy_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_log_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_schedule_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "order_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("suggested_quantity", sa.Text, nullable=True),
        sa.Column("suggested_amount", sa.Text, nullable=True),
        sa.Column(
            "executed", sa.Boolean,
            nullable=False, server_default=sa.false(),
        ),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("realized_pnl", sa.Text, nullable=True),
        sa.Column("holding_days", sa.Integer, nullable=True),
        sa.Column("exit_price", sa.Text, nullable=True),
        sa.Column("market_regime", sa.String(30), nullable=True),
        sa.Column("used_indicators", postgresql.JSONB, nullable=True),
        sa.Column("model", sa.String(60), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_trading_decisions_strategy_created",
        "trading_decisions",
        ["strategy_id", "created_at"],
    )
    op.create_index(
        "ix_trading_decisions_user_created",
        "trading_decisions",
        ["user_id", "created_at"],
    )

    # 3. adaptive_rules
    op.create_table(
        "adaptive_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("rule_text", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("generated_from", sa.String(100), nullable=True),
        sa.Column(
            "is_active", sa.Boolean,
            nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_adaptive_rules_strategy_active",
        "adaptive_rules",
        ["strategy_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_adaptive_rules_strategy_active", table_name="adaptive_rules")
    op.drop_table("adaptive_rules")
    op.drop_index("ix_trading_decisions_user_created", table_name="trading_decisions")
    op.drop_index(
        "ix_trading_decisions_strategy_created", table_name="trading_decisions"
    )
    op.drop_table("trading_decisions")
    # NOTE: Postgres는 enum 값 제거를 직접 지원하지 않는다. enum 롤백이 필요하면
    # 새 타입을 만들어 컬럼을 swap해야 하며, 운영 데이터 손실 위험이 있어
    # 다운그레이드에서는 의도적으로 enum 롤백을 생략한다.
