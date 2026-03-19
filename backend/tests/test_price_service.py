"""시세 조회 서비스 테스트 — 외부 API 모두 mock"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus, AssetType, Currency
from app.schemas.price import PriceMode
from app.services.price_service import CachedPrice, PriceService, price_service


@pytest.fixture
def svc():
    """매 테스트마다 새 PriceService 인스턴스."""
    return PriceService()


@pytest.fixture(autouse=True)
def _reset_global_price_service():
    """글로벌 price_service 상태를 매 테스트마다 초기화."""
    original_mode = price_service._default_mode
    original_user_modes = price_service._user_modes.copy()
    original_cache = price_service._cache.copy()
    yield
    price_service._default_mode = original_mode
    price_service._user_modes = original_user_modes
    price_service._cache = original_cache


@pytest.fixture
def mock_httpx_client():
    """httpx.AsyncClient mock factory."""
    def _create(response_data: dict):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = response_data

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client
    return _create


# ── 캐시 히트/미스 ──────────────────────────────────────────────


class TestCache:
    def test_cache_miss_returns_none(self, svc: PriceService):
        assert svc.get_cached("stock:AAPL") is None

    def test_cache_hit_within_ttl(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("150"), "USD")
        assert svc._is_cache_valid("stock:AAPL") is True

    def test_cache_expired(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("150"), "USD")
        # 강제로 과거 시간 설정
        svc._cache["stock:AAPL"].fetched_at = datetime.now(
            timezone.utc
        ) - timedelta(hours=25)
        assert svc._is_cache_valid("stock:AAPL") is False

    def test_delayed_mode_shorter_ttl(self, svc: PriceService):
        svc.mode = PriceMode.DELAYED
        svc._set_cache("stock:AAPL", Decimal("150"), "USD")
        # 16분 전 → 만료
        svc._cache["stock:AAPL"].fetched_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=16)
        assert svc._is_cache_valid("stock:AAPL") is False

    def test_realtime_mode_shortest_ttl(self, svc: PriceService):
        svc.mode = PriceMode.REALTIME
        svc._set_cache("stock:AAPL", Decimal("150"), "USD")
        # 2분 전 → 만료
        svc._cache["stock:AAPL"].fetched_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=2)
        assert svc._is_cache_valid("stock:AAPL") is False

    def test_per_user_mode_ttl(self, svc: PriceService):
        """유저별 모드에 따라 TTL이 다르게 적용되는지 확인."""
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        svc.set_mode(PriceMode.BATCH, user_a)
        svc.set_mode(PriceMode.REALTIME, user_b)

        svc._set_cache("stock:AAPL", Decimal("150"), "USD")
        # 2분 전 → batch에서는 유효, realtime에서는 만료
        svc._cache["stock:AAPL"].fetched_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=2)
        assert svc._is_cache_valid("stock:AAPL", user_id=user_a) is True
        assert svc._is_cache_valid("stock:AAPL", user_id=user_b) is False


# ── 이상치 탐지 ──────────────────────────────────────────────


class TestAnomaly:
    def test_no_anomaly_first_fetch(self, svc: PriceService):
        assert svc._detect_anomaly("stock:AAPL", Decimal("150")) is False

    def test_no_anomaly_within_threshold(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("100"), "USD")
        # 40% 변동 — 임계값 이하
        assert svc._detect_anomaly("stock:AAPL", Decimal("140")) is False

    def test_anomaly_over_threshold(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("100"), "USD")
        # 60% 변동 — 임계값 초과
        assert svc._detect_anomaly("stock:AAPL", Decimal("160")) is True

    def test_anomaly_drop(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("100"), "USD")
        # 50% 하락 — 임계값 정확히
        assert svc._detect_anomaly("stock:AAPL", Decimal("50")) is True

    def test_no_anomaly_just_below_threshold_drop(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("100"), "USD")
        # 49% 하락 — 임계값 미만
        assert svc._detect_anomaly("stock:AAPL", Decimal("51")) is False

    def test_no_anomaly_just_below_threshold_rise(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("100"), "USD")
        # 49% 상승 — 임계값 미만
        assert svc._detect_anomaly("stock:AAPL", Decimal("149")) is False

    @pytest.mark.asyncio
    async def test_anomaly_does_not_overwrite_cache(self, svc: PriceService):
        """이상치 감지 시 기존 캐시가 보존되는지 확인."""
        svc._set_cache("stock:TEST", Decimal("100"), "USD")
        original_cached = svc._cache["stock:TEST"]
        # 캐시 만료시켜서 재조회 유도
        original_cached.fetched_at = datetime.now(timezone.utc) - timedelta(hours=25)

        mock_info = MagicMock()
        mock_info.last_price = 200.0  # 100% 상승 → 이상치
        mock_info.currency = "USD"
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("app.services.price_service.yf.Ticker", return_value=mock_ticker):
            result = await svc.fetch_stock_price("TEST")

        # 반환값은 anomaly_flag=True
        assert result.anomaly_flag is True
        assert result.price == Decimal("200.0")
        # 캐시는 기존 정상 가격 유지
        assert svc._cache["stock:TEST"].price == Decimal("100")
        assert svc._cache["stock:TEST"] is original_cached


# ── 주식 시세 (yfinance mock) ────────────────────────────────


class TestStockPrice:
    @pytest.mark.asyncio
    async def test_fetch_stock_price_success(self, svc: PriceService):
        mock_info = MagicMock()
        mock_info.last_price = 72500.0
        mock_info.currency = "KRW"

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("app.services.price_service.yf.Ticker", return_value=mock_ticker):
            result = await svc.fetch_stock_price("005930.KS")

        assert result.price == Decimal("72500.0")
        assert result.currency == "KRW"
        assert result.is_stale is False

    @pytest.mark.asyncio
    async def test_fetch_stock_price_cached(self, svc: PriceService):
        svc._set_cache("stock:AAPL", Decimal("150"), "USD")

        # yfinance를 호출하지 않아야 함
        with patch("app.services.price_service.yf.Ticker") as mock_yf:
            result = await svc.fetch_stock_price("AAPL")
            mock_yf.assert_not_called()

        assert result.price == Decimal("150")

    @pytest.mark.asyncio
    async def test_fetch_stock_price_failure_returns_stale(self, svc: PriceService):
        # 먼저 캐시 설정 (만료 상태)
        svc._set_cache("stock:FAIL", Decimal("100"), "USD")
        svc._cache["stock:FAIL"].fetched_at = datetime.now(
            timezone.utc
        ) - timedelta(hours=25)

        with patch(
            "app.services.price_service.yf.Ticker",
            side_effect=Exception("API down"),
        ):
            with patch("app.services.price_service.send_telegram_message", new_callable=AsyncMock):
                result = await svc.fetch_stock_price("FAIL")

        assert result.price == Decimal("100")
        assert result.is_stale is True

    @pytest.mark.asyncio
    async def test_fetch_stock_price_failure_no_cache_raises(self, svc: PriceService):
        with patch(
            "app.services.price_service.yf.Ticker",
            side_effect=Exception("API down"),
        ):
            with patch("app.services.price_service.send_telegram_message", new_callable=AsyncMock):
                with pytest.raises(Exception, match="API down"):
                    await svc.fetch_stock_price("NOEXIST")


# ── 암호화폐 시세 (CoinGecko mock) ──────────────────────────


class TestCryptoPrice:
    @pytest.mark.asyncio
    async def test_fetch_crypto_price_success(self, svc: PriceService, mock_httpx_client):
        mock_client = mock_httpx_client({"bitcoin": {"krw": 95000000}})

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc.fetch_crypto_price("bitcoin")

        assert result.price == Decimal("95000000")
        assert result.currency == "KRW"

    @pytest.mark.asyncio
    async def test_fetch_crypto_price_invalid_symbol(self, svc: PriceService, mock_httpx_client):
        mock_client = mock_httpx_client({})

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.price_service.send_telegram_message", new_callable=AsyncMock):
                with pytest.raises(ValueError, match="CoinGecko returned no data"):
                    await svc.fetch_crypto_price("invalidcoin")


# ── 환율 (ExchangeRate-API mock) ─────────────────────────────


class TestExchangeRate:
    @pytest.mark.asyncio
    async def test_fetch_exchange_rate_success(self, svc: PriceService, mock_httpx_client):
        mock_client = mock_httpx_client({"result": "success", "rates": {"KRW": 1350.5}})

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc.fetch_exchange_rate("USD", "KRW")

        assert result.price == Decimal("1350.5")
        assert result.currency == "KRW"

    @pytest.mark.asyncio
    async def test_fetch_exchange_rate_missing_target(self, svc: PriceService, mock_httpx_client):
        mock_client = mock_httpx_client({"rates": {"EUR": 0.92}})

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.price_service.send_telegram_message", new_callable=AsyncMock):
                with pytest.raises(ValueError, match="Exchange rate not found"):
                    await svc.fetch_exchange_rate("USD", "KRW")


# ── 모드 전환 ────────────────────────────────────────────────


class TestModeSwitch:
    def test_default_mode_is_batch(self, svc: PriceService):
        assert svc.mode == PriceMode.BATCH

    def test_switch_to_delayed(self, svc: PriceService):
        svc.mode = PriceMode.DELAYED
        assert svc.mode == PriceMode.DELAYED
        assert svc._ttl_seconds() == 900

    def test_switch_to_realtime(self, svc: PriceService):
        svc.mode = PriceMode.REALTIME
        assert svc.mode == PriceMode.REALTIME
        assert svc._ttl_seconds() == 60


# ── 일괄 갱신 (DB mock) ──────────────────────────────────────


class TestRefreshAll:
    @pytest.mark.asyncio
    async def test_refresh_all_success(self, svc: PriceService):
        """active 주식 자산 1개 갱신 성공."""
        mock_asset = MagicMock(spec=Asset)
        mock_asset.id = uuid.uuid4()
        mock_asset.type = AssetType.DOMESTIC_STOCK
        mock_asset.ticker = "005930.KS"
        mock_asset.current_price = None

        # DB mock
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_asset]

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()

        # yfinance mock
        mock_info = MagicMock()
        mock_info.last_price = 72500.0
        mock_info.currency = "KRW"
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        user_id = uuid.uuid4()

        with patch("app.services.price_service.yf.Ticker", return_value=mock_ticker):
            # exchange rate 갱신도 mock
            with patch.object(
                svc, "_refresh_exchange_rates", new_callable=AsyncMock, return_value=[],
            ) as mock_refresh_rates:
                success, fail, details, ex_rates = await svc.refresh_all_prices(
                    mock_db, user_id,
                )

        assert success == 1
        assert fail == 0
        assert len(details) == 1
        assert details[0].success is True
        assert details[0].currency == "KRW"
        assert mock_asset.current_price == Decimal("72500.0")
        assert ex_rates == []
        mock_refresh_rates.assert_awaited_once_with(mock_db, user_id=user_id)

    @pytest.mark.asyncio
    async def test_refresh_all_partial_failure(self, svc: PriceService):
        """2개 자산 중 1개 실패."""
        asset_ok = MagicMock(spec=Asset)
        asset_ok.id = uuid.uuid4()
        asset_ok.type = AssetType.CRYPTO
        asset_ok.ticker = "bitcoin"
        asset_ok.current_price = None

        asset_fail = MagicMock(spec=Asset)
        asset_fail.id = uuid.uuid4()
        asset_fail.type = AssetType.FOREIGN_STOCK
        asset_fail.ticker = "BADTICKER"
        asset_fail.current_price = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [asset_ok, asset_fail]

        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()

        # crypto 성공 mock
        async def mock_fetch_crypto(symbol, *, user_id=None):
            return CachedPrice(
                price=Decimal("95000000"),
                currency="KRW",
                fetched_at=datetime.now(timezone.utc),
            )

        # stock 실패 mock
        async def mock_fetch_stock(ticker, *, user_id=None):
            raise Exception("API down")

        user_id = uuid.uuid4()

        with patch.object(svc, "fetch_crypto_price", side_effect=mock_fetch_crypto):
            with patch.object(svc, "fetch_stock_price", side_effect=mock_fetch_stock):
                with patch.object(
                    svc, "_refresh_exchange_rates", new_callable=AsyncMock, return_value=[],
                ) as mock_refresh_rates:
                    success, fail, details, _ex_rates = await svc.refresh_all_prices(
                        mock_db, user_id,
                    )

        assert success == 1
        assert fail == 1
        assert details[0].success is True
        assert details[0].currency == "KRW"
        mock_refresh_rates.assert_awaited_once_with(mock_db, user_id=user_id)
        assert details[1].success is False


# ── 환율 갱신 (DB mock) ───────────────────────────────────────


class TestRefreshExchangeRates:
    @staticmethod
    def _make_savepoint_db():
        """begin_nested를 지원하는 mock DB 세션 생성."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()
        # begin_nested → async context manager (savepoint)
        mock_nested = AsyncMock()
        mock_nested.__aenter__ = AsyncMock(return_value=mock_nested)
        mock_nested.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested.return_value = mock_nested
        return mock_db

    @pytest.mark.asyncio
    async def test_refresh_exchange_rates_success(self, svc: PriceService, mock_httpx_client):
        """_refresh_exchange_rates가 주요 환율을 갱신하고 결과를 반환하는지 확인."""
        mock_client = mock_httpx_client({
            "result": "success",
            "rates": {"KRW": 1350.5, "EUR": 0.92, "JPY": 110.0},
        })

        mock_db = self._make_savepoint_db()
        user_id = uuid.uuid4()

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            results = await svc._refresh_exchange_rates(mock_db, user_id=user_id)

        assert len(results) == 3
        currencies = {(r.from_currency, r.to_currency) for r in results}
        assert ("USD", "KRW") in currencies
        assert ("EUR", "KRW") in currencies
        assert ("JPY", "KRW") in currencies
        # DB upsert가 호출되었는지 확인
        assert mock_db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_refresh_exchange_rates_partial_failure(self, svc: PriceService):
        """일부 환율 갱신 실패 시 성공한 것만 반환."""
        async def mock_fetch(from_cur, to_cur, **kwargs):
            if from_cur == "EUR":
                raise Exception("API error")
            return CachedPrice(
                price=Decimal("1350.5"),
                currency=to_cur,
                fetched_at=datetime.now(timezone.utc),
            )

        mock_db = self._make_savepoint_db()

        with patch.object(svc, "fetch_exchange_rate", side_effect=mock_fetch):
            results = await svc._refresh_exchange_rates(mock_db)

        # EUR 실패 → 2개만 반환
        assert len(results) == 2
        currencies = {r.from_currency for r in results}
        assert "EUR" not in currencies


