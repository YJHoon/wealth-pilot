"""관심종목 CRUD 서비스

Watchlist의 생성·조회·수정·삭제와 소유권 검증을 담당한다.
목표 매수/매도 가격은 AES-256 암호화하여 DB에 저장한다.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Watchlist
from app.schemas.analysis import (
    WatchlistCreate,
    WatchlistResponse,
    WatchlistUpdate,
    watchlist_to_response,
)
from app.services.crypto_service import encrypt_decimal_optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 도메인 예외
# ──────────────────────────────────────────────

class WatchlistNotFoundError(Exception):
    """관심종목을 찾을 수 없거나 소유권이 없음."""


class WatchlistDuplicateError(Exception):
    """동일 종목이 이미 관심종목에 등록됨."""


# ──────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────

async def list_watchlist(
    db: AsyncSession, user_id: UUID,
) -> list[WatchlistResponse]:
    """사용자의 관심종목 목록 반환 (생성일 역순)."""
    result = await db.execute(
        select(Watchlist)
        .where(Watchlist.user_id == user_id)
        .order_by(Watchlist.created_at.desc())
    )
    return [watchlist_to_response(w) for w in result.scalars().all()]


async def create_watchlist(
    db: AsyncSession, user_id: UUID, body: WatchlistCreate,
) -> WatchlistResponse:
    """관심종목 추가. 중복 시 WatchlistDuplicateError."""
    watchlist = Watchlist(
        user_id=user_id,
        ticker=body.ticker,
        market=body.market.value,
        target_buy_price=encrypt_decimal_optional(body.target_buy_price),
        target_sell_price=encrypt_decimal_optional(body.target_sell_price),
        alert_threshold_pct=body.alert_threshold_pct,
        notes=body.notes,
    )
    db.add(watchlist)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        # unique constraint(uq_watchlist_user_ticker_market) 위반만 중복 에러로 변환
        orig_msg = str(getattr(e, "orig", e)).lower()
        if "uq_watchlist_user_ticker_market" in orig_msg:
            raise WatchlistDuplicateError(
                f"이미 등록된 관심종목입니다: {body.ticker} ({body.market.value})"
            ) from None
        raise
    await db.refresh(watchlist)
    return watchlist_to_response(watchlist)


async def update_watchlist(
    db: AsyncSession, user_id: UUID, watchlist_id: UUID, body: WatchlistUpdate,
) -> WatchlistResponse:
    """관심종목 수정. 소유권 불일치 시 WatchlistNotFoundError."""
    watchlist = await _get_owned(db, user_id, watchlist_id)

    update_data = body.model_dump(exclude_unset=True)
    encrypted_fields = {"target_buy_price", "target_sell_price"}
    for key, value in update_data.items():
        if key in encrypted_fields:
            setattr(watchlist, key, encrypt_decimal_optional(value))
        else:
            setattr(watchlist, key, value)

    await db.flush()
    await db.refresh(watchlist)
    return watchlist_to_response(watchlist)


async def delete_watchlist(
    db: AsyncSession, user_id: UUID, watchlist_id: UUID,
) -> None:
    """관심종목 삭제. 소유권 불일치 시 WatchlistNotFoundError."""
    watchlist = await _get_owned(db, user_id, watchlist_id)
    await db.delete(watchlist)
    await db.flush()


# ──────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────

async def _get_owned(
    db: AsyncSession, user_id: UUID, watchlist_id: UUID,
) -> Watchlist:
    """소유권 검증된 Watchlist 반환. 없으면 WatchlistNotFoundError."""
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == user_id,
        )
    )
    watchlist = result.scalar_one_or_none()
    if watchlist is None:
        raise WatchlistNotFoundError("관심종목을 찾을 수 없습니다.")
    return watchlist
