"""보안 수정 v3: ETH 통화 추가, asset_snapshots 유니크 제약, pending_totp_secret 컬럼

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. currency ENUM에 ETH 추가 (프론트엔드 타입과 동기화)
    op.execute(sa.text("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ETH'"))

    # 2. asset_snapshots (user_id, snapshot_date) 유니크 제약 추가 전 중복 데이터 검증
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT user_id, snapshot_date, COUNT(*) AS cnt "
            "FROM asset_snapshots "
            "GROUP BY user_id, snapshot_date "
            "HAVING COUNT(*) > 1"
        )
    )
    duplicates = result.fetchall()
    if duplicates:
        raise RuntimeError(
            f"asset_snapshots에 중복 데이터가 있어 UNIQUE 제약을 적용할 수 없습니다. "
            f"중복 행: {duplicates}"
        )

    op.create_unique_constraint(
        "uq_asset_snapshots_user_id_snapshot_date",
        "asset_snapshots",
        ["user_id", "snapshot_date"],
    )

    # 3. users.pending_totp_secret 추가 (2FA 재설정 시 기존 시크릿 보호)
    #    재설정 중에는 pending에 저장, verify 성공 후 totp_secret으로 교체
    op.add_column(
        "users",
        sa.Column("pending_totp_secret", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_totp_secret")
    op.drop_constraint("uq_asset_snapshots_user_id_snapshot_date", "asset_snapshots")
    # PostgreSQL은 ENUM 값 제거를 지원하지 않으므로 ETH 완전 롤백 불가
    raise NotImplementedError(
        "PostgreSQL은 ENUM 값 제거를 지원하지 않습니다. "
        "'ETH' 값을 포함한 rows를 수동으로 처리한 후 ENUM 타입을 재생성해야 합니다."
    )
