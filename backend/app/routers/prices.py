"""시세 조회 API 라우터"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.exchange_rate import ExchangeRate
from app.models.user import User
from app.schemas.price import (
    ExchangeRateInfo,
    ExchangeRateResponse,
    PriceModeResponse,
    PriceModeUpdate,
    PriceResponse,
    RefreshResponse,
)
from app.services.price_service import EXCHANGE_RATE_SOURCE, price_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prices", tags=["시세"])


@router.get("/stock/{ticker}", response_model=PriceResponse)
async def get_stock_price(
    ticker: str,
    user: User = Depends(get_current_active_user),
):
    """주식 시세 조회."""
    try:
        cached = await price_service.fetch_stock_price(ticker, user_id=user.id)
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
    symbol: str,
    user: User = Depends(get_current_active_user),
):
    """암호화폐 시세 조회."""
    try:
        cached = await price_service.fetch_crypto_price(symbol, user_id=user.id)
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
    from_currency: str = Query(alias="from"),
    to_currency: str = Query(alias="to"),
    user: User = Depends(get_current_active_user),
):
    """환율 조회."""
    try:
        cached = await price_service.fetch_exchange_rate(
            from_currency, to_currency, user_id=user.id,
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
        source=EXCHANGE_RATE_SOURCE,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_all_prices(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목 전체 시세 일괄 갱신."""
    success_count, fail_count, details, exchange_rates = (
        await price_service.refresh_all_prices(db, user.id)
    )
    return RefreshResponse(
        success_count=success_count,
        fail_count=fail_count,
        refreshed_at=datetime.now(timezone.utc),
        details=details,
        exchange_rates=exchange_rates,
    )


@router.get("/exchange-rates", response_model=list[ExchangeRateInfo])
async def get_all_exchange_rates(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """DB에 저장된 모든 환율 조회."""
    result = await db.execute(select(ExchangeRate))
    rows = result.scalars().all()
    return [
        ExchangeRateInfo(
            from_currency=r.from_currency,
            to_currency=r.to_currency,
            rate=r.rate,
            fetched_at=r.fetched_at,
            source=r.source,
        )
        for r in rows
    ]


@router.get("/mode", response_model=PriceModeResponse)
async def get_price_mode(
    user: User = Depends(get_current_active_user),
):
    """현재 시세 모드 조회 (유저별)."""
    return PriceModeResponse(current_mode=price_service.get_mode(user.id))


@router.put("/mode", response_model=PriceModeResponse)
async def update_price_mode(
    body: PriceModeUpdate,
    user: User = Depends(get_current_active_user),
):
    """시세 모드 변경 (유저별)."""
    price_service.set_mode(body.mode, user.id)
    logger.info("Price mode changed to %s by user %s", body.mode, user.id)
    return PriceModeResponse(current_mode=price_service.get_mode(user.id))
