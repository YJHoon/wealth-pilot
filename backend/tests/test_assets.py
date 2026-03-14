"""자산 관리 CRUD API 테스트"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
class TestListAssets:
    async def test_empty_list(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/assets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["assets"] == []
        assert data["total"] == 0

    async def test_filter_by_type(self, auth_client: AsyncClient):
        # 두 종류 자산 생성
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "1000000", "purchase_price": "1000000",
        })
        await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "삼성전자", "currency": "KRW",
            "quantity": "10", "purchase_price": "70000",
        })

        resp = await auth_client.get("/api/assets", params={"type": "cash"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["assets"][0]["type"] == "cash"

    async def test_filter_by_status(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/assets", params={"status_filter": "sold"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_filter_by_group_id(self, auth_client: AsyncClient):
        # 그룹 생성
        group_resp = await auth_client.post("/api/groups", json={"name": "테스트"})
        group_id = group_resp.json()["id"]

        # 그룹 소속 자산
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "그룹 자산", "currency": "KRW",
            "quantity": "500000", "purchase_price": "500000",
            "group_id": group_id,
        })
        # 그룹 미소속 자산
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "일반 자산", "currency": "KRW",
            "quantity": "300000", "purchase_price": "300000",
        })

        resp = await auth_client.get("/api/assets", params={"group_id": group_id})
        assert resp.json()["total"] == 1
        assert resp.json()["assets"][0]["name"] == "그룹 자산"


@pytest.mark.asyncio
class TestCreateAsset:
    async def test_success(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
            "name": "삼성전자",
            "ticker": "005930",
            "currency": "KRW",
            "quantity": "10",
            "purchase_price": "70000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "삼성전자"
        assert data["ticker"] == "005930"
        assert Decimal(data["quantity"]) == Decimal("10")
        assert Decimal(data["purchase_price"]) == Decimal("70000")
        assert data["status"] == "active"

    async def test_with_group(self, auth_client: AsyncClient):
        group_resp = await auth_client.post("/api/groups", json={"name": "주식"})
        group_id = group_resp.json()["id"]

        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
            "name": "카카오",
            "currency": "KRW",
            "quantity": "5",
            "purchase_price": "50000",
            "group_id": group_id,
        })
        assert resp.status_code == 201
        assert resp.json()["group_id"] == group_id

    async def test_invalid_group_404(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "cash",
            "name": "예금",
            "currency": "KRW",
            "quantity": "1000",
            "purchase_price": "1000",
            "group_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 404

    async def test_required_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={"name": "불완전"})
        assert resp.status_code == 422

    async def test_quantity_must_be_positive(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "cash", "name": "예금", "currency": "KRW",
            "quantity": "0", "purchase_price": "1000",
        })
        assert resp.status_code == 422

    async def test_db_encryption(self, auth_client: AsyncClient, db_session):
        """DB에 저장된 값이 암호화되어 있는지 확인."""
        resp = await auth_client.post("/api/assets", json={
            "type": "cash", "name": "암호화 테스트", "currency": "KRW",
            "quantity": "999999", "purchase_price": "888888",
        })
        assert resp.status_code == 201
        asset_id = resp.json()["id"]

        from sqlalchemy import text
        result = await db_session.execute(
            text("SELECT quantity, purchase_price FROM assets WHERE id = :id"),
            {"id": asset_id},
        )
        row = result.one()
        # DB 값은 평문 숫자가 아니라 base64 암호문이어야 함
        assert row[0] != "999999"
        assert row[1] != "888888"


@pytest.mark.asyncio
class TestUpdateAsset:
    async def _create_asset(self, client: AsyncClient) -> str:
        resp = await client.post("/api/assets", json={
            "type": "domestic_stock", "name": "원래 자산", "currency": "KRW",
            "quantity": "10", "purchase_price": "50000",
        })
        return resp.json()["id"]

    async def test_success(self, auth_client: AsyncClient):
        asset_id = await self._create_asset(auth_client)
        resp = await auth_client.put(f"/api/assets/{asset_id}", json={"name": "수정된 이름"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "수정된 이름"

    async def test_partial_update(self, auth_client: AsyncClient):
        asset_id = await self._create_asset(auth_client)
        resp = await auth_client.put(f"/api/assets/{asset_id}", json={
            "quantity": "20",
        })
        assert resp.status_code == 200
        assert Decimal(resp.json()["quantity"]) == Decimal("20")
        # purchase_price 변경 없음
        assert Decimal(resp.json()["purchase_price"]) == Decimal("50000")

    async def test_sold_asset_cannot_be_updated(self, auth_client: AsyncClient):
        asset_id = await self._create_asset(auth_client)
        # 매도
        await auth_client.post(f"/api/assets/{asset_id}/sell", json={"sold_price": "60000"})
        # 수정 시도
        resp = await auth_client.put(f"/api/assets/{asset_id}", json={"name": "변경"})
        assert resp.status_code == 403

    async def test_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.put(f"/api/assets/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestDeleteAsset:
    async def test_success(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "cash", "name": "삭제 대상", "currency": "KRW",
            "quantity": "1000", "purchase_price": "1000",
        })
        asset_id = resp.json()["id"]

        resp = await auth_client.delete(f"/api/assets/{asset_id}")
        assert resp.status_code == 204

        # 삭제 확인
        resp = await auth_client.get("/api/assets")
        ids = [a["id"] for a in resp.json()["assets"]]
        assert asset_id not in ids

    async def test_sold_asset_cannot_be_deleted(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "매도 자산", "currency": "KRW",
            "quantity": "5", "purchase_price": "40000",
        })
        asset_id = resp.json()["id"]
        await auth_client.post(f"/api/assets/{asset_id}/sell", json={"sold_price": "50000"})

        resp = await auth_client.delete(f"/api/assets/{asset_id}")
        assert resp.status_code == 403

    async def test_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/assets/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestSellAsset:
    async def test_success(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "매도 테스트", "currency": "KRW",
            "quantity": "10", "purchase_price": "50000",
        })
        asset_id = resp.json()["id"]

        resp = await auth_client.post(f"/api/assets/{asset_id}/sell", json={
            "sold_price": "60000",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sold"
        assert Decimal(data["sold_price"]) == Decimal("60000")
        assert data["sold_at"] is not None

    async def test_realized_pnl_calculation(self, auth_client: AsyncClient):
        """realized_pnl = (sold_price - purchase_price) * quantity"""
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "PnL 테스트", "currency": "KRW",
            "quantity": "10", "purchase_price": "50000",
        })
        asset_id = resp.json()["id"]

        resp = await auth_client.post(f"/api/assets/{asset_id}/sell", json={
            "sold_price": "60000",
        })
        data = resp.json()
        # (60000 - 50000) * 10 = 100000
        assert Decimal(data["realized_pnl"]) == Decimal("100000")

    async def test_cash_asset_created(self, auth_client: AsyncClient):
        """매도 시 현금 자산이 자동 생성되어야 함."""
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "현금 생성 테스트", "currency": "KRW",
            "quantity": "10", "purchase_price": "50000",
        })
        asset_id = resp.json()["id"]

        await auth_client.post(f"/api/assets/{asset_id}/sell", json={
            "sold_price": "60000",
        })

        # 현금 자산 확인: 총 매도대금 = 60000 * 10 = 600000
        resp = await auth_client.get("/api/assets", params={"type": "cash"})
        cash_assets = resp.json()["assets"]
        assert len(cash_assets) >= 1
        cash = [a for a in cash_assets if a["name"] == "매도 수익금"]
        assert len(cash) == 1
        assert Decimal(cash[0]["quantity"]) == Decimal("600000")

    async def test_cash_asset_merged(self, auth_client: AsyncClient):
        """기존 현금 자산이 있으면 합산."""
        # 기존 현금
        await auth_client.post("/api/assets", json={
            "type": "cash", "name": "매도 수익금", "currency": "KRW",
            "quantity": "100000", "purchase_price": "100000",
        })

        # 주식 매도
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "합산 테스트", "currency": "KRW",
            "quantity": "5", "purchase_price": "40000",
        })
        asset_id = resp.json()["id"]

        await auth_client.post(f"/api/assets/{asset_id}/sell", json={
            "sold_price": "50000",
        })

        # 기존 100000 + 매도대금 250000(50000*5) = 350000
        resp = await auth_client.get("/api/assets", params={"type": "cash", "status_filter": "active"})
        cash_assets = [a for a in resp.json()["assets"] if a["currency"] == "KRW"]
        total_cash = sum(Decimal(a["quantity"]) for a in cash_assets)
        assert total_cash == Decimal("350000")

    async def test_already_sold_403(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock", "name": "이미 매도", "currency": "KRW",
            "quantity": "10", "purchase_price": "50000",
        })
        asset_id = resp.json()["id"]

        await auth_client.post(f"/api/assets/{asset_id}/sell", json={"sold_price": "60000"})
        resp = await auth_client.post(f"/api/assets/{asset_id}/sell", json={"sold_price": "70000"})
        assert resp.status_code == 403

    async def test_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/assets/{uuid.uuid4()}/sell", json={
            "sold_price": "50000",
        })
        assert resp.status_code == 404