# ── API 엔드포인트 (통합 테스트) ──────────────────────────────


class TestPriceEndpoints:
    @pytest.mark.asyncio
    async def test_get_stock_price_endpoint(self, auth_client):
        mock_info = MagicMock()
        mock_info.last_price = 72500.0
        mock_info.currency = "KRW"
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("app.services.price_service.yf.Ticker", return_value=mock_ticker):
            resp = await auth_client.get("/api/prices/stock/005930.KS")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "005930.KS"
        assert Decimal(data["price"]) == Decimal("72500.0")

    @pytest.mark.asyncio
    async def test_get_crypto_price_endpoint(self, auth_client, mock_httpx_client):
        mock_client = mock_httpx_client({"bitcoin": {"krw": 95000000}})

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            resp = await auth_client.get("/api/prices/crypto/bitcoin")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "bitcoin"

    @pytest.mark.asyncio
    async def test_get_exchange_rate_endpoint(self, auth_client, mock_httpx_client):
        mock_client = mock_httpx_client({"rates": {"KRW": 1350.5}})

        with patch("app.services.price_service.httpx.AsyncClient", return_value=mock_client):
            resp = await auth_client.get(
                "/api/prices/exchange-rate",
                params={"from": "USD", "to": "KRW"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["from_currency"] == "USD"
        assert data["to_currency"] == "KRW"

    @pytest.mark.asyncio
    async def test_get_mode_endpoint(self, auth_client):
        resp = await auth_client.get("/api/prices/mode")
        assert resp.status_code == 200
        assert resp.json()["current_mode"] == "batch"

    @pytest.mark.asyncio
    async def test_update_mode_endpoint(self, auth_client):
        resp = await auth_client.put(
            "/api/prices/mode",
            json={"mode": "delayed"},
        )
        assert resp.status_code == 200
        assert resp.json()["current_mode"] == "delayed"

    @pytest.mark.asyncio
    async def test_refresh_endpoint_success(self, auth_client):
        with patch.object(
            price_service,
            "refresh_all_prices",
            new_callable=AsyncMock,
            return_value=(2, 0, [
                {"ticker": "005930.KS", "success": True, "price": "72500.0", "currency": "KRW"},
                {"ticker": "bitcoin", "success": True, "price": "95000000", "currency": "KRW"},
            ], []),
        ):
            resp = await auth_client.post("/api/prices/refresh")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 2
        assert data["fail_count"] == 0
        assert data["exchange_rates"] == []

    @pytest.mark.asyncio
    async def test_refresh_endpoint_partial_failure(self, auth_client):
        with patch.object(
            price_service,
            "refresh_all_prices",
            new_callable=AsyncMock,
            return_value=(1, 1, [
                {"ticker": "005930.KS", "success": True, "price": "72500.0", "currency": "KRW"},
                {"ticker": "BADTICKER", "success": False, "error": "API down"},
            ], []),
        ):
            resp = await auth_client.post("/api/prices/refresh")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 1
        assert data["fail_count"] == 1
        assert len(data["details"]) == 2

    @pytest.mark.asyncio
    async def test_stock_price_api_failure_returns_502(self, auth_client):
        with patch(
            "app.services.price_service.yf.Ticker",
            side_effect=Exception("API down"),
        ):
            with patch("app.services.price_service.send_telegram_message", new_callable=AsyncMock):
                resp = await auth_client.get("/api/prices/stock/BADTICKER")

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_get_exchange_rates_endpoint(self, auth_client):
        """GET /api/prices/exchange-rates 벌크 환율 조회."""
        resp = await auth_client.get("/api/prices/exchange-rates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
