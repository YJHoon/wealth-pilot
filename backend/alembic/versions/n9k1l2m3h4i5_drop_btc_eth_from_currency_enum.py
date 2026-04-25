"""drop BTC/ETH from currency enum

코인 자산은 type='crypto'에 ticker로 식별하고, 평가 통화는 USD/KRW만 사용한다.
Currency enum은 법정통화로 한정한다.

기존 BTC/ETH 통화 데이터는 USD로 마이그레이션 (코인 시세 fetcher가 USD 기준).

Revision ID: n9k1l2m3h4i5
Revises: m8j0k1l2g3h4
Create Date: 2026-04-25
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'n9k1l2m3h4i5'
down_revision: Union[str, None] = 'm8j0k1l2g3h4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 기존 BTC/ETH 데이터를 USD로 마이그레이션
    op.execute("UPDATE assets SET currency = 'USD' WHERE currency IN ('BTC', 'ETH')")

    # 2) enum 타입 재생성 (PostgreSQL은 enum 값 직접 제거 불가)
    op.execute("ALTER TYPE currency RENAME TO currency_old")
    op.execute("CREATE TYPE currency AS ENUM ('KRW', 'USD', 'EUR', 'JPY')")
    op.execute("ALTER TABLE assets ALTER COLUMN currency DROP DEFAULT")
    op.execute(
        "ALTER TABLE assets ALTER COLUMN currency "
        "TYPE currency USING currency::text::currency"
    )
    op.execute("ALTER TABLE assets ALTER COLUMN currency SET DEFAULT 'KRW'::currency")
    op.execute("DROP TYPE currency_old")


def downgrade() -> None:
    op.execute("ALTER TYPE currency RENAME TO currency_new")
    op.execute("CREATE TYPE currency AS ENUM ('KRW', 'USD', 'EUR', 'JPY', 'BTC', 'ETH')")
    op.execute("ALTER TABLE assets ALTER COLUMN currency DROP DEFAULT")
    op.execute(
        "ALTER TABLE assets ALTER COLUMN currency "
        "TYPE currency USING currency::text::currency"
    )
    op.execute("ALTER TABLE assets ALTER COLUMN currency SET DEFAULT 'KRW'::currency")
    op.execute("DROP TYPE currency_new")
