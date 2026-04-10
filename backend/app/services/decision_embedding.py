"""LLM 어드바이저 — 모듈 D: RAG 유사 케이스 회상

과거 의사결정을 벡터화하고 현재 상황과 유사한 케이스를 검색해
LLM 프롬프트에 주입한다. 모듈 B(최근 20건 단기 기억)를 보완하는
장기 기억 장치.

임베딩 모델: intfloat/multilingual-e5-small (384차원, 로컬 실행).
벡터 저장소: pgvector (PostgreSQL 확장).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trading import DecisionEmbedding, TradingDecision

logger = logging.getLogger(__name__)

# 모델 싱글턴 — lazy init (첫 호출 시 로드, 이후 재사용)
_model = None


def _get_embedding_model():
    """sentence-transformers 모델을 싱글턴으로 로드."""
    global _model
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer

    cache_folder = settings.embedding_model_cache_dir or None
    _model = SentenceTransformer(
        settings.embedding_model_name,
        cache_folder=cache_folder,
    )
    logger.info(
        "Embedding model loaded: %s (dim=%d)",
        settings.embedding_model_name,
        _model.get_sentence_embedding_dimension(),
    )
    return _model


def _encode_text(text_input: str) -> list[float]:
    """텍스트를 벡터로 변환."""
    model = _get_embedding_model()
    embedding = model.encode(text_input, normalize_embeddings=True)
    return embedding.tolist()


def _summarize_indicators(indicators: dict[str, Any] | None) -> str:
    """used_indicators를 프롬프트 친화적 문자열로 요약."""
    if not indicators:
        return ""
    parts = []
    for k, v in indicators.items():
        if isinstance(v, float):
            parts.append(f"{k}={v:.1f}")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)


def build_context_text(
    ticker: str,
    ticker_name: str,
    action: str,
    confidence: int,
    reason: str,
    market_regime: str | None = None,
    used_indicators: dict[str, Any] | None = None,
) -> str:
    """임베딩할 컨텍스트 텍스트를 구성.

    e5 모델은 "query: " 접두사를 붙여야 검색 성능이 최적이다.
    """
    regime_part = f" regime={market_regime}" if market_regime else ""
    indicator_part = f" {_summarize_indicators(used_indicators)}" if used_indicators else ""
    reason_short = reason[:200] if reason else ""

    return (
        f"query: {ticker_name or ticker} ({ticker}){regime_part}"
        f"{indicator_part} {action} conf={confidence} {reason_short}"
    ).strip()


def build_context_text_from_decision(decision: TradingDecision) -> str:
    """TradingDecision 행에서 컨텍스트 텍스트를 구성."""
    return build_context_text(
        ticker=decision.ticker,
        ticker_name="",
        action=decision.action,
        confidence=decision.confidence,
        reason=decision.reason or "",
        market_regime=decision.market_regime,
        used_indicators=decision.used_indicators,
    )


async def embed_decision(
    db: AsyncSession,
    decision_id: UUID,
) -> DecisionEmbedding | None:
    """TradingDecision에 대한 임베딩을 생성하고 DB에 저장.

    이미 임베딩이 존재하면 스킵하고 기존 행을 반환한다.
    """
    # 중복 체크
    existing = (
        await db.execute(
            select(DecisionEmbedding).where(
                DecisionEmbedding.decision_id == decision_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    decision = await db.get(TradingDecision, decision_id)
    if decision is None:
        logger.warning("embed_decision: decision not found: %s", decision_id)
        return None

    context = build_context_text_from_decision(decision)
    vector = _encode_text(context)

    row = DecisionEmbedding(
        decision_id=decision_id,
        embedding=vector,
        context_text=context,
    )
    db.add(row)
    return row


@dataclass
class SimilarCase:
    """유사 케이스 검색 결과."""

    decision_id: UUID
    ticker: str
    action: str
    confidence: int
    reason: str
    executed: bool
    realized_pnl: str | None
    holding_days: int | None
    market_regime: str | None
    similarity: float


async def search_similar_cases(
    db: AsyncSession,
    context_text: str,
    strategy_id: UUID,
    top_k: int | None = None,
    min_similarity: float | None = None,
    exclude_decision_id: UUID | None = None,
) -> list[SimilarCase]:
    """현재 상황과 유사한 과거 의사결정을 검색.

    pgvector의 코사인 거리(<=>)를 사용한다.
    코사인 유사도 = 1 - 코사인 거리.
    """
    if top_k is None:
        top_k = settings.rag_top_k
    if min_similarity is None:
        min_similarity = settings.rag_min_similarity

    query_vector = _encode_text(context_text)

    # pgvector 코사인 거리 연산자: <=>
    # similarity = 1 - distance
    sql = text("""
        SELECT
            de.decision_id,
            td.ticker,
            td.action,
            td.confidence,
            td.reason,
            td.executed,
            td.realized_pnl,
            td.holding_days,
            td.market_regime,
            1 - (de.embedding <=> :query_vec) AS similarity
        FROM decision_embeddings de
        JOIN trading_decisions td ON td.id = de.decision_id
        WHERE td.strategy_id = :strategy_id
            AND (:exclude_id IS NULL OR de.decision_id != :exclude_id)
            AND 1 - (de.embedding <=> :query_vec) >= :min_sim
        ORDER BY de.embedding <=> :query_vec
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
            "query_vec": str(query_vector),
            "strategy_id": str(strategy_id),
            "exclude_id": str(exclude_decision_id) if exclude_decision_id else None,
            "top_k": top_k,
            "min_sim": min_similarity,
        },
    )
    rows = result.fetchall()

    return [
        SimilarCase(
            decision_id=row.decision_id,
            ticker=row.ticker,
            action=row.action,
            confidence=row.confidence,
            reason=row.reason,
            executed=row.executed,
            realized_pnl=row.realized_pnl,
            holding_days=row.holding_days,
            market_regime=row.market_regime,
            similarity=float(row.similarity),
        )
        for row in rows
    ]


