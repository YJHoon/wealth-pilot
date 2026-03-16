"""자산 관리 라우터 — CRUD + 매도"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.asset import (
    AssetCreateRequest,
    AssetListResponse,
    AssetResponse,
    AssetSellRequest,
    AssetUpdateRequest,
)
from app.services.asset_service import (
    asset_to_response,
    create_asset,
    delete_asset,
    get_asset_by_id,
    get_user_assets,
    sell_asset,
    update_asset,
)
from app.services.security_service import AccessAction, log_access

router = APIRouter(prefix="/api/assets", tags=["자산"])


@router.get("", response_model=AssetListResponse)
@limiter.limit("100/minute")
async def list_assets(
    request: Request,
    type: str | None = Query(None, description="자산 유형 필터"),
    status_filter: str | None = Query(None, alias="status", description="상태 필터"),
    group_id: uuid.UUID | None = Query(None, description="그룹 ID 필터"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 목록 조회 (필터: type, status, group_id)"""
    assets = await get_user_assets(
        db,
        user.id,
        asset_type=type,
        asset_status=status_filter,
        group_id=group_id,
    )
    await log_access(db, user.id, AccessAction.ASSET_VIEW, request)
    await db.commit()
    return AssetListResponse(
        assets=[asset_to_response(a) for a in assets],
        total=len(assets),
    )


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("100/minute")
async def create_asset_endpoint(
    request: Request,
    body: AssetCreateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 추가"""
    asset = await create_asset(db, user.id, body)
    await log_access(db, user.id, AccessAction.ASSET_CREATE, request)
    await db.commit()
    return asset_to_response(asset)


@router.get("/{asset_id}", response_model=AssetResponse)
@limiter.limit("100/minute")
async def get_asset(
    request: Request,
    asset_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 단건 조회"""
    asset = await get_asset_by_id(db, user.id, asset_id)
    await log_access(db, user.id, AccessAction.ASSET_VIEW, request)
    await db.commit()
    return asset_to_response(asset)


@router.put("/{asset_id}", response_model=AssetResponse)
@limiter.limit("100/minute")
async def update_asset_endpoint(
    request: Request,
    asset_id: uuid.UUID,
    body: AssetUpdateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 수정"""
    asset = await update_asset(db, user.id, asset_id, body)
    await log_access(db, user.id, AccessAction.ASSET_UPDATE, request)
    await db.commit()
    return asset_to_response(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("100/minute")
async def delete_asset_endpoint(
    request: Request,
    asset_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 삭제"""
    await delete_asset(db, user.id, asset_id)
    await log_access(db, user.id, AccessAction.ASSET_DELETE, request)
    await db.commit()


@router.post("/{asset_id}/sell", response_model=AssetResponse)
@limiter.limit("100/minute")
async def sell_asset_endpoint(
    request: Request,
    asset_id: uuid.UUID,
    body: AssetSellRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 매도"""
    asset = await sell_asset(db, user.id, asset_id, body)
    await log_access(db, user.id, AccessAction.ASSET_SELL, request)
    await db.commit()
    return asset_to_response(asset)
