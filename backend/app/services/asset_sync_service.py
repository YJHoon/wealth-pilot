"""KIS 잔고 → Asset 동기화 서비스.

`KISClient.get_balance()` 결과를 받아 Asset 테이블에 upsert한다.
- 보유종목 → Asset(type=DOMESTIC_STOCK, source=KIS, currency=KRW)
- 현금잔고 → Asset(type=CASH, source=KIS, currency=KRW)
- KIS에서 사라진 종목/현금 → status=SOLD 자동 마킹

멱등성 보장 — 같은 잔고를 다시 동기화해도 행이 늘어나지 않는다.
모든 KIS 자산은 source='kis' + trading_account_id로 식별되며 매도/수정/삭제는
asset_service / routers/assets에서 차단한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetSource, AssetStatus, AssetType, Currency
from app.models.trading import TradingAccount
from app.services.crypto_service import encrypt_decimal

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    upserted_holdings: int = 0
    upserted_cash: int = 0
    closed: int = 0  # SOLD 처리된 자산 수


async def sync_kis_balance(
    db: AsyncSession,
    account: TradingAccount,
    balance: dict,
) -> SyncResult:
    """KIS 잔고 결과를 Asset 테이블로 upsert.

    Args:
        db: 세션. 호출자가 commit/rollback 책임.
        account: TradingAccount (소유권 검증 완료된 인스턴스).
        balance: KISClient.get_balance() 반환값.

    Returns:
        SyncResult — 처리 건수.
    """
    user_id = account.user_id
    account_id = account.id
    now = datetime.now(timezone.utc)
    result = SyncResult()

    # 현재 KIS 활성 자산 모두 로드
    existing_q = await db.execute(
        select(Asset).where(
            Asset.user_id == user_id,
            Asset.trading_account_id == account_id,
            Asset.source == AssetSource.KIS,
            Asset.status == AssetStatus.ACTIVE,
        )
    )
    existing: list[Asset] = list(existing_q.scalars().all())
    by_ticker: dict[str, Asset] = {
        a.external_ticker: a
        for a in existing
        if a.type == AssetType.DOMESTIC_STOCK and a.external_ticker
    }
    cash_existing: Asset | None = next(
        (a for a in existing if a.type == AssetType.CASH and a.currency == Currency.KRW),
        None,
    )

    # 1) 보유종목 upsert
    seen_tickers: set[str] = set()
    for h in balance.get("holdings", []):
        ticker = (h.get("ticker") or "").strip()
        if not ticker:
            continue
        seen_tickers.add(ticker)

        quantity = Decimal(str(h.get("quantity", 0)))
        avg_price = Decimal(str(h.get("avg_price", 0)))
        current_price = h.get("current_price")
        name = h.get("name") or ticker

        existing_asset = by_ticker.get(ticker)
        if existing_asset is None:
            db.add(
                Asset(
                    user_id=user_id,
                    type=AssetType.DOMESTIC_STOCK,
                    status=AssetStatus.ACTIVE,
                    name=name,
                    ticker=ticker,
                    currency=Currency.KRW,
                    quantity=encrypt_decimal(quantity),
                    purchase_price=encrypt_decimal(avg_price),
                    current_price=current_price,
                    source=AssetSource.KIS,
                    trading_account_id=account_id,
                    external_ticker=ticker,
                    last_synced_at=now,
                )
            )
        else:
            existing_asset.name = name
            existing_asset.quantity = encrypt_decimal(quantity)
            existing_asset.purchase_price = encrypt_decimal(avg_price)
            existing_asset.current_price = current_price
            existing_asset.last_synced_at = now
        result.upserted_holdings += 1

    # 2) 현금 upsert (KIS는 KRW 단일)
    cash_amount = Decimal(str(balance.get("cash", 0)))
    if cash_existing is None:
        db.add(
            Asset(
                user_id=user_id,
                type=AssetType.CASH,
                status=AssetStatus.ACTIVE,
                name="KIS 예수금",
                currency=Currency.KRW,
                quantity=encrypt_decimal(cash_amount),
                purchase_price=encrypt_decimal(cash_amount),
                source=AssetSource.KIS,
                trading_account_id=account_id,
                last_synced_at=now,
            )
        )
    else:
        cash_existing.quantity = encrypt_decimal(cash_amount)
        cash_existing.purchase_price = encrypt_decimal(cash_amount)
        cash_existing.last_synced_at = now
    result.upserted_cash = 1

    # 3) KIS에서 사라진 보유종목 → SOLD 처리
    # 현금은 잔액 0이어도 계좌가 살아있으면 유지(0원으로 갱신).
    for ticker, asset in by_ticker.items():
        if ticker not in seen_tickers:
            asset.status = AssetStatus.SOLD
            asset.sold_at = now
            asset.last_synced_at = now
            result.closed += 1

    logger.info(
        "KIS balance synced to assets: account=%s holdings=%d closed=%d",
        account_id, result.upserted_holdings, result.closed,
    )
    return result


async def close_kis_assets_for_account(
    db: AsyncSession,
    account_id: UUID,
) -> int:
    """계좌 비활성화 시 해당 계좌의 KIS 자산을 모두 SOLD 처리.

    Returns: 변경된 행 수.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Asset).where(
            Asset.trading_account_id == account_id,
            Asset.source == AssetSource.KIS,
            Asset.status == AssetStatus.ACTIVE,
        )
    )
    rows = list(result.scalars().all())
    for asset in rows:
        asset.status = AssetStatus.SOLD
        asset.sold_at = now
        asset.last_synced_at = now
    return len(rows)
