"""포트폴리오 그룹 라우터 — CRUD"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.group import (
    GroupCreateRequest,
    GroupListResponse,
    GroupResponse,
    GroupUpdateRequest,
)
from app.services.group_service import (
    create_group,
    delete_group,
    get_group_by_id,
    get_user_groups,
    group_to_response,
    update_group,
)
from app.services.security_service import AccessAction, log_access

router = APIRouter(prefix="/api/groups", tags=["포트폴리오 그룹"])


@router.get("", response_model=GroupListResponse)
@limiter.limit("100/minute")
async def list_groups(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """그룹 목록 조회"""
    groups = await get_user_groups(db, user.id)
    responses = [await group_to_response(db, g) for g in groups]
    return GroupListResponse(groups=responses, total=len(responses))


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("100/minute")
async def create_group_endpoint(
    request: Request,
    body: GroupCreateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """그룹 생성"""
    group = await create_group(db, user.id, body)
    await log_access(db, user.id, AccessAction.GROUP_CREATE, request)
    await db.commit()
    return await group_to_response(db, group)


@router.get("/{group_id}", response_model=GroupResponse)
@limiter.limit("100/minute")
async def get_group(
    request: Request,
    group_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """그룹 단건 조회"""
    group = await get_group_by_id(db, user.id, group_id)
    return await group_to_response(db, group)


@router.put("/{group_id}", response_model=GroupResponse)
@limiter.limit("100/minute")
async def update_group_endpoint(
    request: Request,
    group_id: uuid.UUID,
    body: GroupUpdateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """그룹 수정"""
    group = await update_group(db, user.id, group_id, body)
    await log_access(db, user.id, AccessAction.GROUP_UPDATE, request)
    await db.commit()
    return await group_to_response(db, group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("100/minute")
async def delete_group_endpoint(
    request: Request,
    group_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """그룹 삭제"""
    await delete_group(db, user.id, group_id)
    await log_access(db, user.id, AccessAction.GROUP_DELETE, request)
    await db.commit()
