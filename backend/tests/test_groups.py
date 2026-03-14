"""포트폴리오 그룹 CRUD API 테스트"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.asset import Asset, AssetType, Currency
from app.models.portfolio_group import PortfolioGroup
from app.models.user import User
from app.services.crypto_service import encrypt_decimal


@pytest.mark.asyncio
class TestListGroups:
    async def test_empty_list(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert data["groups"] == []
        assert data["total"] == 0

    async def test_asset_count(self, auth_client: AsyncClient, mock_user: User, db_session):
        # 그룹 생성
        resp = await auth_client.post("/api/groups", json={"name": "주식"})
        assert resp.status_code == 201
        group_id = resp.json()["id"]

        # 자산 추가 (그룹 소속)
        await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
            "name": "삼성전자",
            "currency": "KRW",
            "quantity": "10",
            "purchase_price": "70000",
            "group_id": group_id,
        })

        resp = await auth_client.get("/api/groups")
        assert resp.status_code == 200
        groups = resp.json()["groups"]
        assert len(groups) == 1
        assert groups[0]["asset_count"] == 1


@pytest.mark.asyncio
class TestCreateGroup:
    async def test_success(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/groups", json={
            "name": "테스트 그룹",
            "description": "설명",
            "sort_order": 1,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "테스트 그룹"
        assert data["description"] == "설명"
        assert data["sort_order"] == 1
        assert data["asset_count"] == 0

    async def test_name_required(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/groups", json={})
        assert resp.status_code == 422

    async def test_name_max_length(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/groups", json={"name": "a" * 101})
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestUpdateGroup:
    async def test_success(self, auth_client: AsyncClient):
        # 생성
        resp = await auth_client.post("/api/groups", json={"name": "원래 이름"})
        group_id = resp.json()["id"]

        # 수정
        resp = await auth_client.put(f"/api/groups/{group_id}", json={"name": "새 이름"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "새 이름"

    async def test_not_found(self, auth_client: AsyncClient):
        import uuid
        fake_id = str(uuid.uuid4())
        resp = await auth_client.put(f"/api/groups/{fake_id}", json={"name": "x"})
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestDeleteGroup:
    async def test_success(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/groups", json={"name": "삭제할 그룹"})
        group_id = resp.json()["id"]

        resp = await auth_client.delete(f"/api/groups/{group_id}")
        assert resp.status_code == 204

        # 삭제 확인
        resp = await auth_client.get("/api/groups")
        assert resp.json()["total"] == 0

    async def test_assets_group_id_nullified(self, auth_client: AsyncClient):
        # 그룹 생성
        resp = await auth_client.post("/api/groups", json={"name": "삭제 대상"})
        group_id = resp.json()["id"]

        # 자산 추가
        resp = await auth_client.post("/api/assets", json={
            "type": "cash",
            "name": "예금",
            "currency": "KRW",
            "quantity": "1000000",
            "purchase_price": "1000000",
            "group_id": group_id,
        })
        asset_id = resp.json()["id"]

        # 그룹 삭제
        resp = await auth_client.delete(f"/api/groups/{group_id}")
        assert resp.status_code == 204

        # 자산의 group_id가 null인지 확인
        resp = await auth_client.get("/api/assets")
        assets = resp.json()["assets"]
        matched = [a for a in assets if a["id"] == asset_id]
        assert len(matched) == 1
        assert matched[0]["group_id"] is None

    async def test_not_found(self, auth_client: AsyncClient):
        import uuid
        resp = await auth_client.delete(f"/api/groups/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestGroupOwnership:
    """타 유저의 그룹에 대한 접근 차단 테스트."""

    async def test_other_user_cannot_update_or_delete_group(
        self, auth_client: AsyncClient, other_user: User, db_session
    ):
        """다른 유저의 그룹을 수정/삭제하려 하면 404 반환."""
        # other_user 소유 그룹을 DB에 직접 생성
        group = PortfolioGroup(
            user_id=other_user.id,
            name="다른 유저의 그룹",
        )
        db_session.add(group)
        await db_session.commit()
        await db_session.refresh(group)

        # auth_client(mock_user)로 수정 시도 → 404
        resp = await auth_client.put(
            f"/api/groups/{group.id}", json={"name": "탈취"}
        )
        assert resp.status_code == 404

        # auth_client(mock_user)로 삭제 시도 → 404
        resp = await auth_client.delete(f"/api/groups/{group.id}")
        assert resp.status_code == 404
