"""자산 관련 Pydantic v2 스키마"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.asset import AssetStatus, AssetType, Currency


class AssetCreateRequest(BaseModel):
    type: AssetType
    name: str = Field(..., min_length=1, max_length=200)
    ticker: str | None = Field(None, max_length=20)
    currency: Currency = Currency.KRW
    quantity: Decimal = Field(..., gt=0)
    purchase_price: Decimal = Field(..., gt=0)
    current_price: Decimal | None = Field(None, ge=0)
    group_id: uuid.UUID | None = None
    metadata_json: dict | None = None


class AssetUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    ticker: str | None = Field(None, max_length=20)
    currency: Currency | None = None
    quantity: Decimal | None = Field(None, gt=0)
    purchase_price: Decimal | None = Field(None, gt=0)
    current_price: Decimal | None = Field(None, ge=0)
    group_id: uuid.UUID | None = None
    metadata_json: dict | None = None


class AssetSellRequest(BaseModel):
    sold_price: Decimal = Field(..., gt=0)
    sold_at: datetime | None = None


class AssetResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    group_id: uuid.UUID | None
    type: AssetType
    status: AssetStatus
    name: str
    ticker: str | None
    currency: Currency
    quantity: Decimal
    purchase_price: Decimal
    current_price: Decimal | None
    metadata_json: dict | None
    sold_at: datetime | None
    sold_price: Decimal | None
    realized_pnl: Decimal | None
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    assets: list[AssetResponse]
    total: int
