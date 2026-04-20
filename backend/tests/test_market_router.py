"""시장 라우터 테스트 — /api/market/search."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.stock_master import StockInfo


@pytest.mark.asyncio
class TestStockSearch:
    @patch("app.routers.market.ensure_loaded", new_callable=AsyncMock)
    @patch("app.routers.market.search")
    async def test_success(self, mock_search, mock_load, auth_client: AsyncClient):
        mock_search.return_value = [
            StockInfo(ticker="005930", name="삼성전자", market="KOSPI"),
            StockInfo(ticker="005935", name="삼성전자우", market="KOSPI"),
        ]
        resp = await auth_client.get("/api/market/search", params={"q": "삼성전자"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "삼성전자"
        assert len(data["results"]) == 2
        assert data["results"][0] == {
            "ticker": "005930", "name": "삼성전자", "market": "KOSPI",
        }
        mock_load.assert_awaited_once()
        mock_search.assert_called_once_with("삼성전자", limit=20)

    @patch("app.routers.market.ensure_loaded", new_callable=AsyncMock)
    @patch("app.routers.market.search")
    async def test_custom_limit(self, mock_search, mock_load, auth_client: AsyncClient):
        mock_search.return_value = []
        resp = await auth_client.get(
            "/api/market/search", params={"q": "카", "limit": 5},
        )
        assert resp.status_code == 200
        mock_search.assert_called_once_with("카", limit=5)

    async def test_requires_query(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/market/search")
        assert resp.status_code == 422  # q 누락

    async def test_empty_query_rejected(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/market/search", params={"q": ""})
        assert resp.status_code == 422  # min_length=1

    @patch("app.routers.market.ensure_loaded", new_callable=AsyncMock)
    async def test_master_load_failure_returns_502(
        self, mock_load, auth_client: AsyncClient,
    ):
        mock_load.side_effect = RuntimeError("krx down")
        resp = await auth_client.get("/api/market/search", params={"q": "삼성"})
        assert resp.status_code == 502
        assert "종목 마스터" in resp.json()["detail"]
