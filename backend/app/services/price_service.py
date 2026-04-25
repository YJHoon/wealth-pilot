"""시세 조회 서비스 — 3모드(batch/delayed/realtime) 캐시 + 외부 API"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import httpx
import sentry_sdk
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus, AssetType
from app.models.exchange_rate import ExchangeRate
from app.schemas.price import ExchangeRateInfo, PriceMode, RefreshDetail
from app.services.alert_service import send_telegram_message

logger = logging.getLogger(__name__)

# 외부 API 소스명
EXCHANGE_RATE_SOURCE = "exchangerate-api"

# CoinGecko 코인 매핑 — 시총 상위 250개를 24h 주기로 캐싱.
# 17종 하드코딩에서 동적 조회로 전환. 호출 실패 시 lowercase fallback 유지.
_COINGECKO_TOP_PER_PAGE = 250
_COINGECKO_MAP_TTL_SEC = 86400
_coin_symbol_to_id: dict[str, str] = {}
_coin_map_fetched_at: float | None = None
_coin_map_lock = asyncio.Lock()


async def _refresh_coingecko_symbol_map() -> dict[str, str]:
    """CoinGecko /coins/markets 시총 상위에서 symbol→coin_id 매핑 추출."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": _COINGECKO_TOP_PER_PAGE,
        "page": 1,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    new_map: dict[str, str] = {}
    for coin in data:
        sym = (coin.get("symbol") or "").upper()
        coin_id = coin.get("id")
        # 같은 심볼이 여러 코인에 매핑되면 시총 상위(앞쪽)를 우선 채택
        if sym and coin_id and sym not in new_map:
            new_map[sym] = coin_id
    return new_map


async def _resolve_coingecko_id(symbol: str) -> str:
    """심볼(예: 'BTC') → CoinGecko coin_id(예: 'bitcoin').

    프로세스 레벨 캐시(24h)에서 조회. miss 또는 만료 시 시총 상위 250개를 갱신.
    매핑에 없으면 소문자 fallback(과거 동작 유지).
    """
    upper = symbol.upper()
    global _coin_map_fetched_at
    loop = asyncio.get_event_loop()
    now_ts = loop.time()

    def _is_stale() -> bool:
        return (
            not _coin_symbol_to_id
            or _coin_map_fetched_at is None
            or (now_ts - _coin_map_fetched_at) > _COINGECKO_MAP_TTL_SEC
        )

    if _is_stale():
        async with _coin_map_lock:
            now_ts = loop.time()
            if _is_stale():
                try:
                    new_map = await _refresh_coingecko_symbol_map()
                    _coin_symbol_to_id.clear()
                    _coin_symbol_to_id.update(new_map)
                    _coin_map_fetched_at = now_ts
                except Exception as e:
                    logger.warning(
                        "Failed to refresh CoinGecko symbol map: %s — falling back to lowercase",
                        e,
                    )

    if upper in _coin_symbol_to_id:
        return _coin_symbol_to_id[upper]
    return symbol.lower()


# 모드별 TTL (초)
_TTL_MAP: dict[PriceMode, int] = {
    PriceMode.BATCH: 86400,     # 24h
    PriceMode.DELAYED: 900,     # 15min
    PriceMode.REALTIME: 60,     # 1min
}


@dataclass
class CachedPrice:
    price: Decimal
    currency: str
    fetched_at: datetime
    is_stale: bool = False
    anomaly_flag: bool = False
    previous_price: Decimal | None = None


