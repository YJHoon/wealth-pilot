"""자산 스키마 — Pydantic v2"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.asset import AssetSource, AssetStatus, AssetType, Currency
from app.services.crypto_service import decrypt_decimal, decrypt_decimal_optional

if TYPE_CHECKING:
    from app.models.asset import Asset as AssetModel


class AssetCreate(BaseModel):
    type: AssetType
    name: str = Field(max_length=200)
    ticker: str | None = Field(default=None, max_length=20)
    currency: Currency = Currency.KRW
    quantity: Decimal = Field(gt=0)
    purchase_price: Decimal = Field(ge=0)
    current_price: Decimal | None = Field(default=None, ge=0)
    group_id: UUID | None = None
    metadata_json: dict | None = None


class AssetUpdate(BaseModel):
    type: AssetType | None = None
    name: str | None = Field(default=None, max_length=200)
    ticker: str | None = Field(default=None, max_length=20)
    currency: Currency | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    purchase_price: Decimal | None = Field(default=None, ge=0)
    current_price: Decimal | None = Field(default=None, ge=0)
    group_id: UUID | None = None
    metadata_json: dict | None = None


class SellRequest(BaseModel):
    sold_price: Decimal = Field(ge=0)


class AssetResponse(BaseModel):
    id: UUID
    group_id: UUID | None
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
    source: AssetSource
    trading_account_id: UUID | None
    external_ticker: str | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    assets: list[AssetResponse]
    total: int


class HoldingBreakdownItemResponse(BaseModel):
    """종목별 보유 분해 — 전략 N주 + 수동 M주 + KIS 실잔고 + 정합성 차이."""

    account_id: UUID
    ticker: str
    ticker_name: str
    strategy_qty: Decimal
    advisory_qty: Decimal
    kis_qty: Decimal | None
    mismatch_qty: Decimal
    has_mismatch: bool


class HoldingBreakdownResponse(BaseModel):
    items: list[HoldingBreakdownItemResponse]
    mismatches: list[str]


def asset_to_response(asset: AssetModel) -> AssetResponse:
    """Asset 모델 → AssetResponse 변환 (암호화 필드 복호화)."""
    return AssetResponse(
        id=asset.id,
        group_id=asset.group_id,
        type=asset.type,
        status=asset.status,
        name=asset.name,
        ticker=asset.ticker,
        currency=asset.currency,
        quantity=decrypt_decimal(asset.quantity),
        purchase_price=decrypt_decimal(asset.purchase_price),
        current_price=asset.current_price,
        metadata_json=asset.metadata_json,
        sold_at=asset.sold_at,
        sold_price=decrypt_decimal_optional(asset.sold_price),
        realized_pnl=decrypt_decimal_optional(asset.realized_pnl),
        source=asset.source,
        trading_account_id=asset.trading_account_id,
        external_ticker=asset.external_ticker,
        last_synced_at=asset.last_synced_at,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )
