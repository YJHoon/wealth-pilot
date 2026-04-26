"""자동 종목 선정 파이프라인 (순수 함수 중심).

MVP 룰(`v1-volume-rank`): 거래대금 상위에서 시드 한도 및 사용자 제외를
반영해 top N을 고른다. KIS 호출 없이 FinanceDataReader 단일 소스로 처리.

단계:
  1. `load_universe` — 시장 전체 종목 + 거래대금/현재가 로드
  2. `filter_universe_type` — 우선주/SPAC 제외
  3. `filter_by_min_volume` — 최소 일일 거래대금 미만 컷
  4. `filter_by_seed` — 1주 가격 > min(가용현금, 비중한도) 컷
  5. `filter_by_blacklist` — 사용자 blacklist 컷
  6. `rank_and_top` — 거래대금 내림차순 정렬 후 top N

각 단계는 순수 함수. `load_universe`만 I/O를 가지므로 테스트에서는
`load_universe_fn`을 주입해 대체한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable, Literal, Sequence

import FinanceDataReader as fdr

logger = logging.getLogger(__name__)

RULE_VERSION = "v1-volume-rank"
Market = Literal["KOSPI", "KOSDAQ"]
MarketFilter = Literal["KOSPI", "KOSDAQ", "ALL"]

# 기본값 — 사용자가 미설정 시 적용.
DEFAULT_TOP_N = 10
DEFAULT_MIN_VOLUME_VALUE = 100  # 100억원
DEFAULT_MARKET: MarketFilter = "ALL"
MIN_TOP_N = 3
MAX_TOP_N = 30


@dataclass(frozen=True, slots=True)
class StockCandidate:
    ticker: str
    name: str
    market: Market
    price: Decimal  # 현재가 (전일 종가)
    volume_value: int  # 거래대금 (KRW)
    market_cap: int  # 시가총액 (KRW)


@dataclass(frozen=True, slots=True)
class SelectedTicker:
    ticker: str
    name: str
    market: Market
    price: Decimal
    volume_value: int
    score: float  # 0~1 정규화 (거래대금 기준)
    reason: str


@dataclass(frozen=True, slots=True)
class ExcludedTicker:
    ticker: str
    name: str
    reason: str  # "price_over_seed" | "blacklist" | "below_min_volume" | "preferred" | "spac"


@dataclass(frozen=True, slots=True)
class SelectionResult:
    rule_version: str
    selected: list[SelectedTicker]
    excluded_sample: list[ExcludedTicker] = field(default_factory=list)


# ──────────────────────────────────────────────
# 1. Universe 로드 (유일한 I/O)
# ──────────────────────────────────────────────

UniverseLoader = Callable[[MarketFilter], Awaitable[list[StockCandidate]]]


def _load_universe_sync(market: MarketFilter) -> list[StockCandidate]:
    """동기 I/O — 반드시 asyncio.to_thread로 호출."""
    markets: tuple[str, ...]
    if market == "ALL":
        markets = ("KOSPI", "KOSDAQ")
    else:
        markets = (market,)

    out: list[StockCandidate] = []
    for m in markets:
        df = fdr.StockListing(m)
        for _, row in df.iterrows():
            code = str(row.get("Code", "")).strip()
            name = str(row.get("Name", "")).strip()
            if not code or not name:
                continue
            try:
                close = Decimal(str(row.get("Close", 0) or 0))
                if not close.is_finite() or close <= 0:
                    continue
                amount = int(row.get("Amount", 0) or 0)
                marcap = int(row.get("Marcap", 0) or 0)
                if amount <= 0:
                    continue
            except (ValueError, TypeError, InvalidOperation, ArithmeticError):
                continue
            out.append(
                StockCandidate(
                    ticker=code,
                    name=name,
                    market=m,  # type: ignore[arg-type]
                    price=close,
                    volume_value=amount,
                    market_cap=marcap,
                )
            )
    return out


async def load_universe(market: MarketFilter) -> list[StockCandidate]:
    return await asyncio.to_thread(_load_universe_sync, market)


# ──────────────────────────────────────────────
# 2~5. 순수 필터 함수
# ──────────────────────────────────────────────

_PREFERRED_SUFFIXES: tuple[str, ...] = ("우", "우B", "우C", "우(전환)")


def _is_preferred(name: str) -> bool:
    return any(name.endswith(s) for s in _PREFERRED_SUFFIXES)


def _is_spac(name: str) -> bool:
    return "스팩" in name


def filter_universe_type(
    candidates: Sequence[StockCandidate],
) -> tuple[list[StockCandidate], list[ExcludedTicker]]:
    kept: list[StockCandidate] = []
    excluded: list[ExcludedTicker] = []
    for c in candidates:
        if _is_preferred(c.name):
            excluded.append(ExcludedTicker(c.ticker, c.name, "preferred"))
        elif _is_spac(c.name):
            excluded.append(ExcludedTicker(c.ticker, c.name, "spac"))
        else:
            kept.append(c)
    return kept, excluded


def filter_by_min_volume(
    candidates: Sequence[StockCandidate],
    min_volume_value: int,
) -> tuple[list[StockCandidate], list[ExcludedTicker]]:
    if min_volume_value <= 0:
        return list(candidates), []
    kept: list[StockCandidate] = []
    excluded: list[ExcludedTicker] = []
    for c in candidates:
        if c.volume_value < min_volume_value:
            excluded.append(ExcludedTicker(c.ticker, c.name, "below_min_volume"))
        else:
            kept.append(c)
    return kept, excluded


def filter_by_seed(
    candidates: Sequence[StockCandidate],
    *,
    available_cash: Decimal,
    total_eval: Decimal,
    max_position_pct: Decimal,
) -> tuple[list[StockCandidate], list[ExcludedTicker]]:
    """1주 가격이 시드·비중 한도를 초과하는 종목 제외.

    상한 = min(available_cash, total_eval × max_position_pct).
    total_eval 이 0이면 available_cash 만 사용 (신규 계좌 대응).
    """
    pos_cap = total_eval * max_position_pct if total_eval > 0 else available_cash
    limit = min(available_cash, pos_cap) if pos_cap > 0 else available_cash
    if limit <= 0:
        # 전부 제외 — caller 가 설정 오류를 잡도록 반환
        return [], [
            ExcludedTicker(c.ticker, c.name, "price_over_seed") for c in candidates
        ]
    kept: list[StockCandidate] = []
    excluded: list[ExcludedTicker] = []
    for c in candidates:
        if c.price > limit:
            excluded.append(ExcludedTicker(c.ticker, c.name, "price_over_seed"))
        else:
            kept.append(c)
    return kept, excluded


def filter_by_blacklist(
    candidates: Sequence[StockCandidate],
    blacklist: Sequence[str],
) -> tuple[list[StockCandidate], list[ExcludedTicker]]:
    if not blacklist:
        return list(candidates), []
    bl = {b.strip() for b in blacklist if b and b.strip()}
    kept: list[StockCandidate] = []
    excluded: list[ExcludedTicker] = []
    for c in candidates:
        if c.ticker in bl:
            excluded.append(ExcludedTicker(c.ticker, c.name, "blacklist"))
        else:
            kept.append(c)
    return kept, excluded


def rank_and_top(
    candidates: Sequence[StockCandidate],
    top_n: int,
) -> list[SelectedTicker]:
    if top_n <= 0 or not candidates:
        return []
    sorted_c = sorted(candidates, key=lambda x: x.volume_value, reverse=True)
    picks = sorted_c[:top_n]
    max_vol = picks[0].volume_value or 1
    result: list[SelectedTicker] = []
    for rank, c in enumerate(picks, start=1):
        score = float(c.volume_value) / float(max_vol)
        result.append(
            SelectedTicker(
                ticker=c.ticker,
                name=c.name,
                market=c.market,
                price=c.price,
                volume_value=c.volume_value,
                score=score,
                reason=f"거래대금 {rank}위",
            )
        )
    return result


# ──────────────────────────────────────────────
# 6. 파이프라인 오케스트레이션
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SelectorConfig:
    top_n: int
    market: MarketFilter
    min_volume_value: int
    blacklist: tuple[str, ...]

    @classmethod
    def from_dict(cls, d: dict | None) -> "SelectorConfig":
        d = d or {}
        top_n_raw = d.get("top_n")
        top_n = int(top_n_raw) if top_n_raw is not None else DEFAULT_TOP_N
        top_n = max(MIN_TOP_N, min(MAX_TOP_N, top_n))
        market_raw = str(d.get("market") or DEFAULT_MARKET).upper()
        if market_raw not in ("KOSPI", "KOSDAQ", "ALL"):
            market_raw = DEFAULT_MARKET
        min_vol_raw = d.get("min_volume_value")
        min_vol = (
            int(min_vol_raw) if min_vol_raw is not None else DEFAULT_MIN_VOLUME_VALUE
        )
        min_vol = max(0, min_vol)
        bl_raw = d.get("blacklist") or []
        blacklist = tuple(str(x).strip() for x in bl_raw if str(x).strip())
        return cls(
            top_n=top_n,
            market=market_raw,  # type: ignore[arg-type]
            min_volume_value=min_vol,
            blacklist=blacklist,
        )


async def select_tickers(
    config: SelectorConfig,
    *,
    available_cash: Decimal,
    total_eval: Decimal,
    max_position_pct: Decimal,
    loader: UniverseLoader = load_universe,
    excluded_sample_limit: int = 20,
) -> SelectionResult:
    """전체 파이프라인. 각 단계는 순수 함수이고 I/O는 loader 하나."""
    universe = await loader(config.market)
    excluded_all: list[ExcludedTicker] = []

    kept, ex = filter_universe_type(universe)
    excluded_all.extend(ex)

    kept, ex = filter_by_min_volume(kept, config.min_volume_value)
    excluded_all.extend(ex)

    kept, ex = filter_by_seed(
        kept,
        available_cash=available_cash,
        total_eval=total_eval,
        max_position_pct=max_position_pct,
    )
    excluded_all.extend(ex)

    kept, ex = filter_by_blacklist(kept, config.blacklist)
    excluded_all.extend(ex)

    selected = rank_and_top(kept, config.top_n)

    # 디버깅용 샘플 — preferred/spac 같은 대량 제외를 먼저 자르고 상위만 저장.
    priority_reasons = {"price_over_seed", "blacklist", "below_min_volume"}
    priority = [e for e in excluded_all if e.reason in priority_reasons]
    fallback = [e for e in excluded_all if e.reason not in priority_reasons]
    sample = (priority + fallback)[:excluded_sample_limit]

    return SelectionResult(
        rule_version=RULE_VERSION,
        selected=selected,
        excluded_sample=sample,
    )