@dataclass
class PriceService:
    """시세 조회 서비스 — 싱글톤으로 사용."""

    _default_mode: PriceMode = PriceMode.BATCH
    _user_modes: dict[UUID, PriceMode] = field(default_factory=dict)
    _cache: dict[str, CachedPrice] = field(default_factory=dict)

    @property
    def mode(self) -> PriceMode:
        """기본 모드 반환 (하위 호환)."""
        return self._default_mode

    @mode.setter
    def mode(self, value: PriceMode) -> None:
        self._default_mode = value

    def get_mode(self, user_id: UUID | None = None) -> PriceMode:
        if user_id is None:
            return self._default_mode
        return self._user_modes.get(user_id, self._default_mode)

    def set_mode(self, mode: PriceMode, user_id: UUID | None = None) -> None:
        if user_id is None:
            self._default_mode = mode
        else:
            self._user_modes[user_id] = mode

    # ------------------------------------------------------------------
    # 캐시
    # ------------------------------------------------------------------

    def _ttl_seconds(self, user_id: UUID | None = None) -> int:
        return _TTL_MAP[self.get_mode(user_id)]

    def _is_cache_valid(self, key: str, *, user_id: UUID | None = None) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        if entry.anomaly_flag:
            return False
        elapsed = (datetime.now(timezone.utc) - entry.fetched_at).total_seconds()
        return elapsed < self._ttl_seconds(user_id)

    def get_cached(self, key: str) -> CachedPrice | None:
        return self._cache.get(key)

    def _set_cache(
        self,
        key: str,
        price: Decimal,
        currency: str,
        *,
        is_stale: bool = False,
    ) -> CachedPrice:
        previous = self._cache.get(key)
        entry = CachedPrice(
            price=price,
            currency=currency,
            fetched_at=datetime.now(timezone.utc),
            is_stale=is_stale,
            previous_price=previous.price if previous else None,
        )
        self._cache[key] = entry
        return entry

    # ------------------------------------------------------------------
    # 이상치 탐지
    # ------------------------------------------------------------------

    def _detect_anomaly(self, key: str, new_price: Decimal) -> bool:
        """전일 대비 ±50% 이상 변동이면 True."""
        prev = self._cache.get(key)
        if prev is None or prev.price == 0:
            return False
        change_ratio = abs(new_price - prev.price) / prev.price
        if change_ratio >= Decimal("0.5"):
            logger.warning(
                "Price anomaly detected for %s: %.4f -> %.4f (%.1f%%)",
                key, prev.price, new_price, float(change_ratio * 100),
            )
            return True
        return False

    # ------------------------------------------------------------------
    # ticker 자동 변환
    # ------------------------------------------------------------------

    @staticmethod
    def _to_yfinance_ticker(ticker: str, asset_type: str | None = None) -> list[str]:
        """DB ticker → yfinance ticker 후보 목록 반환.

        한국 주식(숫자 6자리)은 .KS(KOSPI), .KQ(KOSDAQ) 순으로 시도.
        이미 접미사가 있으면 그대로 사용.
        """
        # 이미 .KS/.KQ/.T 등 접미사가 붙어 있으면 그대로
        if "." in ticker:
            return [ticker]
        # 숫자 6자리 → 한국 주식
        if ticker.isdigit() and len(ticker) == 6:
            return [f"{ticker}.KS", f"{ticker}.KQ"]
        return [ticker]

    # ------------------------------------------------------------------
    # 주식 시세 (yfinance)
    # ------------------------------------------------------------------

    async def fetch_stock_price(
        self, ticker: str, *, user_id: UUID | None = None,
    ) -> CachedPrice:
        """yfinance로 주식 현재가 조회. 캐시 유효하면 즉시 반환."""
        cache_key = f"stock:{ticker}"

        if self._is_cache_valid(cache_key, user_id=user_id):
            return self._cache[cache_key]

        try:
            candidates = self._to_yfinance_ticker(ticker)

            # yfinance는 동기 라이브러리 → 이벤트 루프 차단 방지
            def _fetch_yf() -> tuple[Decimal, str]:
                last_err: Exception | None = None
                for candidate in candidates:
                    try:
                        tk = yf.Ticker(candidate)
                        info = tk.fast_info
                        return (
                            Decimal(str(info.last_price)),
                            getattr(info, "currency", "KRW") or "KRW",
                        )
                    except Exception as e:
                        last_err = e
                        continue
                raise last_err  # type: ignore[misc]

            price, currency = await asyncio.to_thread(_fetch_yf)

            anomaly = self._detect_anomaly(cache_key, price)
            if anomaly:
                logger.warning(
                    "Rejecting anomalous stock price for %s: %s",
                    ticker, price,
                )
                return CachedPrice(
                    price=price, currency=currency,
                    fetched_at=datetime.now(timezone.utc),
                    anomaly_flag=True,
                    previous_price=(self._cache[cache_key].price
                                    if cache_key in self._cache else None),
                )
            return self._set_cache(cache_key, price, currency)
        except Exception as exc:
            logger.error("Failed to fetch stock price for %s: %s", ticker, exc)
            sentry_sdk.capture_exception(exc)
            await send_telegram_message(
                f"⚠️ [시세 조회 실패] 주식 {ticker}: {exc}"
            )
            # 만료 캐시 반환
            cached = self._cache.get(cache_key)
            if cached:
                cached.is_stale = True
                return cached
            raise

    # ------------------------------------------------------------------
    # 암호화폐 시세 (CoinGecko)
    # ------------------------------------------------------------------

    async def fetch_crypto_price(
        self, symbol: str, *, user_id: UUID | None = None,
    ) -> CachedPrice:
        """CoinGecko 무료 API로 암호화폐 시세 조회."""
        cache_key = f"crypto:{symbol}"

        if self._is_cache_valid(cache_key, user_id=user_id):
            return self._cache[cache_key]

        coin_id = await _resolve_coingecko_id(symbol)
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": "krw"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            if coin_id not in data or "krw" not in data[coin_id]:
                raise ValueError(f"CoinGecko returned no data for {symbol} (coin_id={coin_id})")

            price = Decimal(str(data[coin_id]["krw"]))
            anomaly = self._detect_anomaly(cache_key, price)
            if anomaly:
                logger.warning(
                    "Rejecting anomalous crypto price for %s: %s",
                    symbol, price,
                )
                return CachedPrice(
                    price=price, currency="KRW",
                    fetched_at=datetime.now(timezone.utc),
                    anomaly_flag=True,
                    previous_price=(self._cache[cache_key].price
                                    if cache_key in self._cache else None),
                )
            return self._set_cache(cache_key, price, "KRW")
        except Exception as exc:
            logger.error("Failed to fetch crypto price for %s: %s", symbol, exc)
            sentry_sdk.capture_exception(exc)
            await send_telegram_message(
                f"⚠️ [시세 조회 실패] 암호화폐 {symbol}: {exc}"
            )
            cached = self._cache.get(cache_key)
            if cached:
                cached.is_stale = True
                return cached
            raise

    # ------------------------------------------------------------------
    # 환율 (ExchangeRate-API)
    # ------------------------------------------------------------------

    async def fetch_exchange_rate(
        self, from_currency: str, to_currency: str,
        *, user_id: UUID | None = None,
    ) -> CachedPrice:
        """ExchangeRate-API로 환율 조회."""
        cache_key = f"fx:{from_currency}:{to_currency}"

        if self._is_cache_valid(cache_key, user_id=user_id):
            return self._cache[cache_key]

        url = f"https://open.er-api.com/v6/latest/{from_currency}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            rates = data.get("rates", {})
            if to_currency not in rates:
                raise ValueError(
                    f"Exchange rate not found: {from_currency} -> {to_currency}"
                )

            rate = Decimal(str(rates[to_currency]))
            anomaly = self._detect_anomaly(cache_key, rate)
            if anomaly:
                logger.warning(
                    "Rejecting anomalous exchange rate for %s->%s: %s",
                    from_currency, to_currency, rate,
                )
                return CachedPrice(
                    price=rate, currency=to_currency,
                    fetched_at=datetime.now(timezone.utc),
                    anomaly_flag=True,
                    previous_price=(self._cache[cache_key].price
                                    if cache_key in self._cache else None),
                )
            return self._set_cache(cache_key, rate, to_currency)
        except Exception as exc:
            logger.error(
                "Failed to fetch exchange rate %s->%s: %s",
                from_currency, to_currency, exc,
            )
            sentry_sdk.capture_exception(exc)
            await send_telegram_message(
                f"⚠️ [환율 조회 실패] {from_currency}->{to_currency}: {exc}"
            )
            cached = self._cache.get(cache_key)
            if cached:
                cached.is_stale = True
                return cached
            raise

    # ------------------------------------------------------------------
    # 일괄 갱신
    # ------------------------------------------------------------------

    async def refresh_all_prices(
        self, db: AsyncSession, user_id: UUID,
    ) -> tuple[int, int, list[RefreshDetail], list[ExchangeRateInfo]]:
        """사용자의 active 자산 전체 시세 갱신.

        Returns:
            (success_count, fail_count, details, exchange_rates)
        """
        result = await db.execute(
            select(Asset).where(
                Asset.user_id == user_id,
                Asset.status == AssetStatus.ACTIVE,
                Asset.ticker.is_not(None),
                Asset.ticker != "",
            )
        )
        assets = result.scalars().all()

        details: list[RefreshDetail] = []
        success_count = 0
        fail_count = 0

        for asset in assets:
            try:
                if asset.type == AssetType.CRYPTO:
                    cached = await self.fetch_crypto_price(
                        asset.ticker, user_id=user_id,
                    )
                elif asset.type in (
                    AssetType.DOMESTIC_STOCK,
                    AssetType.FOREIGN_STOCK,
                ):
                    cached = await self.fetch_stock_price(
                        asset.ticker, user_id=user_id,
                    )
                else:
                    # cash, real_estate 등은 시세 조회 불필요
                    continue

                if cached.anomaly_flag:
                    logger.warning(
                        "Skipping DB update for %s due to anomaly flag",
                        asset.ticker,
                    )
                    details.append(RefreshDetail(
                        ticker=asset.ticker,
                        success=False,
                        currency=cached.currency,
                        error="anomaly detected — price not updated",
                    ))
                    fail_count += 1
                    continue

                asset.current_price = cached.price
                details.append(RefreshDetail(
                    ticker=asset.ticker,
                    success=True,
                    price=cached.price,
                    currency=cached.currency,
                ))
                success_count += 1
            except Exception as exc:
                logger.error(
                    "Failed to refresh price for asset %s (%s): %s",
                    asset.id, asset.ticker, exc,
                )
                details.append(RefreshDetail(
                    ticker=asset.ticker,
                    success=False,
                    error=str(exc),
                ))
                fail_count += 1

        # 환율 갱신
        exchange_rates = await self._refresh_exchange_rates(db, user_id=user_id)

        await db.commit()
        return success_count, fail_count, details, exchange_rates

    async def _refresh_exchange_rates(
        self, db: AsyncSession, *, user_id: UUID | None = None,
    ) -> list[ExchangeRateInfo]:
        """주요 환율 갱신 → exchange_rates 테이블 업데이트."""
        pairs = [("USD", "KRW"), ("EUR", "KRW"), ("JPY", "KRW")]
        results: list[ExchangeRateInfo] = []
        for from_cur, to_cur in pairs:
            try:
                cached = await self.fetch_exchange_rate(
                    from_cur, to_cur, user_id=user_id,
                )

                if cached.anomaly_flag:
                    logger.warning(
                        "Skipping exchange rate upsert for %s->%s due to anomaly",
                        from_cur, to_cur,
                    )
                    continue

                # savepoint로 개별 upsert 실패 격리
                async with db.begin_nested():
                    stmt = pg_insert(ExchangeRate).values(
                        from_currency=from_cur,
                        to_currency=to_cur,
                        rate=cached.price,
                        fetched_at=cached.fetched_at,
                        source=EXCHANGE_RATE_SOURCE,
                    ).on_conflict_do_update(
                        constraint="uq_exchange_rate_pair",
                        set_={
                            "rate": cached.price,
                            "fetched_at": cached.fetched_at,
                            "source": EXCHANGE_RATE_SOURCE,
                        },
                    )
                    await db.execute(stmt)
                results.append(ExchangeRateInfo(
                    from_currency=from_cur,
                    to_currency=to_cur,
                    rate=cached.price,
                    fetched_at=cached.fetched_at,
                    source=EXCHANGE_RATE_SOURCE,
                ))
            except Exception as exc:
                logger.error(
                    "Failed to refresh exchange rate %s->%s: %s",
                    from_cur, to_cur, exc,
                )
        return results


# 싱글톤 인스턴스
price_service = PriceService()