def format_similar_cases_for_prompt(cases: list[SimilarCase]) -> str | None:
    """유사 케이스를 LLM 프롬프트에 주입할 텍스트로 포맷.

    결과가 없으면 None 반환 (프롬프트에 섹션 생략).
    """
    if not cases:
        return None

    # 통계 집계
    executed_cases = [c for c in cases if c.executed]
    has_pnl = [c for c in executed_cases if c.realized_pnl is not None]
    win_count = 0
    loss_count = 0
    total_pnl = 0.0
    for c in has_pnl:
        try:
            pnl = float(c.realized_pnl)
            total_pnl += pnl
            if pnl > 0:
                win_count += 1
            else:
                loss_count += 1
        except (ValueError, TypeError):
            continue

    lines = []

    # 요약 통계
    if has_pnl:
        avg_pnl = total_pnl / len(has_pnl)
        lines.append(
            f"유사 사례 {len(cases)}건 중 결과 확인된 {len(has_pnl)}건: "
            f"{win_count}승 {loss_count}패, 평균 PnL {avg_pnl:+,.0f}원"
        )
    else:
        lines.append(f"유사 사례 {len(cases)}건 (아직 결과 미확정)")

    # 개별 케이스
    for i, c in enumerate(cases, 1):
        exec_tag = "발주" if c.executed else "미발주"
        pnl_tag = ""
        if c.realized_pnl is not None:
            try:
                pnl_tag = f" PnL={float(c.realized_pnl):+,.0f}원"
            except (ValueError, TypeError):
                pass
        holding_tag = f" {c.holding_days}일보유" if c.holding_days else ""
        regime_tag = f" [{c.market_regime}]" if c.market_regime else ""

        lines.append(
            f"{i}. {c.ticker} {c.action} (conf={c.confidence}) "
            f"유사도={c.similarity:.2f}{regime_tag} "
            f"{exec_tag}{pnl_tag}{holding_tag}"
        )
        if c.reason:
            lines.append(f"   사유: {c.reason[:100]}")

    return "\n".join(lines)


async def backfill_embeddings(
    db: AsyncSession,
    strategy_id: UUID,
    batch_size: int = 50,
) -> int:
    """임베딩이 없는 기존 TradingDecision을 일괄 임베딩.

    최초 배포 시 또는 모델 교체 시 1회 실행용.
    반환: 생성된 임베딩 수.
    """
    stmt = (
        select(TradingDecision)
        .outerjoin(
            DecisionEmbedding,
            DecisionEmbedding.decision_id == TradingDecision.id,
        )
        .where(
            TradingDecision.strategy_id == strategy_id,
            DecisionEmbedding.id.is_(None),
        )
        .order_by(TradingDecision.created_at)
        .limit(batch_size)
    )
    decisions = (await db.execute(stmt)).scalars().all()

    count = 0
    for decision in decisions:
        context = build_context_text_from_decision(decision)
        vector = _encode_text(context)
        row = DecisionEmbedding(
            decision_id=decision.id,
            embedding=vector,
            context_text=context,
        )
        db.add(row)
        count += 1

    if count > 0:
        logger.info(
            "Backfilled %d embeddings for strategy %s", count, strategy_id,
        )

    return count
