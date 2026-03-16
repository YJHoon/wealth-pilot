"""포트폴리오 그룹 CRUD 라우터"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.schemas.group import (
    GroupCreate,
    GroupListResponse,
    GroupResponse,
    GroupUpdate,
)
from app.services.group_service import (
    create_group as svc_create_group,
    delete_group as svc_delete_group,
    list_groups as svc_list_groups,
    update_group as svc_update_group,
)
from app.services.security_service import AccessAction, log_access

router = APIRouter(prefix="/api/groups", tags=["포트폴리오 그룹"])


@router.get("", response_model=GroupListResponse)
async def list_groups(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 포트폴리오 그룹 목록 조회."""
    result = await svc_list_groups(db, user)
    try:
        await log_access(db, user.id, AccessAction.GROUP_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
    return result


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """새 포트폴리오 그룹 생성."""
    return await svc_create_group(db, user, body, request)


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: UUID,
    body: GroupUpdate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 그룹 수정 (부분 업데이트)."""
    result = await svc_update_group(db, user, group_id, body, request)
    if result is None:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return result


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 그룹 삭제 (소속 자산의 group_id는 null로)."""
    deleted = await svc_delete_group(db, user, group_id, request)
    if not deleted:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
