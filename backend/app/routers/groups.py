"""포트폴리오 그룹 CRUD 라우터"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.asset import Asset
from app.models.portfolio_group import PortfolioGroup
from app.models.user import User
from app.schemas.group import (
    GroupCreate,
    GroupListResponse,
    GroupResponse,
    GroupUpdate,
)

router = APIRouter(prefix="/api/groups", tags=["포트폴리오 그룹"])


@router.get("", response_model=GroupListResponse)
async def list_groups(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 포트폴리오 그룹 목록 조회."""
    # asset_count 서브쿼리
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


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """새 포트폴리오 그룹 생성."""
    group = PortfolioGroup(
        user_id=user.id,
        name=body.name,
        description=body.description,
        sort_order=body.sort_order,
    )
    db.add(group)
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


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    body: GroupUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 그룹 수정 (부분 업데이트)."""
    result = await db.execute(
        select(PortfolioGroup).where(
            PortfolioGroup.id == group_id,
            PortfolioGroup.user_id == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    await db.commit()
    await db.refresh(group)

    # asset_count 계산
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


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 그룹 삭제 (소속 자산의 group_id는 null로)."""
    result = await db.execute(
        select(PortfolioGroup).where(
            PortfolioGroup.id == group_id,
            PortfolioGroup.user_id == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")

    # 소속 자산의 group_id를 null로 업데이트
    from sqlalchemy import update

    await db.execute(
        update(Asset).where(Asset.group_id == group.id).values(group_id=None)
    )

    await db.delete(group)
    await db.commit()
