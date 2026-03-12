"""sessions 테이블에 refresh_token_hash 컬럼 추가 (Refresh Token 재사용 방지)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-03-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("refresh_token_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "refresh_token_hash")
