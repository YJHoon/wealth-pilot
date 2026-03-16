"""포트폴리오 그룹 CRUD 테스트"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.main import app
from app.models.asset import Asset
from app.models.portfolio_group import PortfolioGroup
from app.models.user import User

TEST_USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _make_test_user(user_id: uuid.UUID = TEST_USER_ID) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.email = "test@example.com"
    user.name = "Test User"
    user.totp_enabled = True
    return user


def _make_group(
    user_id: uuid.UUID = TEST_USER_ID,
    group_id: uuid.UUID | None = None,
    name: str = "테스트 그룹",
) -> PortfolioGroup:
    group = MagicMock(spec=PortfolioGroup)
    group.id = group_id or uuid.uuid4()
    group.user_id = user_id
    group.name = name
    group.description = None
    group.sort_order = 0
    group.created_at = datetime.now(timezone.utc)
    return group


@pytest_asyncio.fixture
async def auth_client():
    """인증 우회 + DB mock이 적용된 테스트 클라이언트."""
    mock_db = AsyncMock()
    mock_user = _make_test_user()

    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            ac._mock_db = mock_db
            ac._mock_user = mock_user
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client():
    """인증 없는 테스트 클라이언트."""
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# --- 인증 테스트 ---


class TestAuthRequired:
    @pytest.mark.asyncio
    async def test_list_groups_without_token(self, unauth_client):
        """토큰 없이 그룹 목록 요청 시 403."""
        resp = await unauth_client.get("/api/groups")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_group_without_token(self, unauth_client):
        """토큰 없이 그룹 생성 요청 시 403."""
        resp = await unauth_client.post("/api/groups", json={"name": "테스트"})
        assert resp.status_code == 403


# --- 서비스 레이어 단위 테스트 ---


class TestGroupService:
    @pytest.mark.asyncio
    async def test_create_group(self):
        """그룹 생성."""
        from app.schemas.group import GroupCreateRequest
        from app.services.group_service import create_group

        db = AsyncMock()
        body = GroupCreateRequest(name="국내 주식", description="한국 주식 포트폴리오")

        group = await create_group(db, TEST_USER_ID, body)

        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        added = db.add.call_args[0][0]
        assert added.name == "국내 주식"
        assert added.description == "한국 주식 포트폴리오"
        assert added.user_id == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_get_group_not_found(self):
        """존재하지 않는 그룹 조회 시 404."""
        from app.services.group_service import get_group_by_id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(Exception) as exc_info:
            await get_group_by_id(db, TEST_USER_ID, uuid.uuid4())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_group_forbidden(self):
        """다른 사용자 그룹 접근 시 403."""
        from app.services.group_service import get_group_by_id

        db = AsyncMock()
        group = _make_group(user_id=OTHER_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = group
        db.execute.return_value = mock_result

        with pytest.raises(Exception) as exc_info:
            await get_group_by_id(db, TEST_USER_ID, group.id)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_group(self):
        """그룹 수정."""
        from app.schemas.group import GroupUpdateRequest
        from app.services.group_service import update_group

        db = AsyncMock()
        group = _make_group()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = group
        db.execute.return_value = mock_result

        body = GroupUpdateRequest(name="변경된 이름", sort_order=5)
        result = await update_group(db, TEST_USER_ID, group.id, body)

        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_group(self):
        """그룹 삭제."""
        from app.services.group_service import delete_group

        db = AsyncMock()
        group = _make_group()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = group
        db.execute.return_value = mock_result

        await delete_group(db, TEST_USER_ID, group.id)

        db.delete.assert_awaited_once_with(group)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_asset_count(self):
        """그룹의 자산 수 조회."""
        from app.services.group_service import get_asset_count

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        db.execute.return_value = mock_result

        count = await get_asset_count(db, uuid.uuid4())
        assert count == 3

    @pytest.mark.asyncio
    async def test_group_to_response(self):
        """group_to_response가 asset_count를 포함."""
        from app.services.group_service import get_asset_count, group_to_response

        db = AsyncMock()
        group = _make_group(name="해외 주식")

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        db.execute.return_value = mock_result

        response = await group_to_response(db, group)

        assert response.name == "해외 주식"
        assert response.asset_count == 5


# --- 유효성 검증 테스트 ---


class TestGroupValidation:
    @pytest.mark.asyncio
    async def test_empty_name_rejected(self, auth_client):
        """빈 이름 → 422."""
        resp = await auth_client.post("/api/groups", json={"name": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_name_too_long_rejected(self, auth_client):
        """100자 초과 이름 → 422."""
        resp = await auth_client.post("/api/groups", json={"name": "a" * 101})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_name_rejected(self, auth_client):
        """이름 누락 → 422."""
        resp = await auth_client.post("/api/groups", json={})
        assert resp.status_code == 422
