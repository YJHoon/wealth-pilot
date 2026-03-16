"""자산 서비스 — CRUD + 매도 비즈니스 로직"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus
from app.models.portfolio_group import PortfolioGroup
from app.schemas.asset import (
    AssetCreateRequest,
    AssetResponse,
    AssetSellRequest,
    AssetUpdateRequest,
)
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
    encrypt_decimal,
    encrypt_decimal_optional,
)

# 암호화 대상 필드
_ENCRYPTED_FIELDS = {"quantity", "purchase_price"}


async def create_asset(
    db: AsyncSession, user_id: uuid.UUID, body: AssetCreateRequest
) -> Asset:
    """자산 생성 — group_id 소유권 검증 후 금액 필드 암호화."""
    if body.group_id:
        await _verify_group_ownership(db, user_id, body.group_id)

    asset = Asset(
        user_id=user_id,
        type=body.type,
        name=body.name,
        ticker=body.ticker,
        currency=body.currency,
        quantity=encrypt_decimal(body.quantity),
        purchase_price=encrypt_decimal(body.purchase_price),
        current_price=body.current_price,
        group_id=body.group_id,
        metadata_json=body.metadata_json,
    )
    db.add(asset)
    await db.flush()
    return asset


async def get_user_assets(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    asset_type: str | None = None,
    asset_status: str | None = None,
    group_id: uuid.UUID | None = None,
) -> list[Asset]:
    """사용자 자산 목록 조회 (필터 지원)."""
    query = select(Asset).where(Asset.user_id == user_id)

    if asset_type:
        query = query.where(Asset.type == asset_type)
    if asset_status:
        query = query.where(Asset.status == asset_status)
    if group_id:
        query = query.where(Asset.group_id == group_id)

    query = query.order_by(Asset.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_asset_by_id(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> Asset:
    """자산 단건 조회 — 404/403 처리."""
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="자산을 찾을 수 없습니다.",
        )
    if asset.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 자산에 접근할 권한이 없습니다.",
        )
    return asset


async def update_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetUpdateRequest,
) -> Asset:
    """자산 수정 — 매도 자산 수정 불가, 금액 필드 재암호화."""
    asset = await get_asset_by_id(db, user_id, asset_id)

    if asset.status == AssetStatus.SOLD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 매도된 자산은 수정할 수 없습니다.",
        )

    update_data = body.model_dump(exclude_unset=True)

    # group_id 변경 시 소유권 검증
    if "group_id" in update_data and update_data["group_id"] is not None:
        await _verify_group_ownership(db, user_id, update_data["group_id"])

    for field, value in update_data.items():
        if field in _ENCRYPTED_FIELDS:
            setattr(asset, field, encrypt_decimal(value))
        else:
            setattr(asset, field, value)

    await db.flush()
    return asset


async def delete_asset(
    db: AsyncSession, user_id: uuid.UUID, asset_id: uuid.UUID
) -> None:
    """자산 삭제 — 매도 자산 삭제 불가."""
    asset = await get_asset_by_id(db, user_id, asset_id)

    if asset.status == AssetStatus.SOLD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 매도된 자산은 삭제할 수 없습니다.",
        )

    await db.delete(asset)
    await db.flush()


async def sell_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetSellRequest,
) -> Asset:
    """자산 매도 — PnL 계산 후 암호화 저장."""
    asset = await get_asset_by_id(db, user_id, asset_id)

    if asset.status == AssetStatus.SOLD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 매도된 자산입니다.",
        )

    # 복호화하여 PnL 계산 (Decimal 정밀도)
    qty = decrypt_decimal(asset.quantity)
    buy_price = decrypt_decimal(asset.purchase_price)
    realized_pnl = (body.sold_price - buy_price) * qty

    asset.status = AssetStatus.SOLD
    asset.sold_at = body.sold_at or datetime.now(timezone.utc)
    asset.sold_price = encrypt_decimal(body.sold_price)
    asset.realized_pnl = encrypt_decimal(realized_pnl)

    await db.flush()
    return asset


def asset_to_response(asset: Asset) -> AssetResponse:
    """ORM 모델 → AssetResponse 변환 (금액 필드 복호화)."""
    return AssetResponse(
        id=asset.id,
        user_id=asset.user_id,
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
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


async def _verify_group_ownership(
    db: AsyncSession, user_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    """그룹 소유권 검증."""
    result = await db.execute(
        select(PortfolioGroup).where(PortfolioGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="포트폴리오 그룹을 찾을 수 없습니다.",
        )
    if group.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 그룹에 접근할 권한이 없습니다.",
        )
