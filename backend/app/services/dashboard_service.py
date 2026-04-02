"""대시보드 서비스 — 자산 요약, 히스토리, 스냅샷 생성"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus, AssetType, Currency
from app.models.asset_snapshot import AssetSnapshot
from app.models.exchange_rate import ExchangeRate
from app.models.portfolio_group import PortfolioGroup
from app.models.trading import TradingAccount, TradingPosition
from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
    encrypt_decimal,
)

logger = logging.getLogger(__name__)

# 비중 소수점 자리수
_RATIO_PLACES = Decimal("0.0001")


async def _get_exchange_rates(db: AsyncSession) -> dict[str, Decimal]:
    """DB에서 최신 환율 조회 → {from_currency: KRW 환산 비율} 딕셔너리.

    KRW는 1.0, 나머지는 exchange_rates 테이블에서 조회.
    """
    rates: dict[str, Decimal] = {"KRW": Decimal("1")}
    result = await db.execute(
        select(ExchangeRate).where(ExchangeRate.to_currency == "KRW")
    )
    for er in result.scalars().all():
        rates[er.from_currency] = er.rate
    return rates


def _to_krw(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    """금액을 원화로 환산. 환율이 없으면 ValueError를 발생시킨다."""
    if currency == "KRW":
        return amount
    rate = rates.get(currency)
    if rate is None:
        raise ValueError(f"Missing exchange rate for {currency}→KRW")
    return (amount * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


async def get_dashboard_summary(
    db: AsyncSession, user_id: uuid.UUID
) -> dict:
    """대시보드 요약 데이터 계산.

    Returns:
        총 자산, 유형별/그룹별 소계, 손익, 전일 대비 변동
    """
    rates = await _get_exchange_rates(db)

    # 모든 사용자 자산 조회
    result = await db.execute(
        select(Asset).where(Asset.user_id == user_id)
    )
    assets = result.scalars().all()

    # 그룹 이름 매핑
    group_result = await db.execute(
        select(PortfolioGroup).where(PortfolioGroup.user_id == user_id)
    )
    groups = {g.id: g.name for g in group_result.scalars().all()}

    total_value_krw = Decimal("0")
    total_cost_krw = Decimal("0")
    realized_pnl = Decimal("0")

    by_type: dict[str, Decimal] = {}
    by_group: dict[str, dict] = {}  # group_id → {name, value_krw}

    for asset in assets:
        quantity = decrypt_decimal(asset.quantity)
        purchase_price = decrypt_decimal(asset.purchase_price)
        currency = asset.currency.value if isinstance(asset.currency, Currency) else asset.currency

        if asset.status == AssetStatus.SOLD:
            # 매도 자산: 실현 손익만 반영
            rpnl = decrypt_decimal_optional(asset.realized_pnl)
            if rpnl is not None:
                try:
                    realized_pnl += _to_krw(rpnl, currency, rates)
                except ValueError:
                    logger.warning(
                        "Skipping sold asset %s: missing exchange rate for %s",
                        asset.id, currency,
                    )
            continue

        # 활성 자산: 평가액 계산
        if asset.type == AssetType.CASH:
            # 현금: quantity가 총액
            value = quantity
        elif asset.current_price is not None:
            value = quantity * asset.current_price
        else:
            # 현재가 없으면 매입가 기준
            value = quantity * purchase_price

        try:
            value_krw = _to_krw(value, currency, rates)
            cost_krw = _to_krw(quantity * purchase_price, currency, rates)
        except ValueError:
            logger.warning(
                "Skipping asset %s: missing exchange rate for %s",
                asset.id, currency,
            )
            continue

        total_value_krw += value_krw
        total_cost_krw += cost_krw

        # 유형별 집계
        asset_type = asset.type.value if isinstance(asset.type, AssetType) else asset.type
        by_type[asset_type] = by_type.get(asset_type, Decimal("0")) + value_krw

        # 그룹별 집계
        if asset.group_id is not None:
            gid = str(asset.group_id)
            if gid not in by_group:
                by_group[gid] = {
                    "name": groups.get(asset.group_id, "알 수 없는 그룹"),
                    "value_krw": Decimal("0"),
                }
            by_group[gid]["value_krw"] += value_krw
        else:
            if "ungrouped" not in by_group:
                by_group["ungrouped"] = {"name": "미분류", "value_krw": Decimal("0")}
            by_group["ungrouped"]["value_krw"] += value_krw

    # ── 증권 계좌 (Trading) 데이터 합산 ──
    trading_total_value = Decimal("0")

    acct_result = await db.execute(
        select(TradingAccount).where(
            TradingAccount.user_id == user_id,
            TradingAccount.is_active.is_(True),
        )
    )
    trading_accounts = acct_result.scalars().all()

    for acct in trading_accounts:
        # 현금 잔고
        cash = decrypt_decimal_optional(acct.cash_balance)
        if cash is not None and cash > 0:
            total_value_krw += cash
            trading_total_value += cash
            by_type["cash"] = by_type.get("cash", Decimal("0")) + cash

        # 보유 포지션
        pos_result = await db.execute(
            select(TradingPosition).where(
                TradingPosition.account_id == acct.id,
            )
        )
        for pos in pos_result.scalars().all():
            qty = decrypt_decimal(pos.quantity)
            avg_price = decrypt_decimal(pos.avg_buy_price)
            cur_price = Decimal(str(pos.current_price)) if pos.current_price is not None else avg_price

            pos_value = qty * cur_price
            pos_cost = qty * avg_price

            total_value_krw += pos_value
            total_cost_krw += pos_cost
            trading_total_value += pos_value

            by_type["domestic_stock"] = by_type.get("domestic_stock", Decimal("0")) + pos_value

    # 자동매매 그룹
    if trading_total_value > 0:
        by_group["trading"] = {"name": "자동매매", "value_krw": trading_total_value}

    # 비중 계산
    by_type_result = {}
    for t, val in by_type.items():
        ratio = (val / total_value_krw).quantize(_RATIO_PLACES) if total_value_krw else Decimal("0")
        by_type_result[t] = {"value_krw": val, "ratio": ratio}

    by_group_result = {}
    for gid, info in by_group.items():
        ratio = (info["value_krw"] / total_value_krw).quantize(_RATIO_PLACES) if total_value_krw else Decimal("0")
        by_group_result[gid] = {
            "name": info["name"],
            "value_krw": info["value_krw"],
            "ratio": ratio,
        }

    # 미실현 손익
    unrealized_pnl = total_value_krw - total_cost_krw
    total_pnl = realized_pnl + unrealized_pnl
    total_ratio = (total_pnl / total_cost_krw).quantize(_RATIO_PLACES) if total_cost_krw else Decimal("0")

    # 전일 대비 변동: 어제 스냅샷과 비교
    yesterday = date.today() - timedelta(days=1)
    snap_result = await db.execute(
        select(AssetSnapshot).where(
            and_(
                AssetSnapshot.user_id == user_id,
                AssetSnapshot.snapshot_date == yesterday,
            )
        )
    )
    yesterday_snap = snap_result.scalar_one_or_none()

    if yesterday_snap is not None:
        yesterday_value = decrypt_decimal(yesterday_snap.total_value_krw)
        day_change = total_value_krw - yesterday_value
        day_ratio = (day_change / yesterday_value).quantize(_RATIO_PLACES) if yesterday_value else Decimal("0")
    else:
        day_change = Decimal("0")
        day_ratio = Decimal("0")

    return {
        "total_value_krw": total_value_krw,
        "by_type": by_type_result,
        "by_group": by_group_result,
        "pnl": {
            "total": total_pnl,
            "realized": realized_pnl,
            "unrealized": unrealized_pnl,
            "total_ratio": total_ratio,
        },
        "previous_day_change": {
            "amount": day_change,
            "ratio": day_ratio,
        },
        "updated_at": datetime.now(timezone.utc),
    }


async def get_dashboard_history(
    db: AsyncSession, user_id: uuid.UUID, period: str
) -> list[dict]:
    """기간별 자산 추이 데이터 조회."""
    period_days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    days = period_days.get(period, 30)
    since = date.today() - timedelta(days=days)

    result = await db.execute(
        select(AssetSnapshot)
        .where(
            and_(
                AssetSnapshot.user_id == user_id,
                AssetSnapshot.snapshot_date >= since,
            )
        )
        .order_by(AssetSnapshot.snapshot_date.asc())
    )
    snapshots = result.scalars().all()

    data_points = []
    for snap in snapshots:
        data_points.append({
            "date": snap.snapshot_date.isoformat(),
            "total_value_krw": decrypt_decimal(snap.total_value_krw),
            "breakdown": snap.breakdown,
        })

    return data_points


async def create_snapshot(
    db: AsyncSession, user_id: uuid.UUID
) -> AssetSnapshot:
    """현재 자산 상태를 스냅샷으로 저장.

    - 같은 날짜에 이미 스냅샷이 있으면 업데이트
    - expires_at = created_at + 1년
    """
    summary = await get_dashboard_summary(db, user_id)
    today = date.today()

    # 오늘 이미 스냅샷이 있는지 확인
    result = await db.execute(
        select(AssetSnapshot).where(
            and_(
                AssetSnapshot.user_id == user_id,
                AssetSnapshot.snapshot_date == today,
            )
        )
    )
    existing = result.scalar_one_or_none()

    # breakdown에서 비중만 저장 (금액 제외)
    breakdown = {
        "by_type": {
            t: {"ratio": float(info["ratio"])}
            for t, info in summary["by_type"].items()
        },
        "by_group": {
            gid: {"name": info["name"], "ratio": float(info["ratio"])}
            for gid, info in summary["by_group"].items()
        },
    }

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=365)

    if existing is not None:
        existing.total_value_krw = encrypt_decimal(summary["total_value_krw"])
        existing.breakdown = breakdown
        existing.expires_at = expires_at
        await db.commit()
        await db.refresh(existing)
        return existing

    snapshot = AssetSnapshot(
        user_id=user_id,
        total_value_krw=encrypt_decimal(summary["total_value_krw"]),
        breakdown=breakdown,
        snapshot_date=today,
        expires_at=expires_at,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot
