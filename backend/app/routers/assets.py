"""자산 관리 CRUD 라우터"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.asset import Asset, AssetSource, AssetStatus, AssetType
from app.models.user import User
from app.schemas.asset import (
    AssetCreate,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
    HoldingBreakdownItemResponse,
    HoldingBreakdownResponse,
    SellRequest,
    asset_to_response,
)
from app.services.asset_service import (
    AssetForbiddenError,
    AssetNotFoundError,
    process_asset_sale,
)
from app.services.crypto_service import encrypt_decimal
from app.services.group_service import GroupNotFoundError, ensure_group_owned_by
from app.services.holding_breakdown import build_user_holding_breakdown
from app.services.security_service import AccessAction, log_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["자산"])


@router.get("", response_model=AssetListResponse)
async def list_assets(
    request: Request,
    asset_type: AssetType | None = Query(default=None, alias="type"),
    status_filter: AssetStatus | None = None,
    group_id: UUID | None = None,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 자산 목록 조회 (필터 지원)."""
    query = select(Asset).where(Asset.user_id == user.id)

    if asset_type is not None:
        query = query.where(Asset.type == asset_type)
    if status_filter is not None:
        query = query.where(Asset.status == status_filter)
    if group_id is not None:
        query = query.where(Asset.group_id == group_id)

    query = query.order_by(Asset.created_at.desc())
    result = await db.execute(query)
    assets = result.scalars().all()

    try:
        await log_access(db, user.id, AccessAction.ASSET_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning(
            "ASSET_VIEW access logging failed",
            exc_info=True,
            extra={"user_id": str(user.id)},
        )

    return AssetListResponse(
        assets=[asset_to_response(a) for a in assets],
        total=len(assets),
    )


@router.get("/holdings/breakdown", response_model=HoldingBreakdownResponse)
async def get_holdings_breakdown(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """종목별 보유량 분해: 전략 N주 + 수동 M주 + KIS 실잔고 + 정합성 차이.

    자동매매(`TradingPosition`)와 원클릭 매매(`AdvisoryPosition`)는 격리된 포지션이며,
    KIS는 둘을 구분 못 한 합계만 본다. 자산 화면에서 두 출처를 분리 표기하고,
    내부 합계 ≠ KIS 실잔고면 mismatch 메시지를 함께 반환한다.
    """
    breakdown = await build_user_holding_breakdown(db, user.id)

    try:
        await log_access(db, user.id, AccessAction.ASSET_VIEW, request)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning(
            "ASSET_VIEW (breakdown) access logging failed",
            exc_info=True,
            extra={"user_id": str(user.id)},
        )

    return HoldingBreakdownResponse(
        items=[
            HoldingBreakdownItemResponse(
                account_id=item.account_id,
                ticker=item.ticker,
                ticker_name=item.ticker_name,
                strategy_qty=item.strategy_qty,
                advisory_qty=item.advisory_qty,
                kis_qty=item.kis_qty,
                mismatch_qty=item.mismatch_qty,
                has_mismatch=item.has_mismatch,
            )
            for item in breakdown.items
        ],
        mismatches=breakdown.mismatches,
    )


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    body: AssetCreate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """새 자산 등록."""
    if body.group_id is not None:
        try:
            await ensure_group_owned_by(db, body.group_id, user.id)
        except GroupNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

    asset = Asset(
        user_id=user.id,
        group_id=body.group_id,
        type=body.type,
        name=body.name,
        ticker=body.ticker,
        currency=body.currency,
        quantity=encrypt_decimal(body.quantity),
        purchase_price=encrypt_decimal(body.purchase_price),
        current_price=body.current_price,
        metadata_json=body.metadata_json,
    )
    db.add(asset)

    await log_access(db, user.id, AccessAction.ASSET_CREATE, request)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="같은 통화의 활성 현금 자산은 하나만 가질 수 있습니다.") from None
    await db.refresh(asset)

    return asset_to_response(asset)


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    body: AssetUpdate,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 정보 수정 (부분 업데이트). 매도된 자산은 수정 불가."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다.")

    if asset.status == AssetStatus.SOLD:
        raise HTTPException(
            status_code=403, detail="매도된 자산은 수정할 수 없습니다."
        )

    if asset.source != AssetSource.MANUAL:
        raise HTTPException(
            status_code=403,
            detail="KIS 동기화 자산은 수정할 수 없습니다. 잔고 새로고침으로만 갱신됩니다.",
        )

    update_data = body.model_dump(exclude_unset=True)

    # group_id 소유권 검증
    if "group_id" in update_data and update_data["group_id"] is not None:
        try:
            await ensure_group_owned_by(db, update_data["group_id"], user.id)
        except GroupNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

    # 암호화 필드 처리
    encrypted_fields = {"quantity", "purchase_price"}
    for key, value in update_data.items():
        if key in encrypted_fields:
            setattr(asset, key, encrypt_decimal(value))
        else:
            setattr(asset, key, value)

    await log_access(db, user.id, AccessAction.ASSET_UPDATE, request)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="같은 통화의 활성 현금 자산은 하나만 가질 수 있습니다.") from None
    await db.refresh(asset)

    return asset_to_response(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 삭제 (하드 삭제). 매도된 자산은 삭제 불가."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다.")

    if asset.status == AssetStatus.SOLD:
        raise HTTPException(
            status_code=403, detail="매도된 자산은 삭제할 수 없습니다."
        )

    if asset.source != AssetSource.MANUAL:
        raise HTTPException(
            status_code=403,
            detail="KIS 동기화 자산은 삭제할 수 없습니다. 계좌 비활성화 시 자동 정리됩니다.",
        )

    await log_access(db, user.id, AccessAction.ASSET_DELETE, request)
    await db.delete(asset)
    await db.commit()


@router.post("/{asset_id}/sell", response_model=AssetResponse)
async def sell_asset(
    asset_id: UUID,
    body: SellRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """자산 매도 처리 (단일 트랜잭션, 원자적).

    - 자산 상태를 SOLD로 변경
    - realized_pnl 계산: (sold_price - purchase_price) * quantity
    - 같은 통화의 활성 현금 자산에 매도 대금 합산 (없으면 생성)
    """
    try:
        asset = await process_asset_sale(
            db, user, str(asset_id), body.sold_price, request
        )
    except AssetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except AssetForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="현금 자산 처리 중 충돌이 발생했습니다. 다시 시도해 주세요.",
        ) from None

    return asset_to_response(asset)
