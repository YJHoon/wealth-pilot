"""자산 매도 비즈니스 로직 서비스"""

from datetime import datetime, timezone
from decimal import Decimal

import logging

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetSource, AssetStatus, AssetType
from app.models.user import User
from app.services.crypto_service import decrypt_decimal, encrypt_decimal
from app.services.security_service import AccessAction, log_access

logger = logging.getLogger(__name__)


class AssetNotFoundError(Exception):
    pass


class AssetForbiddenError(Exception):
    pass


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
        AssetNotFoundError: 자산을 찾을 수 없는 경우
        AssetForbiddenError: 매도가 차단된 경우. 두 가지 사유:
            - 이미 매도된 자산 (status == SOLD)
            - KIS 동기화 자산 (source != MANUAL) — KIS 잔고 sync로만 변동
    """
    # rollback 시 expired 객체 접근 방지를 위해 스칼라 값 캐시
    user_id = user.id

    # 자산 조회 + 소유권 검증
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundError("자산을 찾을 수 없습니다.")

    if asset.status == AssetStatus.SOLD:
        raise AssetForbiddenError("이미 매도된 자산입니다.")

    if asset.source != AssetSource.MANUAL:
        raise AssetForbiddenError("KIS 동기화 자산은 매도 처리할 수 없습니다.")

    # 기존 값 복호화
    quantity = decrypt_decimal(asset.quantity)
    purchase_price = decrypt_decimal(asset.purchase_price)
    currency = asset.currency

    # 매도 처리
    asset.status = AssetStatus.SOLD
    asset.sold_at = datetime.now(timezone.utc)
    asset.sold_price = encrypt_decimal(sold_price)

    # realized_pnl = (단가 차이) * 수량
    realized_pnl = (sold_price - purchase_price) * quantity
    asset.realized_pnl = encrypt_decimal(realized_pnl)

    # 총 매도 대금
    total_proceeds = sold_price * quantity

    # 같은 통화의 활성 manual 현금 자산 검색 (행 잠금으로 동시성 보호)
    # KIS 동기화 cash는 잔고 sync로만 갱신되므로 매도 대금 합산 대상에서 제외.
    cash_result = await db.execute(
        select(Asset)
        .where(
            Asset.user_id == user_id,
            Asset.type == AssetType.CASH,
            Asset.status == AssetStatus.ACTIVE,
            Asset.currency == currency,
            Asset.source == AssetSource.MANUAL,
        )
        .with_for_update()
    )
    cash_asset = cash_result.scalar_one_or_none()

    if cash_asset is not None:
        # 기존 현금에 합산
        existing_quantity = decrypt_decimal(cash_asset.quantity)
        cash_asset.quantity = encrypt_decimal(existing_quantity + total_proceeds)
    else:
        # 새 현금 자산 생성 (manual source)
        cash_asset = Asset(
            user_id=user_id,
            type=AssetType.CASH,
            name="매도 수익금",
            currency=currency,
            quantity=encrypt_decimal(total_proceeds),
            purchase_price=encrypt_decimal(total_proceeds),
            source=AssetSource.MANUAL,
        )
        db.add(cash_asset)

    await log_access(db, user_id, AccessAction.ASSET_SELL, request)

    # 단일 commit — 원자성 보장
    # 동시 매도 요청 시 현금 자산 INSERT 충돌(IntegrityError) 처리
    try:
        await db.commit()
    except IntegrityError:
        logger.warning(
            "Cash asset IntegrityError during sale, retrying with existing row. "
            "user_id=%s asset_id=%s",
            user_id,
            asset_id,
        )
        await db.rollback()

        # 충돌 후 기존 현금 자산 re-query (행 잠금)
        cash_result = await db.execute(
            select(Asset)
            .where(
                Asset.user_id == user_id,
                Asset.type == AssetType.CASH,
                Asset.status == AssetStatus.ACTIVE,
                Asset.currency == currency,
                Asset.source == AssetSource.MANUAL,
            )
            .with_for_update()
        )
        cash_asset = cash_result.scalar_one_or_none()
        if cash_asset is None:
            # 현금 자산이 없다면 재시도 불가 — 상위에서 409로 처리
            raise

        # rollback으로 매도 상태가 초기화되었으므로 다시 적용
        result = await db.execute(
            select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            raise AssetNotFoundError("자산을 찾을 수 없습니다.")

        asset.status = AssetStatus.SOLD
        asset.sold_at = datetime.now(timezone.utc)
        asset.sold_price = encrypt_decimal(sold_price)
        asset.realized_pnl = encrypt_decimal(realized_pnl)

        existing_quantity = decrypt_decimal(cash_asset.quantity)
        cash_asset.quantity = encrypt_decimal(existing_quantity + total_proceeds)

        await log_access(db, user_id, AccessAction.ASSET_SELL, request)
        await db.commit()

    await db.refresh(asset)

    return asset
