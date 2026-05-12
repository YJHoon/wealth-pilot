"""종목별 보유량 분해 (전략 N주 + 수동 M주 + KIS 실잔고) — 자산 화면용.

자동매매(`TradingPosition`)와 원클릭 매매(`AdvisoryPosition`)는 격리된 포지션이며,
KIS는 둘을 구분하지 못한 합산 잔고만 알고 있다. 자산 화면에서 "전략 N주 + 수동 M주"
형태로 분리 표기하고 정합성 어긋남을 경고하기 위한 read 전용 어그리게이터.

정합성 식: KIS실잔고(ticker) = Σ TradingPosition + Σ AdvisoryPosition

Asset 테이블의 KIS DOMESTIC_STOCK 활성 자산이 KIS 실잔고를 대표한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetSource, AssetStatus, AssetType
from app.models.trading import AdvisoryPosition, TradingAccount, TradingPosition
from app.services.crypto_service import decrypt_decimal


@dataclass
class HoldingBreakdownItem:
    account_id: UUID
    ticker: str
    ticker_name: str
    strategy_qty: Decimal
    advisory_qty: Decimal
    kis_qty: Decimal | None
    mismatch_qty: Decimal
    has_mismatch: bool


@dataclass
class HoldingBreakdownResult:
    items: list[HoldingBreakdownItem] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)


async def build_user_holding_breakdown(
    db: AsyncSession,
    user_id: UUID,
) -> HoldingBreakdownResult:
    """사용자의 모든 활성 매매 계좌에 대해 ticker별 보유량 분해."""
    accounts_q = await db.execute(
        select(TradingAccount).where(
            TradingAccount.user_id == user_id,
            TradingAccount.is_active.is_(True),
        )
    )
    accounts = list(accounts_q.scalars().all())

    result = HoldingBreakdownResult()
    for account in accounts:
        items = await _breakdown_for_account(db, account.id)
        result.items.extend(items)
        result.mismatches.extend(_format_mismatches(items))

    return result


async def _breakdown_for_account(
    db: AsyncSession,
    account_id: UUID,
) -> list[HoldingBreakdownItem]:
    # 전략 포지션 합 (ticker별)
    strat_q = await db.execute(
        select(TradingPosition).where(TradingPosition.account_id == account_id)
    )
    strat_qty: dict[str, Decimal] = {}
    ticker_names: dict[str, str] = {}
    for pos in strat_q.scalars().all():
        strat_qty[pos.ticker] = (
            strat_qty.get(pos.ticker, Decimal("0")) + decrypt_decimal(pos.quantity)
        )
        if pos.ticker_name and pos.ticker not in ticker_names:
            ticker_names[pos.ticker] = pos.ticker_name

    # advisory 포지션 합 (ticker별; account+ticker UNIQUE라 1행이지만 안전하게 합산)
    adv_q = await db.execute(
        select(AdvisoryPosition).where(AdvisoryPosition.account_id == account_id)
    )
    adv_qty: dict[str, Decimal] = {}
    for pos in adv_q.scalars().all():
        adv_qty[pos.ticker] = (
            adv_qty.get(pos.ticker, Decimal("0")) + decrypt_decimal(pos.quantity)
        )
        if pos.ticker_name and pos.ticker not in ticker_names:
            ticker_names[pos.ticker] = pos.ticker_name

    # KIS 실잔고 (Asset 테이블: KIS source, DOMESTIC_STOCK, ACTIVE, same trading_account_id)
    asset_q = await db.execute(
        select(Asset).where(
            Asset.trading_account_id == account_id,
            Asset.source == AssetSource.KIS,
            Asset.type == AssetType.DOMESTIC_STOCK,
            Asset.status == AssetStatus.ACTIVE,
        )
    )
    kis_qty: dict[str, Decimal] = {}
    for asset in asset_q.scalars().all():
        ticker = asset.external_ticker or asset.ticker
        if not ticker:
            continue
        kis_qty[ticker] = (
            kis_qty.get(ticker, Decimal("0")) + decrypt_decimal(asset.quantity)
        )
        if asset.name and ticker not in ticker_names:
            ticker_names[ticker] = asset.name

    all_tickers = set(strat_qty) | set(adv_qty) | set(kis_qty)
    items: list[HoldingBreakdownItem] = []
    # 결정성 보장
    for ticker in sorted(all_tickers):
        s = strat_qty.get(ticker, Decimal("0"))
        a = adv_qty.get(ticker, Decimal("0"))
        kis = kis_qty.get(ticker)
        internal = s + a
        if kis is None:
            # KIS 실잔고를 모르면 mismatch 판정 보류 (자산 미동기화 가능성)
            mismatch = Decimal("0")
            has_mismatch = False
        else:
            mismatch = internal - kis
            has_mismatch = mismatch != 0
        items.append(
            HoldingBreakdownItem(
                account_id=account_id,
                ticker=ticker,
                ticker_name=ticker_names.get(ticker, ""),
                strategy_qty=s,
                advisory_qty=a,
                kis_qty=kis,
                mismatch_qty=mismatch,
                has_mismatch=has_mismatch,
            )
        )
    return items


def _format_mismatches(items: list[HoldingBreakdownItem]) -> list[str]:
    out: list[str] = []
    for it in items:
        if not it.has_mismatch:
            continue
        kis_repr = "?" if it.kis_qty is None else str(it.kis_qty)
        out.append(
            f"{it.ticker}: 전략={it.strategy_qty}, 수동={it.advisory_qty}, "
            f"합계={it.strategy_qty + it.advisory_qty} vs KIS={kis_repr} "
            f"(차이={it.mismatch_qty})"
        )
    return out
