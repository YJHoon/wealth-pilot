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
    async def test_fetch_crypto_price_success(self, svc: PriceService):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"bitcoin": {"krw": 95000000}}

        with patch("app.services.price_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc.fetch_crypto_price("bitcoin")

        assert result.price == Decimal("95000000")
        assert result.currency == "KRW"

    @pytest.mark.asyncio
    async def test_fetch_crypto_price_invalid_symbol(self, svc: PriceService):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}

        with patch("app.services.price_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch("app.services.price_service.send_telegram_message", new_callable=AsyncMock):
                with pytest.raises(ValueError, match="CoinGecko returned no data"):
                    await svc.fetch_crypto_price("invalidcoin")


# ── 환율 (ExchangeRate-API mock) ─────────────────────────────


class TestExchangeRate:
    @pytest.mark.asyncio
    async def test_fetch_exchange_rate_success(self, svc: PriceService):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "result": "success",
            "rates": {"KRW": 1350.5},
        }

        with patch("app.services.price_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc.fetch_exchange_rate("USD", "KRW")

        assert result.price == Decimal("1350.5")
        assert result.currency == "KRW"

    @pytest.mark.asyncio
    async def test_fetch_exchange_rate_missing_target(self, svc: PriceService):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"rates": {"EUR": 0.92}}

        with patch("app.services.price_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

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

        with patch("app.services.price_service.yf.Ticker", return_value=mock_ticker):
            # exchange rate 갱신도 mock
            with patch.object(svc, "_refresh_exchange_rates", new_callable=AsyncMock):
                success, fail, details = await svc.refresh_all_prices(
                    mock_db, uuid.uuid4(),
                )

        assert success == 1
        assert fail == 0
        assert len(details) == 1
        assert details[0].success is True
        assert mock_asset.current_price == Decimal("72500.0")

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
        async def mock_fetch_crypto(symbol):
            return CachedPrice(
                price=Decimal("95000000"),
                currency="KRW",
                fetched_at=datetime.now(timezone.utc),
            )

        # stock 실패 mock
        async def mock_fetch_stock(ticker):
            raise Exception("API down")

        with patch.object(svc, "fetch_crypto_price", side_effect=mock_fetch_crypto):
            with patch.object(svc, "fetch_stock_price", side_effect=mock_fetch_stock):
                with patch.object(svc, "_refresh_exchange_rates", new_callable=AsyncMock):
                    success, fail, details = await svc.refresh_all_prices(
                        mock_db, uuid.uuid4(),
                    )

        assert success == 1
        assert fail == 1
        assert details[0].success is True
        assert details[1].success is False


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
    async def test_get_crypto_price_endpoint(self, auth_client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"bitcoin": {"krw": 95000000}}

        with patch("app.services.price_service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await auth_client.get("/api/prices/crypto/bitcoin")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "bitcoin"

    @pytest.mark.asyncio
    async def test_get_exchange_rate_endpoint(self, auth_client):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"rates": {"KRW": 1350.5}}

        with patch("app.services.price_service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

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
                {"ticker": "005930.KS", "success": True, "price": "72500.0"},
                {"ticker": "bitcoin", "success": True, "price": "95000000"},
            ]),
        ):
            resp = await auth_client.post("/api/prices/refresh")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 2
        assert data["fail_count"] == 0

    @pytest.mark.asyncio
    async def test_refresh_endpoint_partial_failure(self, auth_client):
        with patch.object(
            price_service,
            "refresh_all_prices",
            new_callable=AsyncMock,
            return_value=(1, 1, [
                {"ticker": "005930.KS", "success": True, "price": "72500.0"},
                {"ticker": "BADTICKER", "success": False, "error": "API down"},
            ]),
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
