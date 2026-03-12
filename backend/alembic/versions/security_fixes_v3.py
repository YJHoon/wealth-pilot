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

    # 2. asset_snapshots (user_id, snapshot_date) 유니크 제약 추가
    #    중복 스냅샷 삽입 방지 → 일별 집계 정확성 보장
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
    # NOTE: PostgreSQL은 ENUM 값 제거를 지원하지 않음 — ETH 롤백 불가
