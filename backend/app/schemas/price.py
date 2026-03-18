"""시세 조회 스키마 — Pydantic v2"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class PriceMode(str, Enum):
    BATCH = "batch"         # 하루 1회, TTL 24h
    DELAYED = "delayed"     # 5~15분 주기, TTL 15min
    REALTIME = "realtime"   # 웹소켓(추후), TTL 1min


class PriceResponse(BaseModel):
    ticker: str
    price: Decimal
    currency: str
    fetched_at: datetime
    is_stale: bool = False
    anomaly_flag: bool = False


class RefreshDetail(BaseModel):
    ticker: str
    success: bool
    price: Decimal | None = None
    error: str | None = None


class RefreshResponse(BaseModel):
    success_count: int
    fail_count: int
    refreshed_at: datetime
    details: list[RefreshDetail]


class PriceModeResponse(BaseModel):
    current_mode: PriceMode


class PriceModeUpdate(BaseModel):
    mode: PriceMode


class ExchangeRateResponse(BaseModel):
    from_currency: str
    to_currency: str
    rate: Decimal
    fetched_at: datetime
    source: str
