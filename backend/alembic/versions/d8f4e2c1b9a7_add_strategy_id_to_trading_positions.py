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

    # 2. 백필: 각 포지션을 해당 계좌의 가장 오래된 active 전략에 귀속.
    #    active 전략이 없으면 비활성 전략 중 가장 오래된 것으로 폴백.
    #    그래도 없으면 (계좌에 전략이 0개) 해당 포지션은 격리할 대상이 없으므로 삭제.
    conn = op.get_bind()

    positions = conn.execute(
        sa.text("SELECT id, account_id FROM trading_positions WHERE strategy_id IS NULL")
    ).fetchall()

    for pos_id, acc_id in positions:
        sid_row = conn.execute(
            sa.text(
                "SELECT id FROM trading_strategies "
                "WHERE account_id = :acc_id "
                "ORDER BY is_active DESC, created_at ASC "
                "LIMIT 1"
            ),
            {"acc_id": acc_id},
        ).fetchone()

        if sid_row is None:
            # 귀속할 전략이 없는 고아 포지션 → 삭제 (Phase 3 모델상 의미 없음)
            conn.execute(
                sa.text("DELETE FROM trading_positions WHERE id = :pid"),
                {"pid": pos_id},
            )
            continue

        conn.execute(
            sa.text(
                "UPDATE trading_positions SET strategy_id = :sid WHERE id = :pid"
            ),
            {"sid": sid_row[0], "pid": pos_id},
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
