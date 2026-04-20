"""시장 공통 라우터 — 종목 검색 등.

- GET /api/market/search?q=... : KOSPI/KOSDAQ 종목을 이름 또는 코드로 검색.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies.auth import get_current_active_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.market import StockSearchItem, StockSearchResponse
from app.services.stock_master import ensure_loaded, search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["시장"])


@router.get("/search", response_model=StockSearchResponse)
@limiter.limit("60/minute")
async def search_stocks(
    request: Request,
    q: str = Query(min_length=1, max_length=40, description="종목명 또는 코드"),
    limit: int = Query(default=20, ge=1, le=50),
    _: User = Depends(get_current_active_user),
):
    try:
        await ensure_loaded()
    except Exception as exc:
        logger.exception("stock master load failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="종목 마스터 데이터를 불러올 수 없습니다",
        ) from exc

    hits = search(q, limit=limit)
    return StockSearchResponse(
        query=q,
        results=[
            StockSearchItem(ticker=h.ticker, name=h.name, market=h.market)
            for h in hits
        ],
    )
