"""add initial_capital and realized_pnl to trading_strategies (Phase 2)

Revision ID: a7c2f1d9b3e8
Revises: 335dfd3e456b
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c2f1d9b3e8"
down_revision: Union[str, None] = "335dfd3e456b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 다중 전략 단일 계좌 자본 관리 — Phase 2
    # 두 컬럼 모두 AES-256 암호화 문자열로 저장 (Text)
    op.add_column(
        "trading_strategies",
        sa.Column("initial_capital", sa.Text(), nullable=True),
    )
    op.add_column(
        "trading_strategies",
        sa.Column("realized_pnl", sa.Text(), nullable=True),
    )

    # 백필: 기존 전략은 NULL → 0원으로 해석되어 매수가 즉시 차단되므로
    # 같은 계좌의 활성 전략 수로 계좌 initial_capital을 등분해 할당한다.
    # 암호화 값이라 SQL로 직접 산술이 불가능 → 앱 crypto_service를 호출.
    from decimal import Decimal

    from app.services.crypto_service import decrypt_decimal, encrypt_decimal

    conn = op.get_bind()

    accounts = conn.execute(
        sa.text(
            "SELECT id, initial_capital FROM trading_accounts WHERE is_active = TRUE"
        )
    ).fetchall()

    for acc_id, enc_capital in accounts:
        if not enc_capital:
            continue
        try:
            total = decrypt_decimal(enc_capital)
        except Exception:
            # 키 불일치 등으로 복호화 실패하면 건너뜀 (운영자가 수동 백필)
            continue

        strategies = conn.execute(
            sa.text(
                "SELECT id FROM trading_strategies "
                "WHERE account_id = :acc_id AND initial_capital IS NULL"
            ),
            {"acc_id": acc_id},
        ).fetchall()
        if not strategies:
            continue

        per_strategy = total / Decimal(len(strategies))
        enc_per = encrypt_decimal(per_strategy)
        enc_zero = encrypt_decimal(Decimal("0"))

        for (sid,) in strategies:
            conn.execute(
                sa.text(
                    "UPDATE trading_strategies "
                    "SET initial_capital = :cap, realized_pnl = :pnl "
                    "WHERE id = :sid"
                ),
                {"cap": enc_per, "pnl": enc_zero, "sid": sid},
            )


def downgrade() -> None:
    op.drop_column("trading_strategies", "realized_pnl")
    op.drop_column("trading_strategies", "initial_capital")
