"""시세 조회 서비스 — 3모드(batch/delayed/realtime) 캐시 + 외부 API"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx
import sentry_sdk
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus, AssetType
from app.models.exchange_rate import ExchangeRate
from app.schemas.price import PriceMode, RefreshDetail
from app.services.alert_service import send_telegram_message

logger = logging.getLogger(__name__)

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
            # yfinance는 동기 라이브러리 → 이벤트 루프 차단 방지
            def _fetch_yf() -> tuple[Decimal, str]:
                tk = yf.Ticker(ticker)
                info = tk.fast_info
                return (
                    Decimal(str(info.last_price)),
                    getattr(info, "currency", "KRW") or "KRW",
                )

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

        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": symbol, "vs_currencies": "krw"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            if symbol not in data or "krw" not in data[symbol]:
                raise ValueError(f"CoinGecko returned no data for {symbol}")

            price = Decimal(str(data[symbol]["krw"]))
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
    ) -> tuple[int, int, list[RefreshDetail]]:
        """사용자의 active 자산 전체 시세 갱신.

        Returns:
            (success_count, fail_count, details)
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
                    cached = await self.fetch_crypto_price(asset.ticker)
                elif asset.type in (
                    AssetType.DOMESTIC_STOCK,
                    AssetType.FOREIGN_STOCK,
                ):
                    cached = await self.fetch_stock_price(asset.ticker)
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
                        error="anomaly detected — price not updated",
                    ))
                    fail_count += 1
                    continue

                asset.current_price = cached.price
                details.append(RefreshDetail(
                    ticker=asset.ticker,
                    success=True,
                    price=cached.price,
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
        await self._refresh_exchange_rates(db)

        await db.commit()
        return success_count, fail_count, details

    async def _refresh_exchange_rates(self, db: AsyncSession) -> None:
        """주요 환율 갱신 → exchange_rates 테이블 업데이트."""
        pairs = [("USD", "KRW"), ("EUR", "KRW"), ("JPY", "KRW")]
        for from_cur, to_cur in pairs:
            try:
                cached = await self.fetch_exchange_rate(from_cur, to_cur)

                # atomic upsert (INSERT ... ON CONFLICT DO UPDATE)
                stmt = pg_insert(ExchangeRate).values(
                    from_currency=from_cur,
                    to_currency=to_cur,
                    rate=cached.price,
                    fetched_at=cached.fetched_at,
                    source="exchangerate-api",
                ).on_conflict_do_update(
                    index_elements=["from_currency", "to_currency"],
                    set_={
                        "rate": cached.price,
                        "fetched_at": cached.fetched_at,
                        "source": "exchangerate-api",
                    },
                )
                await db.execute(stmt)
            except Exception as exc:
                logger.error(
                    "Failed to refresh exchange rate %s->%s: %s",
                    from_cur, to_cur, exc,
                )


# 싱글톤 인스턴스
price_service = PriceService()
