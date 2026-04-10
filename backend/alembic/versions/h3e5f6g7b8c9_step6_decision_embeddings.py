"""step6 RAG — pgvector extension + decision_embeddings table

Revision ID: h3e5f6g7b8c9
Revises: g2d4e5f6a7b8
Create Date: 2026-04-10

Stage 3 Step 6 (모듈 D):
- pgvector 확장 활성화
- decision_embeddings: TradingDecision 벡터 임베딩 (384차원, multilingual-e5-small)
- HNSW 인덱스 (코사인 유사도 검색)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "h3e5f6g7b8c9"
down_revision: Union[str, Sequence[str], None] = "g2d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. pgvector 확장 활성화 (Supabase/Neon은 기본 제공)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. decision_embeddings 테이블
    op.create_table(
        "decision_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "decision_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_decisions.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("context_text", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )

    # 3. HNSW 인덱스 — 코사인 유사도 (소규모~중규모 데이터에서 잘 동작)
    op.execute(
        "CREATE INDEX ix_decision_embeddings_hnsw "
        "ON decision_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_decision_embeddings_hnsw")
    op.drop_table("decision_embeddings")
    # NOTE: pgvector 확장은 다른 테이블에서 사용할 수 있으므로 DROP하지 않는다.
