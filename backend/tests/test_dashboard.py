"""대시보드 API 테스트"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_log import AccessLog
from app.models.asset_snapshot import AssetSnapshot
from app.models.user import User
from app.services.crypto_service import encrypt_decimal


@pytest.mark.asyncio
class TestDashboardSummary:
    async def test_empty_portfolio(self, auth_client: AsyncClient):
        """자산 없을 때 요약 데이터가 0으로 반환된다."""
        resp = await auth_client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["total_value_krw"]) == 0
        assert data["by_type"] == {}
        assert float(data["pnl"]["total"]) == 0
        assert float(data["pnl"]["realized"]) == 0
        assert float(data["pnl"]["unrealized"]) == 0

    async def test_cash_asset_summary(self, auth_client: AsyncClient):
        """현금 자산만 있을 때 총 자산 = 현금 수량."""
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "5000000", "purchase_price": "5000000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["total_value_krw"]) == 5_000_000
        assert "cash" in data["by_type"]
        assert float(data["by_type"]["cash"]["ratio"]) == 1.0

    async def test_stock_with_current_price(self, auth_client: AsyncClient):
        """주식 자산 — 현재가 있으면 현재가 * 수량으로 평가."""
        await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "삼성전자", "currency": "KRW",
            "quantity": "10", "purchase_price": "70000",
            "current_price": "80000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        # 10 * 80000 = 800,000
        assert float(data["total_value_krw"]) == 800_000
        # 미실현: 800,000 - 700,000 = 100,000
        assert float(data["pnl"]["unrealized"]) == 100_000

    async def test_stock_without_current_price(self, auth_client: AsyncClient):
        """현재가 없으면 매입가 기준 평가."""
        await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "SK하이닉스", "currency": "KRW",
            "quantity": "5", "purchase_price": "120000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        # 5 * 120000 = 600,000
        assert float(data["total_value_krw"]) == 600_000

    async def test_mixed_assets_type_breakdown(self, auth_client: AsyncClient):
        """복수 유형 자산 — 유형별 비중이 올바르게 계산된다."""
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "1000000", "purchase_price": "1000000",
        })
        await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "삼성전자", "currency": "KRW",
            "quantity": "10", "purchase_price": "100000",
            "current_price": "100000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        # 총: 1,000,000 + 1,000,000 = 2,000,000
        assert float(data["total_value_krw"]) == 2_000_000
        assert float(data["by_type"]["cash"]["ratio"]) == 0.5
        assert float(data["by_type"]["domestic_stock"]["ratio"]) == 0.5

    async def test_group_breakdown(self, auth_client: AsyncClient):
        """그룹별 비중이 올바르게 계산된다."""
        group_resp = await auth_client.post("/api/groups", json={"name": "국내주식"})
        group_id = group_resp.json()["id"]

        await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "삼성전자", "currency": "KRW",
            "quantity": "10", "purchase_price": "100000",
            "current_price": "100000", "group_id": group_id,
        })
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "1000000", "purchase_price": "1000000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        assert group_id in data["by_group"]
        assert "ungrouped" in data["by_group"]
        assert data["by_group"]["ungrouped"]["name"] == "미분류"

    async def test_sold_asset_excluded_from_total(self, auth_client: AsyncClient):
        """매도 자산은 총 자산에서 제외되고, 실현 손익에만 반영된다."""
        # 자산 생성 후 매도
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "매도주식", "currency": "KRW",
            "quantity": "10", "purchase_price": "50000",
            "current_price": "50000",
        })
        asset_id = resp.json()["id"]
        await auth_client.post(f"/api/assets/{asset_id}/sell", json={
            "sold_price": "60000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        # 매도로 생긴 현금(600,000)만 총 자산에 반영
        # 매도 자산 자체는 제외
        assert float(data["pnl"]["realized"]) == 100_000  # (60000-50000)*10

    async def test_previous_day_change_with_snapshot(
        self, auth_client: AsyncClient, mock_user: User, db_session: AsyncSession
    ):
        """어제 스냅샷이 있으면 전일 대비 변동이 계산된다."""
        # 어제 스냅샷 생성
        yesterday = date.today() - timedelta(days=1)
        snapshot = AssetSnapshot(
            user_id=mock_user.id,
            total_value_krw=encrypt_decimal(Decimal("1000000")),
            breakdown=None,
            snapshot_date=yesterday,
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        db_session.add(snapshot)
        await db_session.commit()

        # 오늘 자산: 1,200,000
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "1200000", "purchase_price": "1200000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        assert float(data["previous_day_change"]["amount"]) == 200_000
        assert float(data["previous_day_change"]["ratio"]) == 0.2

    async def test_previous_day_change_no_snapshot(self, auth_client: AsyncClient):
        """어제 스냅샷이 없으면 전일 대비 변동 = 0."""
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "1000000", "purchase_price": "1000000",
        })

        resp = await auth_client.get("/api/dashboard/summary")
        data = resp.json()
        assert float(data["previous_day_change"]["amount"]) == 0
        assert float(data["previous_day_change"]["ratio"]) == 0

    async def test_audit_log_created(
        self, auth_client: AsyncClient, mock_user: User, db_session: AsyncSession
    ):
        """대시보드 조회 시 액세스 로그가 기록된다."""
        resp = await auth_client.get("/api/dashboard/summary")
        assert resp.status_code == 200

        result = await db_session.execute(
            select(AccessLog).where(
                AccessLog.user_id == mock_user.id,
                AccessLog.action == "dashboard_view",
            )
        )
        logs = result.scalars().all()
        assert len(logs) >= 1


@pytest.mark.asyncio
class TestDashboardHistory:
    async def test_empty_history(self, auth_client: AsyncClient):
        """스냅샷이 없으면 빈 리스트."""
        resp = await auth_client.get("/api/dashboard/history", params={"period": "1M"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_points"] == []
        assert data["total_count"] == 0
        assert data["period"] == "1M"

    async def test_history_with_snapshots(
        self, auth_client: AsyncClient, mock_user: User, db_session: AsyncSession
    ):
        """스냅샷이 있으면 기간 내 데이터 반환."""
        now = datetime.now(timezone.utc)
        for i in range(5):
            d = date.today() - timedelta(days=i)
            snapshot = AssetSnapshot(
                user_id=mock_user.id,
                total_value_krw=encrypt_decimal(Decimal(str(1_000_000 + i * 10_000))),
                breakdown={"by_type": {"cash": {"ratio": 1.0}}},
                snapshot_date=d,
                expires_at=now + timedelta(days=365),
            )
            db_session.add(snapshot)
        await db_session.commit()

        resp = await auth_client.get("/api/dashboard/history", params={"period": "1M"})
        data = resp.json()
        assert data["total_count"] == 5
        # 날짜 오름차순
        dates = [dp["date"] for dp in data["data_points"]]
        assert dates == sorted(dates)

    async def test_history_filters_by_period(
        self, auth_client: AsyncClient, mock_user: User, db_session: AsyncSession
    ):
        """기간 외 스냅샷은 제외된다."""
        now = datetime.now(timezone.utc)
        # 40일 전 (1M 범위 밖)
        old_snapshot = AssetSnapshot(
            user_id=mock_user.id,
            total_value_krw=encrypt_decimal(Decimal("900000")),
            breakdown=None,
            snapshot_date=date.today() - timedelta(days=40),
            expires_at=now + timedelta(days=365),
        )
        # 10일 전 (1M 범위 내)
        recent_snapshot = AssetSnapshot(
            user_id=mock_user.id,
            total_value_krw=encrypt_decimal(Decimal("1000000")),
            breakdown=None,
            snapshot_date=date.today() - timedelta(days=10),
            expires_at=now + timedelta(days=365),
        )
        db_session.add_all([old_snapshot, recent_snapshot])
        await db_session.commit()

        resp = await auth_client.get("/api/dashboard/history", params={"period": "1M"})
        data = resp.json()
        assert data["total_count"] == 1

    async def test_history_period_validation(self, auth_client: AsyncClient):
        """잘못된 period 값은 422 에러."""
        resp = await auth_client.get("/api/dashboard/history", params={"period": "INVALID"})
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestDashboardSnapshot:
    async def test_create_snapshot(self, auth_client: AsyncClient):
        """스냅샷 생성 성공."""
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "3000000", "purchase_price": "3000000",
        })

        resp = await auth_client.post("/api/dashboard/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["total_value_krw"]) == 3_000_000
        assert data["snapshot_date"] == date.today().isoformat()
        assert data["breakdown"] is not None

    async def test_upsert_same_day(self, auth_client: AsyncClient):
        """같은 날 두 번 스냅샷 → 업데이트 (중복 생성 안됨)."""
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "1000000", "purchase_price": "1000000",
        })

        resp1 = await auth_client.post("/api/dashboard/snapshot")
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        resp2 = await auth_client.post("/api/dashboard/snapshot")
        assert resp2.status_code == 200
        id2 = resp2.json()["id"]

        assert id1 == id2  # 같은 스냅샷이 업데이트됨

    async def test_snapshot_empty_portfolio(self, auth_client: AsyncClient):
        """자산 없을 때도 스냅샷 생성 가능 (총액 0)."""
        resp = await auth_client.post("/api/dashboard/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["total_value_krw"]) == 0

    async def test_snapshot_audit_log(
        self, auth_client: AsyncClient, mock_user: User, db_session: AsyncSession
    ):
        """스냅샷 생성 시 액세스 로그 기록."""
        resp = await auth_client.post("/api/dashboard/snapshot")
        assert resp.status_code == 200

        result = await db_session.execute(
            select(AccessLog).where(
                AccessLog.user_id == mock_user.id,
                AccessLog.action == "snapshot_create",
            )
        )
        logs = result.scalars().all()
        assert len(logs) >= 1
