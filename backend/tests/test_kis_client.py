"""KIS API 클라이언트 테스트 — httpx mock 기반"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.trading import TradingMode
from app.services.kis_client import _THROTTLE_STATE, _TOKEN_CACHE, KISClient, KISClientError


@pytest.fixture(autouse=True)
def _clear_kis_state():
    _TOKEN_CACHE.clear()
    _THROTTLE_STATE.clear()
    yield
    _TOKEN_CACHE.clear()
    _THROTTLE_STATE.clear()


def _make_client(mode=TradingMode.PAPER, **kwargs):
    return KISClient(
        app_key="test_key",
        app_secret="test_secret",
        account_number="12345678",
        account_product_code="01",
        mode=mode,
        **kwargs,
    )


class TestTrId:
    def test_paper_mode_converts_prefix(self):
        client = _make_client(mode=TradingMode.PAPER)
        assert client._tr_id("TTTC0802U") == "VTTC0802U"

    def test_live_mode_keeps_prefix(self):
        client = _make_client(mode=TradingMode.LIVE)
        assert client._tr_id("TTTC0802U") == "TTTC0802U"

    def test_non_t_prefix_unchanged(self):
        client = _make_client(mode=TradingMode.PAPER)
        assert client._tr_id("FHKST01010100") == "FHKST01010100"


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "tok123",
            "expires_in": 86400,
        }
        mock_resp.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_resp)

        token = await client.authenticate()
        assert token == "tok123"
        assert client.access_token == "tok123"
        assert client.token_expires_at is not None

    @pytest.mark.asyncio
    async def test_authenticate_non_200_with_valid_json_raises_kis_error(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"error_description": "invalid appkey"}

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(KISClientError) as exc_info:
            await client.authenticate()
        assert exc_info.value.status_code == 401
        assert exc_info.value.response_data == {"error_description": "invalid appkey"}

    @pytest.mark.asyncio
    async def test_authenticate_non_200_with_malformed_json_raises_kis_error(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.json.side_effect = ValueError("malformed json")

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(KISClientError) as exc_info:
            await client.authenticate()
        assert exc_info.value.status_code == 500
        assert exc_info.value.response_data == {}

    @pytest.mark.asyncio
    async def test_ensure_token_skips_when_valid(self):
        client = _make_client(
            access_token="existing",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        client.authenticate = AsyncMock()
        await client._ensure_token()
        client.authenticate.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_token_refreshes_when_expired(self):
        client = _make_client(
            access_token="old",
            token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        client.authenticate = AsyncMock(return_value="new_tok")
        await client._ensure_token()
        client.authenticate.assert_called_once()


class TestRequest:
    @pytest.mark.asyncio
    async def test_kis_error_raises(self):
        client = _make_client(
            access_token="tok",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rt_cd": "1", "msg1": "에러 메시지"}
        mock_resp.status_code = 200

        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(KISClientError, match="에러 메시지"):
            await client._request("GET", "/test", tr_id="TEST")

    @pytest.mark.asyncio
    async def test_successful_request(self):
        client = _make_client(
            access_token="tok",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rt_cd": "0", "output": {"price": "50000"}}
        mock_resp.status_code = 200

        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        result = await client._request("GET", "/test", tr_id="TEST")
        assert result["rt_cd"] == "0"

    @pytest.mark.asyncio
    async def test_rate_limit_message_is_retried_then_succeeds(self):
        """KIS rate limit 류 메시지(rt_cd != 0)는 backoff 후 재시도되어 회복된다."""
        client = _make_client(
            access_token="tok",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        rate_limit_resp = MagicMock()
        rate_limit_resp.json.return_value = {
            "rt_cd": "1", "msg1": "초당 거래건수를 초과하였습니다.",
        }
        rate_limit_resp.status_code = 200

        success_resp = MagicMock()
        success_resp.json.return_value = {"rt_cd": "0", "output": {"ok": True}}
        success_resp.status_code = 200

        client._client = AsyncMock()
        client._client.get = AsyncMock(
            side_effect=[rate_limit_resp, success_resp],
        )

        with patch("app.services.kis_client.asyncio.sleep", new=AsyncMock()):
            result = await client._request(
                "GET", "/test", tr_id="TEST", retries=2,
            )
        assert result["rt_cd"] == "0"
        assert client._client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_egw_gateway_error_is_retried(self):
        """rt_cd 가 EGW* 인 게이트웨이 일시 에러도 재시도 대상."""
        client = _make_client(
            access_token="tok",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        egw_resp = MagicMock()
        egw_resp.json.return_value = {
            "rt_cd": "EGW00201", "msg1": "게이트웨이 일시 오류",
        }
        egw_resp.status_code = 200

        success_resp = MagicMock()
        success_resp.json.return_value = {"rt_cd": "0", "output": {"ok": True}}
        success_resp.status_code = 200

        client._client = AsyncMock()
        client._client.get = AsyncMock(side_effect=[egw_resp, success_resp])

        with patch("app.services.kis_client.asyncio.sleep", new=AsyncMock()):
            result = await client._request(
                "GET", "/test", tr_id="TEST", retries=2,
            )
        assert result["rt_cd"] == "0"

    @pytest.mark.asyncio
    async def test_non_retryable_kis_error_raises_immediately(self):
        """rate limit 가 아닌 일반 KIS 에러는 retry 없이 즉시 raise (회귀 방지)."""
        client = _make_client(
            access_token="tok",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        biz_err_resp = MagicMock()
        biz_err_resp.json.return_value = {
            "rt_cd": "1", "msg1": "주문가능금액 부족",
        }
        biz_err_resp.status_code = 200
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=biz_err_resp)

        with pytest.raises(KISClientError, match="주문가능금액 부족"):
            await client._request("GET", "/test", tr_id="TEST", retries=3)
        # retry 없이 1회만 호출돼야 함
        assert client._client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted_eventually_raises(self):
        """retry 한도까지 모두 rate limit 이면 마지막엔 KISClientError raise."""
        client = _make_client(
            access_token="tok",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        rate_limit_resp = MagicMock()
        rate_limit_resp.json.return_value = {
            "rt_cd": "1", "msg1": "초당 거래건수를 초과하였습니다.",
        }
        rate_limit_resp.status_code = 200
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=rate_limit_resp)

        with patch("app.services.kis_client.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(KISClientError, match="초당 거래건수"):
                await client._request(
                    "GET", "/test", tr_id="TEST", retries=2,
                )
        # 1 + retries=3 회 호출
        assert client._client.get.await_count == 3


class TestGetCurrentPrice:
    @pytest.mark.asyncio
    async def test_parses_price_data(self):
        client = _make_client()
        client._request = AsyncMock(return_value={
            "output": {
                "stck_prpr": "65000",
                "hts_kor_isnm": "삼성전자",
                "acml_vol": "12345678",
                "prdy_ctrt": "1.23",
                "stck_hgpr": "66000",
                "stck_lwpr": "64000",
            }
        })

        result = await client.get_current_price("005930")
        assert result["price"] == Decimal("65000")
        assert result["name"] == "삼성전자"
        assert result["volume"] == 12345678
        assert result["change_rate"] == Decimal("1.23")


class TestGetPriceHistory:
    @pytest.mark.asyncio
    async def test_returns_sorted_list(self):
        client = _make_client()
        # KIS returns newest first
        client._request = AsyncMock(return_value={
            "output": [
                {"stck_bsop_date": "20240102", "stck_clpr": "66000", "stck_oprc": "65000", "stck_hgpr": "67000", "stck_lwpr": "64000", "acml_vol": "100"},
                {"stck_bsop_date": "20240101", "stck_clpr": "65000", "stck_oprc": "64000", "stck_hgpr": "66000", "stck_lwpr": "63000", "acml_vol": "200"},
            ]
        })

        result = await client.get_price_history("005930", count=2)
        assert len(result) == 2
        # Should be oldest first
        assert result[0]["date"] == "20240101"
        assert result[1]["date"] == "20240102"
        assert result[0]["close"] == Decimal("65000")


class TestPlaceOrder:
    @pytest.mark.asyncio
    async def test_buy_order(self):
        client = _make_client()
        client._request = AsyncMock(return_value={
            "output": {"ODNO": "0001234", "ORD_TMD": "20240101"}
        })

        result = await client.place_order("buy", "005930", 10, order_type="market")
        assert result["order_id"] == "0001234"

        call_args = client._request.call_args
        assert call_args.kwargs["tr_id"] == "TTTC0802U"

    @pytest.mark.asyncio
    async def test_sell_order(self):
        client = _make_client()
        client._request = AsyncMock(return_value={
            "output": {"ODNO": "0001235", "ORD_TMD": "20240101"}
        })

        result = await client.place_order("sell", "005930", 5)
        assert result["order_id"] == "0001235"

        call_args = client._request.call_args
        assert call_args.kwargs["tr_id"] == "TTTC0801U"


class TestGetBalance:
    @pytest.mark.asyncio
    async def test_parses_balance(self):
        client = _make_client()
        client._request = AsyncMock(return_value={
            "output1": [
                {
                    "pdno": "005930",
                    "prdt_name": "삼성전자",
                    "hldg_qty": "10",
                    "pchs_avg_pric": "65000",
                    "prpr": "66000",
                    "evlu_amt": "660000",
                    "evlu_pfls_amt": "10000",
                    "evlu_pfls_rt": "1.54",
                },
            ],
            "output2": [
                {
                    "dnca_tot_amt": "5000000",
                    "scts_evlu_amt": "660000",
                    "evlu_pfls_smtl_amt": "10000",
                },
            ],
        })

        result = await client.get_balance()
        assert result["cash"] == Decimal("5000000")
        assert result["total_eval"] == Decimal("660000")
        assert len(result["holdings"]) == 1
        assert result["holdings"][0]["ticker"] == "005930"
        assert result["holdings"][0]["quantity"] == 10

    @pytest.mark.asyncio
    async def test_skips_zero_quantity_holdings(self):
        client = _make_client()
        client._request = AsyncMock(return_value={
            "output1": [
                {"pdno": "005930", "hldg_qty": "0", "pchs_avg_pric": "65000", "prpr": "66000", "evlu_amt": "0", "evlu_pfls_amt": "0", "evlu_pfls_rt": "0"},
            ],
            "output2": [{"dnca_tot_amt": "5000000", "scts_evlu_amt": "0", "evlu_pfls_smtl_amt": "0"}],
        })

        result = await client.get_balance()
        assert len(result["holdings"]) == 0


class TestProperties:
    def test_mode_property(self):
        client = _make_client(mode=TradingMode.PAPER)
        assert client.mode == TradingMode.PAPER

    def test_base_url_by_mode(self):
        paper = _make_client(mode=TradingMode.PAPER)
        live = _make_client(mode=TradingMode.LIVE)
        assert "openapivts" in paper._base_url
        assert "openapi.koreainvestment" in live._base_url
