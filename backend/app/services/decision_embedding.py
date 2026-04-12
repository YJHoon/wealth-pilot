"""LLM 어드바이저 — 모듈 D: RAG 유사 케이스 회상

과거 의사결정을 벡터화하고 현재 상황과 유사한 케이스를 검색해
LLM 프롬프트에 주입한다. 모듈 B(최근 20건 단기 기억)를 보완하는
장기 기억 장치.

임베딩 모델: intfloat/multilingual-e5-small (384차원, 로컬 실행).
벡터 저장소: pgvector (PostgreSQL 확장).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trading import DecisionEmbedding, TradingDecision
from app.services.crypto_service import decrypt_decimal

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


def _encode_text_sync(text_input: str) -> list[float]:
    """텍스트를 벡터로 변환 (동기, 내부용)."""
    model = _get_embedding_model()
    embedding = model.encode(text_input, normalize_embeddings=True)
    return embedding.tolist()


async def _encode_text(text_input: str) -> list[float]:
    """텍스트를 벡터로 변환 (비동기 — 이벤트 루프 블로킹 방지)."""
    return await asyncio.to_thread(_encode_text_sync, text_input)


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
    *,
    is_query: bool = False,
) -> str:
    """임베딩할 컨텍스트 텍스트를 구성.

    e5 모델은 저장 대상 문서에 "passage: ", 검색 쿼리에 "query: " 접두사를
    붙여야 최적 성능이 나온다.

    Args:
        is_query: True면 "query: " (검색 시), False면 "passage: " (저장 시).
    """
    prefix = "query: " if is_query else "passage: "
    regime_part = f" regime={market_regime}" if market_regime else ""
    indicator_part = f" {_summarize_indicators(used_indicators)}" if used_indicators else ""
    reason_short = reason[:200] if reason else ""

    return (
        f"{prefix}{ticker_name or ticker} ({ticker}){regime_part}"
        f"{indicator_part} {action} conf={confidence} {reason_short}"
    ).strip()


def build_context_text_from_decision(decision: TradingDecision) -> str:
    """TradingDecision 행에서 저장용 컨텍스트 텍스트를 구성 (passage 모드)."""
    return build_context_text(
        ticker=decision.ticker,
        ticker_name="",
        action=decision.action,
        confidence=decision.confidence,
        reason=decision.reason or "",
        market_regime=decision.market_regime,
        used_indicators=decision.used_indicators,
        is_query=False,
    )


async def embed_decision(
    db: AsyncSession,
    decision_id: UUID,
) -> DecisionEmbedding | None:
    """TradingDecision에 대한 임베딩을 생성하고 DB에 저장.

    동시 호출 시 UNIQUE 제약 위반(IntegrityError)을 잡아 기존 행을 반환한다.
    """
    decision = await db.get(TradingDecision, decision_id)
    if decision is None:
        logger.warning("embed_decision: decision not found: %s", decision_id)
        return None

    context = build_context_text_from_decision(decision)
    vector = await _encode_text(context)

    row = DecisionEmbedding(
        decision_id=decision_id,
        embedding=vector,
        context_text=context,
    )
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        return (
            await db.execute(
                select(DecisionEmbedding).where(
                    DecisionEmbedding.decision_id == decision_id
                )
            )
        ).scalar_one_or_none()
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

    query_vector = await _encode_text(context_text)

    # pgvector cosine_distance: 0 = 동일, 2 = 정반대
    # similarity = 1 - distance
    distance = DecisionEmbedding.embedding.cosine_distance(query_vector)
    max_distance = 1.0 - min_similarity  # similarity >= min_sim ↔ distance <= max_dist

    stmt = (
        select(
            DecisionEmbedding.decision_id,
            TradingDecision.ticker,
            TradingDecision.action,
            TradingDecision.confidence,
            TradingDecision.reason,
            TradingDecision.executed,
            TradingDecision.realized_pnl,
            TradingDecision.holding_days,
            TradingDecision.market_regime,
            (1 - distance).label("similarity"),
        )
        .join(TradingDecision, TradingDecision.id == DecisionEmbedding.decision_id)
        .where(
            TradingDecision.strategy_id == strategy_id,
            distance <= max_distance,
        )
        .order_by(distance)
        .limit(top_k)
    )
    if exclude_decision_id is not None:
        stmt = stmt.where(DecisionEmbedding.decision_id != exclude_decision_id)

    result = await db.execute(stmt)
    rows = result.all()

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

    # 통계 집계 — realized_pnl은 AES-256 암호화되어 있으므로 복호화 필요
    executed_cases = [c for c in cases if c.executed]
    win_count = 0
    loss_count = 0
    total_pnl = Decimal("0")
    pnl_count = 0
    # 개별 케이스 복호화 결과 캐시 (요약 + 개별 표시에서 재사용)
    _decrypted_pnl: dict[int, Decimal] = {}
    for idx, c in enumerate(executed_cases):
        if c.realized_pnl is None:
            continue
        try:
            pnl = decrypt_decimal(c.realized_pnl)
            _decrypted_pnl[id(c)] = pnl
            total_pnl += pnl
            pnl_count += 1
            if pnl > 0:
                win_count += 1
            else:
                loss_count += 1
        except Exception:
            continue

    lines = []

    # 요약 통계
    if pnl_count > 0:
        avg_pnl = total_pnl / pnl_count
        lines.append(
            f"유사 사례 {len(cases)}건 중 결과 확인된 {pnl_count}건: "
            f"{win_count}승 {loss_count}패, 평균 PnL {int(avg_pnl):+,}원"
        )
    else:
        lines.append(f"유사 사례 {len(cases)}건 (아직 결과 미확정)")

    # 개별 케이스
    for i, c in enumerate(cases, 1):
        exec_tag = "발주" if c.executed else "미발주"
        pnl_tag = ""
        if c.realized_pnl is not None:
            pnl_val = _decrypted_pnl.get(id(c))
            if pnl_val is None:
                try:
                    pnl_val = decrypt_decimal(c.realized_pnl)
                except Exception:
                    pnl_val = None
            if pnl_val is not None:
                pnl_tag = f" PnL={int(pnl_val):+,}원"
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
        vector = await _encode_text(context)
        row = DecisionEmbedding(
            decision_id=decision.id,
            embedding=vector,
            context_text=context,
        )
        db.add(row)
        try:
            async with db.begin_nested():
                await db.flush()
            count += 1
        except IntegrityError:
            pass  # savepoint 롤백으로 이 행만 스킵, 나머지는 유지

    if count > 0:
        logger.info(
            "Backfilled %d embeddings for strategy %s", count, strategy_id,
        )

    return count
