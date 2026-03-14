"""자산 매도 비즈니스 로직 서비스"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus, AssetType
from app.models.user import User
from app.services.crypto_service import decrypt_decimal, encrypt_decimal
from app.services.security_service import AccessAction, log_access


async def process_asset_sale(
    db: AsyncSession,
    user: User,
    asset_id: str,
    sold_price: Decimal,
    request: Request,
) -> Asset:
    """자산 매도 처리 (단일 트랜잭션, 원자적).

    - 자산 상태를 SOLD로 변경
    - realized_pnl 계산: (sold_price - purchase_price) * quantity
    - 같은 통화의 활성 현금 자산에 매도 대금 합산 (없으면 생성)

    Returns:
        매도 처리된 Asset 객체 (commit/refresh 완료)

    Raises:
        ValueError: 자산을 찾을 수 없거나 이미 매도된 경우
    """
    # 자산 조회 + 소유권 검증
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == user.id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise ValueError("자산을 찾을 수 없습니다.")

    if asset.status == AssetStatus.SOLD:
        raise ValueError("이미 매도된 자산입니다.")

    # 기존 값 복호화
    quantity = decrypt_decimal(asset.quantity)
    purchase_price = decrypt_decimal(asset.purchase_price)

    # 매도 처리
    asset.status = AssetStatus.SOLD
    asset.sold_at = datetime.now(timezone.utc)
    asset.sold_price = encrypt_decimal(sold_price)

    # realized_pnl = (단가 차이) * 수량
    realized_pnl = (sold_price - purchase_price) * quantity
    asset.realized_pnl = encrypt_decimal(realized_pnl)

    # 총 매도 대금
    total_proceeds = sold_price * quantity

    # 같은 통화의 활성 현금 자산 검색 (행 잠금으로 동시성 보호)
    cash_result = await db.execute(
        select(Asset)
        .where(
            Asset.user_id == user.id,
            Asset.type == AssetType.CASH,
            Asset.status == AssetStatus.ACTIVE,
            Asset.currency == asset.currency,
        )
        .with_for_update()
    )
    cash_asset = cash_result.scalar_one_or_none()

    if cash_asset is not None:
        # 기존 현금에 합산
        existing_quantity = decrypt_decimal(cash_asset.quantity)
        cash_asset.quantity = encrypt_decimal(existing_quantity + total_proceeds)
    else:
        # 새 현금 자산 생성
        cash_asset = Asset(
            user_id=user.id,
            type=AssetType.CASH,
            name="매도 수익금",
            currency=asset.currency,
            quantity=encrypt_decimal(total_proceeds),
            purchase_price=encrypt_decimal(total_proceeds),
        )
        db.add(cash_asset)

    await log_access(db, user.id, AccessAction.ASSET_SELL, request)

    # 단일 commit — 원자성 보장
    await db.commit()
    await db.refresh(asset)

    return asset
