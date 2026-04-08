"""add strategy_id to trading_positions (Phase 3 - position isolation)

Revision ID: d8f4e2c1b9a7
Revises: a7c2f1d9b3e8, bb26383cd251
Create Date: 2026-04-08

다중 전략 단일 계좌 — Phase 3
- trading_positions에 strategy_id 추가 (전략별 포지션 격리)
- UNIQUE: (account_id, ticker) → (account_id, strategy_id, ticker)
- 백필: 기존 포지션을 해당 계좌의 가장 오래된 active 전략에 귀속
- 두 head(a7c2f1d9b3e8, bb26383cd251)를 머지하는 역할도 겸함
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f4e2c1b9a7"
down_revision: Union[str, Sequence[str], None] = ("a7c2f1d9b3e8", "bb26383cd251")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. nullable로 컬럼 추가
    op.add_column(
        "trading_positions",
        sa.Column("strategy_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2. 백필 (set-based, 두 statement만 실행)
    #    (a) 각 포지션을 해당 계좌의 우선 전략(active 우선, 그다음 created_at 오름차순)에 귀속
    #    (b) 귀속할 전략이 없는 고아 포지션은 삭제 (Phase 3 모델상 의미 없음)
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE trading_positions p
            SET strategy_id = (
                SELECT s.id FROM trading_strategies s
                WHERE s.account_id = p.account_id
                ORDER BY s.is_active DESC, s.created_at ASC
                LIMIT 1
            )
            WHERE p.strategy_id IS NULL
            """
        )
    )

    conn.execute(
        sa.text("DELETE FROM trading_positions WHERE strategy_id IS NULL")
    )

    # 3. NOT NULL 전환
    op.alter_column("trading_positions", "strategy_id", nullable=False)

    # 4. FK 추가 (RESTRICT — 전략 삭제 시 포지션이 남아있으면 막음)
    op.create_foreign_key(
        "fk_trading_positions_strategy_id",
        "trading_positions",
        "trading_strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 5. UNIQUE 제약 재구성: (account_id, ticker) → (account_id, strategy_id, ticker)
    op.drop_constraint(
        "uq_trading_position_account_ticker", "trading_positions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_trading_position_account_strategy_ticker",
        "trading_positions",
        ["account_id", "strategy_id", "ticker"],
    )

    # 6. 조회 최적화 인덱스
    op.create_index(
        "ix_trading_positions_strategy_id",
        "trading_positions",
        ["strategy_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trading_positions_strategy_id", table_name="trading_positions")
    op.drop_constraint(
        "uq_trading_position_account_strategy_ticker",
        "trading_positions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_trading_position_account_ticker",
        "trading_positions",
        ["account_id", "ticker"],
    )
    op.drop_constraint(
        "fk_trading_positions_strategy_id", "trading_positions", type_="foreignkey"
    )
    op.drop_column("trading_positions", "strategy_id")
