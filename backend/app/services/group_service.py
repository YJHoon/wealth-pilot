"""포트폴리오 그룹 서비스 — CRUD 비즈니스 로직"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.portfolio_group import PortfolioGroup
from app.schemas.group import GroupCreateRequest, GroupResponse, GroupUpdateRequest


async def create_group(
    db: AsyncSession, user_id: uuid.UUID, body: GroupCreateRequest
) -> PortfolioGroup:
    """포트폴리오 그룹 생성."""
    group = PortfolioGroup(
        user_id=user_id,
        name=body.name,
        description=body.description,
        sort_order=body.sort_order,
    )
    db.add(group)
    await db.flush()
    return group


async def get_user_groups(
    db: AsyncSession, user_id: uuid.UUID
) -> list[PortfolioGroup]:
    """사용자의 그룹 목록 조회 (sort_order 오름차순)."""
    result = await db.execute(
        select(PortfolioGroup)
        .where(PortfolioGroup.user_id == user_id)
        .order_by(PortfolioGroup.sort_order, PortfolioGroup.created_at)
    )
    return list(result.scalars().all())


async def get_group_by_id(
    db: AsyncSession, user_id: uuid.UUID, group_id: uuid.UUID
) -> PortfolioGroup:
    """그룹 단건 조회 — 404/403 처리."""
    result = await db.execute(
        select(PortfolioGroup).where(PortfolioGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="그룹을 찾을 수 없습니다.",
        )
    if group.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 그룹에 접근할 권한이 없습니다.",
        )
    return group


async def update_group(
    db: AsyncSession,
    user_id: uuid.UUID,
    group_id: uuid.UUID,
    body: GroupUpdateRequest,
) -> PortfolioGroup:
    """그룹 수정."""
    group = await get_group_by_id(db, user_id, group_id)
    update_data = body.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(group, field, value)

    await db.flush()
    return group


async def delete_group(
    db: AsyncSession, user_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    """그룹 삭제 — FK CASCADE로 자산의 group_id는 NULL 설정."""
    group = await get_group_by_id(db, user_id, group_id)
    await db.delete(group)
    await db.flush()


async def get_asset_count(db: AsyncSession, group_id: uuid.UUID) -> int:
    """그룹에 속한 자산 수."""
    result = await db.execute(
        select(func.count()).select_from(Asset).where(Asset.group_id == group_id)
    )
    return result.scalar_one()


async def group_to_response(db: AsyncSession, group: PortfolioGroup) -> GroupResponse:
    """ORM 모델 → GroupResponse 변환 (asset_count 포함)."""
    count = await get_asset_count(db, group.id)
    return GroupResponse(
        id=group.id,
        user_id=group.user_id,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        created_at=group.created_at,
        asset_count=count,
    )
