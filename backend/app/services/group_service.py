"""포트폴리오 그룹 비즈니스 로직 서비스"""

from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.portfolio_group import PortfolioGroup
from app.models.user import User
from app.schemas.group import (
    GroupCreate,
    GroupListResponse,
    GroupResponse,
    GroupUpdate,
)
from app.services.security_service import AccessAction, log_access


class GroupNotFoundError(Exception):
    pass


async def ensure_group_owned_by(
    db: AsyncSession, group_id: UUID, user_id: UUID
) -> None:
    """그룹 소유권 검증. 그룹이 존재하지 않거나 소유자가 아니면 GroupNotFoundError 발생."""
    result = await db.execute(
        select(PortfolioGroup).where(
            PortfolioGroup.id == group_id,
            PortfolioGroup.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise GroupNotFoundError("그룹을 찾을 수 없습니다.")


async def list_groups(db: AsyncSession, user: User) -> GroupListResponse:
    """사용자의 포트폴리오 그룹 목록 조회."""
    asset_count_subq = (
        select(func.count(Asset.id))
        .where(Asset.group_id == PortfolioGroup.id)
        .correlate(PortfolioGroup)
        .scalar_subquery()
    )

    result = await db.execute(
        select(PortfolioGroup, asset_count_subq.label("asset_count"))
        .where(PortfolioGroup.user_id == user.id)
        .order_by(PortfolioGroup.sort_order)
    )
    rows = result.all()

    groups = [
        GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            sort_order=group.sort_order,
            created_at=group.created_at,
            asset_count=count,
        )
        for group, count in rows
    ]
    return GroupListResponse(groups=groups, total=len(groups))


async def create_group(
    db: AsyncSession, user: User, body: GroupCreate, request: Request
) -> GroupResponse:
    """새 포트폴리오 그룹 생성."""
    group = PortfolioGroup(
        user_id=user.id,
        name=body.name,
        description=body.description,
        sort_order=body.sort_order,
    )
    db.add(group)
    await log_access(db, user.id, AccessAction.GROUP_CREATE, request)
    await db.commit()
    await db.refresh(group)

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        created_at=group.created_at,
        asset_count=0,
    )


async def update_group(
    db: AsyncSession,
    user: User,
    group_id: UUID,
    body: GroupUpdate,
    request: Request,
) -> GroupResponse | None:
    """포트폴리오 그룹 수정. 존재하지 않으면 None 반환."""
    result = await db.execute(
        select(PortfolioGroup).where(
            PortfolioGroup.id == group_id,
            PortfolioGroup.user_id == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        return None

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    await log_access(db, user.id, AccessAction.GROUP_UPDATE, request)
    await db.commit()
    await db.refresh(group)

    count_result = await db.execute(
        select(func.count(Asset.id)).where(Asset.group_id == group.id)
    )
    asset_count = count_result.scalar_one()

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        sort_order=group.sort_order,
        created_at=group.created_at,
        asset_count=asset_count,
    )


async def delete_group(
    db: AsyncSession, user: User, group_id: UUID, request: Request
) -> bool:
    """포트폴리오 그룹 삭제. 성공 시 True, 미존재 시 False."""
    result = await db.execute(
        select(PortfolioGroup).where(
            PortfolioGroup.id == group_id,
            PortfolioGroup.user_id == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        return False

    # 소속 자산의 group_id를 null로 업데이트 (user_id 조건 추가)
    await db.execute(
        update(Asset)
        .where(Asset.group_id == group.id, Asset.user_id == user.id)
        .values(group_id=None)
    )

    await log_access(db, user.id, AccessAction.GROUP_DELETE, request)
    await db.delete(group)
    await db.commit()
    return True
