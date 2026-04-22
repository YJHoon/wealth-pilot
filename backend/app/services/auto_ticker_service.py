"""자동 종목 선정 서비스 — DB 영속화 계층.

`ticker_selector`의 순수 파이프라인을 호출해서 결과를 전략 컬럼과
이력 테이블에 기록한다. LazyRefresh, schedule, manual 세 트리거에서 공유.

선정 결과가 비어 있는 경우 기존 `auto_selected_tickers`를 유지한다(D7).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trading import AutoTickerSelection, TradingPosition, TradingStrategy
from app.services.ticker_selector import (
    SelectionResult,
    SelectorConfig,
    UniverseLoader,
    load_universe,
    select_tickers,
)

logger = logging.getLogger(__name__)

TriggerSource = Literal["schedule", "lazy", "manual"]

# lazy 트리거가 허용하는 최대 stale 시간. 이 이상 지나면 자동 갱신.
STALE_AFTER = timedelta(hours=24)


def _max_position_pct(strategy: TradingStrategy) -> Decimal:
    try:
        raw = (strategy.params_json or {}).get("max_position_pct", "0.20")
        return Decimal(str(raw))
    except (ValueError, ArithmeticError):
        return Decimal("0.20")


def is_enabled(strategy: TradingStrategy) -> bool:
    cfg = strategy.auto_select_config or {}
    return bool(cfg.get("enabled"))


def is_stale(strategy: TradingStrategy, *, now: datetime | None = None) -> bool:
    """auto_selected_tickers가 없거나 24h 이상 경과했는지."""
    now = now or datetime.now(timezone.utc)
    stored = strategy.auto_selected_tickers or {}
    ts = stored.get("generated_at")
    if not ts:
        return True
    try:
        generated_at = datetime.fromisoformat(ts)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True
    return (now - generated_at) >= STALE_AFTER


def _serialize_selection(result: SelectionResult, *, now: datetime) -> dict:
    return {
        "tickers": [s.ticker for s in result.selected],
        "generated_at": now.isoformat(),
        "rule_version": result.rule_version,
        "details": [
            {
                "ticker": s.ticker,
                "name": s.name,
                "market": s.market,
                "price": str(s.price),
                "volume_value": s.volume_value,
                "score": round(s.score, 4),
                "reason": s.reason,
            }
            for s in result.selected
        ],
    }


async def select_and_persist(
    db: AsyncSession,
    strategy: TradingStrategy,
    *,
    available_cash: Decimal,
    total_eval: Decimal,
    triggered_by: TriggerSource,
    loader: UniverseLoader = load_universe,
) -> SelectionResult:
    """파이프라인 실행 → 전략 컬럼/이력 저장.

    호출 전 strategy 는 현재 세션에서 영속(attached) 상태여야 한다.
    commit 은 caller 책임.
    """
    config = SelectorConfig.from_dict(strategy.auto_select_config or {})
    max_pct = _max_position_pct(strategy)

    result = await select_tickers(
        config,
        available_cash=available_cash,
        total_eval=total_eval,
        max_position_pct=max_pct,
        loader=loader,
    )

    now = datetime.now(timezone.utc)

    if result.selected:
        strategy.auto_selected_tickers = _serialize_selection(result, now=now)
    else:
        # 결과 0개 — 기존 tickers 유지하되 generated_at만 현재로 갱신해 is_stale
        # 재진입 루프와 lazy 이력 폭주를 막는다. 다음 lazy 재시도는 24h 이후.
        old = strategy.auto_selected_tickers or {}
        strategy.auto_selected_tickers = {
            "tickers": list(old.get("tickers") or []),
            "generated_at": now.isoformat(),
            "rule_version": old.get("rule_version") or result.rule_version,
            **({"details": old["details"]} if old.get("details") else {}),
        }
        logger.warning(
            "Auto ticker selection returned 0 tickers: strategy=%s, trigger=%s",
            strategy.id, triggered_by,
        )
        # lazy 트리거의 빈 결과는 이력 스팸이 되므로 스킵. manual/schedule는 audit 목적상 유지.
        if triggered_by == "lazy":
            return result

    history = AutoTickerSelection(
        strategy_id=strategy.id,
        generated_at=now,
        rule_version=result.rule_version,
        selected_tickers=[
            {
                "ticker": s.ticker,
                "name": s.name,
                "market": s.market,
                "price": str(s.price),
                "volume_value": s.volume_value,
                "score": round(s.score, 4),
                "reason": s.reason,
            }
            for s in result.selected
        ],
        excluded_sample=[asdict(e) for e in result.excluded_sample] or None,
        config_snapshot={
            "top_n": config.top_n,
            "market": config.market,
            "min_volume_value": config.min_volume_value,
            "blacklist": list(config.blacklist),
        },
        triggered_by=triggered_by,
    )
    db.add(history)
    return result


def get_auto_tickers(strategy: TradingStrategy) -> list[str]:
    """전략의 마지막 자동 선정 결과 ticker 리스트 (없으면 빈 리스트)."""
    stored = strategy.auto_selected_tickers or {}
    tickers = stored.get("tickers") or []
    return [str(t) for t in tickers if t]


async def _fetch_strategy_held_tickers(
    db: AsyncSession, strategy: TradingStrategy,
) -> set[str]:
    rows = await db.execute(
        select(TradingPosition.ticker).where(
            TradingPosition.strategy_id == strategy.id,
        )
    )
    return {row[0] for row in rows.all()}


async def resolve_strategy_tickers(
    db: AsyncSession,
    strategy: TradingStrategy,
    *,
    available_cash: Decimal,
    total_eval: Decimal,
    held_tickers: Iterable[str] | None = None,
    loader: UniverseLoader = load_universe,
) -> list[str]:
    """사이클 평가 대상 ticker 해석.

    - `auto_select_config.enabled` True + stale 이면 lazy 갱신 시도.
    - 최종 리스트 = `target_tickers`(수동) ∪ auto 선정 ∪ 보유중 종목.
      순서 보존, 중복 제거.

    Lazy 갱신 실패는 기존 리스트로 폴백(fail-open).
    commit 은 caller 책임.
    """
    if is_enabled(strategy) and is_stale(strategy):
        try:
            await select_and_persist(
                db,
                strategy,
                available_cash=available_cash,
                total_eval=total_eval,
                triggered_by="lazy",
                loader=loader,
            )
        except Exception:
            logger.exception(
                "Lazy auto-ticker refresh failed (continuing with previous list): "
                "strategy=%s", strategy.id,
            )

    if held_tickers is None:
        held_set = await _fetch_strategy_held_tickers(db, strategy)
    else:
        held_set = {t for t in held_tickers if t}

    seen: set[str] = set()
    out: list[str] = []

    for t in strategy.target_tickers or []:
        s = str(t).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    if is_enabled(strategy):
        for t in get_auto_tickers(strategy):
            if t not in seen:
                seen.add(t)
                out.append(t)

    for t in held_set:
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    return out
