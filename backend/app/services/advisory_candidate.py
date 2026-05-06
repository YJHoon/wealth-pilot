"""원클릭 분석·매매 후보풀 빌더.

자동매매와 충돌하지 않는 안전한 후보 집합을 만든다.
- HOLDING source: 사용자 자기가 보유한 advisory 분량 (SELL/HOLD 평가 대상)
- AUTO_PICK source: 룰베이스 종목 선정 결과 (BUY 평가 대상)

충돌 격리:
- 활성 전략이 들고 있는 ticker는 BUY/SELL 모두에서 제외 → 자동매매가 같은
  종목을 들고 있다면 advisory는 손대지 않는다 (유령 보유분 방지).
- SELL 평가가 가능한 보유분은 오로지 AdvisoryPosition 뿐.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import (
    AnalysisItemSource,
    TradingPosition,
    TradingStrategy,
)
from app.services.advisory_position import list_advisory_positions
from app.services.crypto_service import decrypt_decimal
from app.services.ticker_selector import (
    SelectedTicker,
    SelectorConfig,
    UniverseLoader,
    load_universe,
    select_tickers,
)

DEFAULT_MAX_CANDIDATES = 20
DEFAULT_MAX_POSITION_PCT = Decimal("0.20")


@dataclass(slots=True)
class CandidateItem:
    """후보 1건."""

    ticker: str
    ticker_name: str
    source: AnalysisItemSource
    ref_price: Decimal | None = None
    held_qty: Decimal | None = None  # HOLDING source 일 때 advisory 보유 수량


@dataclass(slots=True)
class CandidatePool:
    items: list[CandidateItem]
    # 디버그/감사용
    excluded_by_active_strategy: list[str] = field(default_factory=list)
    auto_pick_rule_version: str | None = None


async def _active_strategy_held_tickers(
    db: AsyncSession, account_id: UUID,
) -> set[str]:
    """계좌의 활성(`is_active=True`) 전략들이 보유 중인 ticker 집합."""
    rows = await db.execute(
        select(TradingPosition.ticker)
        .join(
            TradingStrategy, TradingStrategy.id == TradingPosition.strategy_id,
        )
        .where(
            TradingPosition.account_id == account_id,
            TradingStrategy.is_active.is_(True),
        )
    )
    return {row[0] for row in rows.all() if row[0]}


def _normalize_blocked_extra(extra: Iterable[str] | None) -> set[str]:
    if not extra:
        return set()
    return {str(t).strip() for t in extra if str(t).strip()}


async def build_candidate_pool(
    db: AsyncSession,
    *,
    user_id: UUID,
    account_id: UUID,
    options: dict | None,
    available_cash: Decimal,
    total_eval: Decimal,
    max_position_pct: Decimal = DEFAULT_MAX_POSITION_PCT,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    extra_blocked_tickers: Iterable[str] | None = None,
    loader: UniverseLoader = load_universe,
) -> CandidatePool:
    """후보풀을 만든다.

    Args:
        options: AnalysisRun.candidate_pool_options. SelectorConfig.from_dict 와 같은 키 셋.
        available_cash / total_eval / max_position_pct: ticker_selector 시드 컷용.
        max_candidates: 최종 후보 상한 (LLM 비용 가드 — 보통 20개).
        extra_blocked_tickers: 호출자가 추가로 제외하고 싶은 ticker (예: 사용자 blacklist).

    Returns:
        CandidatePool. items 는 HOLDING이 먼저, AUTO_PICK이 뒤로.
    """
    _ = user_id  # 추후 사용자별 워치리스트 등에 사용 예정. 현재 시그니처 보존.

    blocked = await _active_strategy_held_tickers(db, account_id)
    extra = _normalize_blocked_extra(extra_blocked_tickers)
    excluded_set = blocked | extra

    items: list[CandidateItem] = []
    seen: set[str] = set()

    # 1) HOLDING — advisory 보유분만 SELL/HOLD 평가 대상으로 노출
    advisory_holdings = await list_advisory_positions(db, account_id)
    for pos in advisory_holdings:
        if pos.ticker in excluded_set or pos.ticker in seen:
            continue
        try:
            qty = decrypt_decimal(pos.quantity)
        except (ValueError, ArithmeticError):
            continue
        if qty <= 0:
            continue
        items.append(
            CandidateItem(
                ticker=pos.ticker,
                ticker_name=pos.ticker_name or pos.ticker,
                source=AnalysisItemSource.HOLDING,
                ref_price=Decimal(str(pos.current_price))
                if pos.current_price is not None
                else None,
                held_qty=qty,
            )
        )
        seen.add(pos.ticker)

    # 2) AUTO_PICK — 룰베이스 자동 선정
    config = SelectorConfig.from_dict(options or {})
    selection = await select_tickers(
        config,
        available_cash=available_cash,
        total_eval=total_eval,
        max_position_pct=max_position_pct,
        loader=loader,
    )
    rule_version = selection.rule_version

    selected: list[SelectedTicker] = list(selection.selected)
    for s in selected:
        if s.ticker in excluded_set or s.ticker in seen:
            continue
        items.append(
            CandidateItem(
                ticker=s.ticker,
                ticker_name=s.name or s.ticker,
                source=AnalysisItemSource.AUTO_PICK,
                ref_price=s.price,
            )
        )
        seen.add(s.ticker)

    # 3) 상한 컷 — HOLDING 우선이라 잘려도 사용자 보유분은 보존됨
    items = items[:max_candidates]

    return CandidatePool(
        items=items,
        excluded_by_active_strategy=sorted(blocked),
        auto_pick_rule_version=rule_version,
    )
