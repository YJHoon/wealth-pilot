"""한국 주식 종목 마스터 서비스

KOSPI/KOSDAQ 상장종목의 이름↔코드 매핑을 FinanceDataReader로 로드하고
메모리에 캐시한다. 종목명/코드 검색에 사용한다.

캐시는 프로세스 메모리 기준이며 TTL(24h)로 자동 갱신된다. FastAPI 워커가
여러 개여도 각자 자기 캐시를 갖지만, 데이터 변동이 크지 않고 재로드도
수 초 내라 문제 없다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

import FinanceDataReader as fdr

logger = logging.getLogger(__name__)


Market = Literal["KOSPI", "KOSDAQ", "KONEX"]


@dataclass(frozen=True, slots=True)
class StockInfo:
    ticker: str
    name: str
    market: Market


_CACHE: dict[str, StockInfo] = {}
_ORDER: list[StockInfo] = []  # 검색 스캔용(리스트 순회가 dict.values()보다 조금 빠르고 순서 안정적)
_LOADED_AT: float = 0.0
_TTL_SEC = 24 * 60 * 60
_LOCK = asyncio.Lock()


def _load_sync() -> tuple[dict[str, StockInfo], list[StockInfo]]:
    """동기 I/O — 반드시 `asyncio.to_thread`로 호출."""
    df = fdr.StockListing("KRX")
    # 필수 컬럼만 사용. FinanceDataReader 버전에 따라 'Market' 값이
    # 'KOSPI'/'KOSDAQ'/'KONEX' 외 'KOSPI GLOBAL' 등이 섞여 있을 수 있다.
    cache: dict[str, StockInfo] = {}
    order: list[StockInfo] = []
    for _, row in df[["Code", "Name", "Market"]].iterrows():
        code = str(row["Code"]).strip()
        name = str(row["Name"]).strip()
        market_raw = str(row["Market"]).strip().upper()
        if not code or not name:
            continue
        if market_raw.startswith("KOSPI"):
            market: Market = "KOSPI"
        elif market_raw.startswith("KOSDAQ"):
            market = "KOSDAQ"
        elif market_raw.startswith("KONEX"):
            market = "KONEX"
        else:
            continue
        info = StockInfo(ticker=code, name=name, market=market)
        cache[code] = info
        order.append(info)
    return cache, order


async def ensure_loaded(force: bool = False) -> None:
    """TTL 만료 시 캐시 갱신. 동시 호출 시 하나만 실제 로드."""
    global _CACHE, _ORDER, _LOADED_AT
    now = time.time()
    if not force and _CACHE and (now - _LOADED_AT) < _TTL_SEC:
        return
    async with _LOCK:
        # 더블체크 — 락 대기 중 다른 코루틴이 로드 완료했을 수 있음
        if not force and _CACHE and (time.time() - _LOADED_AT) < _TTL_SEC:
            return
        logger.info("Loading KRX stock master via FinanceDataReader…")
        try:
            cache, order = await asyncio.to_thread(_load_sync)
        except Exception:
            logger.exception("Stock master load failed")
            raise
        if not cache:
            logger.warning("Stock master load returned empty dataset; keeping prior cache")
            return
        _CACHE = cache
        _ORDER = order
        _LOADED_AT = time.time()
        logger.info("Stock master loaded: %d tickers", len(cache))


def get_by_ticker(ticker: str) -> StockInfo | None:
    return _CACHE.get(ticker.strip())


def search(query: str, limit: int = 20) -> list[StockInfo]:
    """이름 또는 종목코드로 검색. 우선순위:

    1. 종목코드 정확 일치
    2. 이름 prefix 일치 (입력 기준)
    3. 이름 substring 일치
    4. 종목코드 prefix 일치

    이름 검색은 대소문자/공백 무시. 정렬 후 `limit`개 반환.
    """
    q = query.strip()
    if not q:
        return []
    q_upper_nospace = q.upper().replace(" ", "")
    results: list[tuple[int, StockInfo]] = []  # (priority, info) — 낮을수록 먼저
    for info in _ORDER:
        name_key = info.name.upper().replace(" ", "")
        if info.ticker == q:
            priority = 0
        elif name_key.startswith(q_upper_nospace):
            priority = 1
        elif q_upper_nospace in name_key:
            priority = 2
        elif info.ticker.startswith(q):
            priority = 3
        else:
            continue
        results.append((priority, info))
    results.sort(key=lambda t: (t[0], t[1].name))
    return [info for _, info in results[:limit]]
