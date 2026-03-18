"""시세 조회 API 라우터"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.schemas.price import (
    ExchangeRateResponse,
    PriceModeResponse,
    PriceModeUpdate,
    PriceResponse,
    RefreshResponse,
)
from app.services.price_service import price_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prices", tags=["시세"])


@router.get("/stock/{ticker}", response_model=PriceResponse)
async def get_stock_price(
    request: Request,
    ticker: str,
    user: User = Depends(get_current_active_user),
):
    """주식 시세 조회."""
    try:
        cached = await price_service.fetch_stock_price(ticker)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"주식 시세를 조회할 수 없습니다: {ticker}",
        ) from exc
    return PriceResponse(
        ticker=ticker,
        price=cached.price,
        currency=cached.currency,
        fetched_at=cached.fetched_at,
        is_stale=cached.is_stale,
        anomaly_flag=cached.anomaly_flag,
    )


@router.get("/crypto/{symbol}", response_model=PriceResponse)
async def get_crypto_price(
    request: Request,
    symbol: str,
    user: User = Depends(get_current_active_user),
):
    """암호화폐 시세 조회."""
    try:
        cached = await price_service.fetch_crypto_price(symbol)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"암호화폐 시세를 조회할 수 없습니다: {symbol}",
        ) from exc
    return PriceResponse(
        ticker=symbol,
        price=cached.price,
        currency=cached.currency,
        fetched_at=cached.fetched_at,
        is_stale=cached.is_stale,
        anomaly_flag=cached.anomaly_flag,
    )


@router.get("/exchange-rate", response_model=ExchangeRateResponse)
async def get_exchange_rate(
    request: Request,
    from_currency: str = Query(alias="from"),
    to_currency: str = Query(alias="to"),
    user: User = Depends(get_current_active_user),
):
    """환율 조회."""
    try:
        cached = await price_service.fetch_exchange_rate(
            from_currency, to_currency,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"환율을 조회할 수 없습니다: {from_currency} → {to_currency}",
        ) from exc
    return ExchangeRateResponse(
        from_currency=from_currency,
        to_currency=to_currency,
        rate=cached.price,
        fetched_at=cached.fetched_at,
        source="exchangerate-api",
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_all_prices(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목 전체 시세 일괄 갱신."""
    success_count, fail_count, details = await price_service.refresh_all_prices(
        db, user.id,
    )
    return RefreshResponse(
        success_count=success_count,
        fail_count=fail_count,
        refreshed_at=datetime.now(timezone.utc),
        details=details,
    )


@router.get("/mode", response_model=PriceModeResponse)
async def get_price_mode(
    request: Request,
    user: User = Depends(get_current_active_user),
):
    """현재 시세 모드 조회 (유저별)."""
    return PriceModeResponse(current_mode=price_service.get_mode(user.id))


@router.put("/mode", response_model=PriceModeResponse)
async def update_price_mode(
    request: Request,
    body: PriceModeUpdate,
    user: User = Depends(get_current_active_user),
):
    """시세 모드 변경 (유저별)."""
    price_service.set_mode(body.mode, user.id)
    logger.info("Price mode changed to %s by user %s", body.mode, user.id)
    return PriceModeResponse(current_mode=price_service.get_mode(user.id))
