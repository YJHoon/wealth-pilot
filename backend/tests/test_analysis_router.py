"""투자 분석 + 관심종목 라우터 테스트

8개 엔드포인트 + 소유권 위반 테스트.
분석 엔드포인트는 stock_analysis_service를 mock하여 검증.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

from app.models.analysis import Watchlist
from app.models.user import User
from app.schemas.analysis import (
    FundamentalAnalysisResponse,
    TechnicalAnalysisResponse,
    TradingSignalAction,
    TradingSignalsResponse,
    ValuationSignal,
)
from app.services.stock_analysis_service import StockAnalysisError


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_fundamental() -> FundamentalAnalysisResponse:
    return FundamentalAnalysisResponse(
        ticker="005930",
        market="KRX",
        company_name="삼성전자",
        sector="Technology",
        per=Decimal("12.5"),
        pbr=Decimal("1.2"),
        roe=Decimal("15.3"),
        eps=Decimal("5000"),
        current_price=Decimal("75000"),
        valuation_signal=ValuationSignal.FAIR,
        data_source="yfinance",
    )


def _make_technical() -> TechnicalAnalysisResponse:
    return TechnicalAnalysisResponse(
        ticker="005930",
        market="KRX",
        rsi=Decimal("55"),
        macd=Decimal("100"),
        macd_signal=Decimal("80"),
        macd_histogram=Decimal("20"),
        current_price=Decimal("75000"),
        data_source="yfinance",
    )


def _make_signals() -> TradingSignalsResponse:
    return TradingSignalsResponse(
        ticker="005930",
        market="KRX",
        action=TradingSignalAction.HOLD,
        confidence=Decimal("52"),
        risk_level="중",
        reasons=["적정 가치 범위", "RSI 중립 (55)"],
        fundamental_score=Decimal("50"),
        technical_score=Decimal("55"),
        current_price=Decimal("75000"),
        data_source="yfinance",
    )


@pytest_asyncio.fixture
async def _cleanup_watchlists(db_session: AsyncSession, mock_user: User):
    """테스트 후 watchlists 정리."""
    yield
    await db_session.execute(
        delete(Watchlist).where(Watchlist.user_id == mock_user.id)
    )
    await db_session.commit()


# ──────────────────────────────────────────────
# 기본적 분석 — GET /api/analysis/stock/{ticker}
# ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestFundamentalAnalysis:
    @patch(
        "app.routers.analysis.get_fundamental_analysis",
        new_callable=AsyncMock,
    )
    async def test_success(self, mock_fn, auth_client: AsyncClient):
        mock_fn.return_value = _make_fundamental()
        resp = await auth_client.get(
            "/api/analysis/stock/005930", params={"market": "KRX"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "005930"
        assert data["company_name"] == "삼성전자"
        assert data["valuation_signal"] == "fair"
        mock_fn.assert_awaited_once_with("005930", "KRX")

    @patch(
        "app.routers.analysis.get_fundamental_analysis",
        new_callable=AsyncMock,
    )
    async def test_service_error_returns_502(self, mock_fn, auth_client: AsyncClient):
        mock_fn.side_effect = StockAnalysisError("종목 정보 조회 실패: INVALID")
        resp = await auth_client.get(
            "/api/analysis/stock/INVALID", params={"market": "NASDAQ"},
        )
        assert resp.status_code == 502
        assert "조회 실패" in resp.json()["detail"]

    @patch(
        "app.routers.analysis.get_fundamental_analysis",
        new_callable=AsyncMock,
    )
    async def test_default_market_krx(self, mock_fn, auth_client: AsyncClient):
        """market 파라미터 생략 시 KRX 기본값."""
        mock_fn.return_value = _make_fundamental()
        resp = await auth_client.get("/api/analysis/stock/005930")
        assert resp.status_code == 200
        mock_fn.assert_awaited_once_with("005930", "KRX")


# ──────────────────────────────────────────────
# 기술적 분석 — GET /api/analysis/stock/{ticker}/technical
# ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestTechnicalAnalysis:
    @patch(
        "app.routers.analysis.get_technical_analysis",
        new_callable=AsyncMock,
    )
    async def test_success(self, mock_fn, auth_client: AsyncClient):
        mock_fn.return_value = _make_technical()
        resp = await auth_client.get(
            "/api/analysis/stock/005930/technical", params={"market": "KRX"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "005930"
        assert Decimal(data["rsi"]) == Decimal("55")
        mock_fn.assert_awaited_once_with("005930", "KRX")

    @patch(
        "app.routers.analysis.get_technical_analysis",
        new_callable=AsyncMock,
    )
    async def test_service_error_returns_502(self, mock_fn, auth_client: AsyncClient):
        mock_fn.side_effect = StockAnalysisError("시세 조회 실패")
        resp = await auth_client.get(
            "/api/analysis/stock/INVALID/technical", params={"market": "KRX"},
        )
        assert resp.status_code == 502


# ──────────────────────────────────────────────
# 매매 시그널 — GET /api/analysis/stock/{ticker}/signals
# ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestTradingSignals:
    @patch(
        "app.routers.analysis.get_trading_signals",
        new_callable=AsyncMock,
    )
    async def test_success(self, mock_fn, auth_client: AsyncClient):
        mock_fn.return_value = _make_signals()
        resp = await auth_client.get(
            "/api/analysis/stock/005930/signals", params={"market": "KRX"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "hold"
        assert len(data["reasons"]) == 2
        mock_fn.assert_awaited_once_with("005930", "KRX")

    @patch(
        "app.routers.analysis.get_trading_signals",
        new_callable=AsyncMock,
    )
    async def test_service_error_returns_502(self, mock_fn, auth_client: AsyncClient):
        mock_fn.side_effect = StockAnalysisError("조회 실패")
        resp = await auth_client.get(
            "/api/analysis/stock/INVALID/signals",
        )
        assert resp.status_code == 502


# ──────────────────────────────────────────────
# 시뮬레이션 — POST /api/analysis/simulate
# ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestSimulate:
    async def test_returns_501(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/analysis/simulate")
        assert resp.status_code == 501
        assert "준비 중" in resp.json()["detail"]


# ──────────────────────────────────────────────
# 관심종목 CRUD — /api/analysis/watchlist
# ──────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.usefixtures("_cleanup_watchlists")
class TestWatchlistCRUD:

    _BODY = {
        "ticker": "005930",
        "market": "KRX",
        "target_buy_price": "60000",
        "target_sell_price": "90000",
        "alert_threshold_pct": "5.00",
        "notes": "삼성전자 관심 종목",
    }

    async def _create(self, client: AsyncClient) -> dict:
        resp = await client.post("/api/analysis/watchlist", json=self._BODY)
        assert resp.status_code == 201
        return resp.json()

    # --- LIST ---
    async def test_list_empty(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/analysis/watchlist")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_items(self, auth_client: AsyncClient):
        await self._create(auth_client)
        resp = await auth_client.get("/api/analysis/watchlist")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["ticker"] == "005930"

    # --- CREATE ---
    async def test_create_success(self, auth_client: AsyncClient):
        data = await self._create(auth_client)
        assert data["ticker"] == "005930"
        assert data["market"] == "KRX"
        assert Decimal(data["target_buy_price"]) == Decimal("60000")
        assert Decimal(data["target_sell_price"]) == Decimal("90000")
        assert data["notes"] == "삼성전자 관심 종목"

    async def test_create_duplicate_409(self, auth_client: AsyncClient):
        await self._create(auth_client)
        resp = await auth_client.post("/api/analysis/watchlist", json=self._BODY)
        assert resp.status_code == 409
        assert "이미 등록" in resp.json()["detail"]

    async def test_create_without_optional_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/analysis/watchlist", json={
            "ticker": "AAPL",
            "market": "NASDAQ",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["target_buy_price"] is None
        assert data["target_sell_price"] is None

    async def test_create_validation_error(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/analysis/watchlist", json={
            "ticker": "005930",
            "market": "KRX",
            "target_buy_price": "-100",
        })
        assert resp.status_code == 422

    # --- DB encryption verification ---
    async def test_db_encryption(
        self, auth_client: AsyncClient, db_session: AsyncSession, mock_user: User,
    ):
        data = await self._create(auth_client)
        result = await db_session.execute(
            select(Watchlist).where(Watchlist.id == data["id"])
        )
        watchlist = result.scalar_one()
        # DB에 저장된 암호화 값은 원본 숫자와 다름
        assert watchlist.target_buy_price != "60000"
        assert watchlist.target_sell_price != "90000"
        # 비암호화 필드는 그대로
        assert watchlist.ticker == "005930"

    # --- UPDATE ---
    async def test_update_success(self, auth_client: AsyncClient):
        data = await self._create(auth_client)
        resp = await auth_client.put(
            f"/api/analysis/watchlist/{data['id']}",
            json={"target_buy_price": "55000", "notes": "수정됨"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert Decimal(updated["target_buy_price"]) == Decimal("55000")
        assert updated["notes"] == "수정됨"

    async def test_update_not_found(self, auth_client: AsyncClient):
        fake_id = str(uuid4())
        resp = await auth_client.put(
            f"/api/analysis/watchlist/{fake_id}",
            json={"notes": "없는 종목"},
        )
        assert resp.status_code == 404

    # --- DELETE ---
    async def test_delete_success(self, auth_client: AsyncClient):
        data = await self._create(auth_client)
        resp = await auth_client.delete(f"/api/analysis/watchlist/{data['id']}")
        assert resp.status_code == 204

        # 삭제 후 목록에서 제거 확인
        resp = await auth_client.get("/api/analysis/watchlist")
        assert len(resp.json()) == 0

    async def test_delete_not_found(self, auth_client: AsyncClient):
        fake_id = str(uuid4())
        resp = await auth_client.delete(f"/api/analysis/watchlist/{fake_id}")
        assert resp.status_code == 404


# ──────────────────────────────────────────────
# 소유권 위반 테스트
# ──────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.usefixtures("_cleanup_watchlists")
class TestWatchlistOwnership:
    """다른 사용자의 관심종목에 접근 불가 검증."""

    async def test_update_other_user_watchlist_404(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        other_user: User,
    ):
        """다른 사용자의 관심종목 수정 시도 → 404."""
        # other_user 소유의 관심종목 직접 생성
        watchlist = Watchlist(
            user_id=other_user.id,
            ticker="AAPL",
            market="NASDAQ",
        )
        db_session.add(watchlist)
        await db_session.commit()
        await db_session.refresh(watchlist)

        resp = await auth_client.put(
            f"/api/analysis/watchlist/{watchlist.id}",
            json={"notes": "탈취 시도"},
        )
        assert resp.status_code == 404

        # cleanup
        await db_session.execute(
            delete(Watchlist).where(Watchlist.user_id == other_user.id)
        )
        await db_session.commit()

    async def test_delete_other_user_watchlist_404(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        other_user: User,
    ):
        """다른 사용자의 관심종목 삭제 시도 → 404."""
        watchlist = Watchlist(
            user_id=other_user.id,
            ticker="TSLA",
            market="NASDAQ",
        )
        db_session.add(watchlist)
        await db_session.commit()
        await db_session.refresh(watchlist)

        resp = await auth_client.delete(f"/api/analysis/watchlist/{watchlist.id}")
        assert resp.status_code == 404

        # cleanup
        await db_session.execute(
            delete(Watchlist).where(Watchlist.user_id == other_user.id)
        )
        await db_session.commit()

    async def test_list_only_own_watchlist(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        other_user: User,
    ):
        """목록 조회 시 다른 사용자의 관심종목은 보이지 않음."""
        watchlist = Watchlist(
            user_id=other_user.id,
            ticker="GOOG",
            market="NASDAQ",
        )
        db_session.add(watchlist)
        await db_session.commit()

        resp = await auth_client.get("/api/analysis/watchlist")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        # cleanup
        await db_session.execute(
            delete(Watchlist).where(Watchlist.user_id == other_user.id)
        )
        await db_session.commit()
