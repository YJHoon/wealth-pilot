"""온보딩 완료 API 테스트"""

import uuid

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def onboarding_db():
    await engine.dispose()
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def user_no_2fa(onboarding_db: AsyncSession):
    """2FA 미설정 사용자 (온보딩 미완료)."""
    user = User(
        id=uuid.uuid4(),
        email="onboard-no2fa@example.com",
        name="온보딩 테스트",
        totp_enabled=False,
        onboarding_completed=False,
    )
    onboarding_db.add(user)
    await onboarding_db.commit()
    await onboarding_db.refresh(user)
    yield user
    await onboarding_db.delete(user)
    await onboarding_db.commit()


@pytest_asyncio.fixture
async def user_with_2fa(onboarding_db: AsyncSession):
    """2FA 설정 완료 사용자 (온보딩 미완료)."""
    user = User(
        id=uuid.uuid4(),
        email="onboard-2fa@example.com",
        name="온보딩 테스트 2FA",
        totp_enabled=True,
        onboarding_completed=False,
    )
    onboarding_db.add(user)
    await onboarding_db.commit()
    await onboarding_db.refresh(user)
    yield user
    await onboarding_db.delete(user)
    await onboarding_db.commit()


@pytest_asyncio.fixture
async def user_already_onboarded(onboarding_db: AsyncSession):
    """이미 온보딩 완료된 사용자."""
    user = User(
        id=uuid.uuid4(),
        email="onboard-done@example.com",
        name="온보딩 완료",
        totp_enabled=True,
        onboarding_completed=True,
    )
    onboarding_db.add(user)
    await onboarding_db.commit()
    await onboarding_db.refresh(user)
    yield user
    await onboarding_db.delete(user)
    await onboarding_db.commit()


def _make_auth_client(user: User):
    """get_current_user를 override한 인증 클라이언트 컨텍스트 매니저."""

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override

    class _Ctx:
        async def __aenter__(self):
            self._lm = LifespanManager(app)
            await self._lm.__aenter__()
            self._ac = AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            )
            return await self._ac.__aenter__()

        async def __aexit__(self, *exc):
            await self._ac.__aexit__(*exc)
            await self._lm.__aexit__(*exc)
            app.dependency_overrides.pop(get_current_user, None)

    return _Ctx()


@pytest.mark.asyncio
class TestCompleteOnboarding:
    async def test_success(self, user_with_2fa: User):
        """2FA 설정 완료 + 면책 동의 → 온보딩 완료."""
        async with _make_auth_client(user_with_2fa) as client:
            resp = await client.put(
                "/api/onboarding/complete",
                json={"disclaimer_agreed": True, "selected_asset_types": ["cash", "domestic_stock"]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["onboarding_completed"] is True

    async def test_disclaimer_not_agreed(self, user_with_2fa: User):
        """면책 미동의 → 400."""
        async with _make_auth_client(user_with_2fa) as client:
            resp = await client.put(
                "/api/onboarding/complete",
                json={"disclaimer_agreed": False, "selected_asset_types": []},
            )
        assert resp.status_code == 400
        assert "면책" in resp.json()["detail"]

    async def test_2fa_not_setup(self, user_no_2fa: User):
        """2FA 미설정 → 400."""
        async with _make_auth_client(user_no_2fa) as client:
            resp = await client.put(
                "/api/onboarding/complete",
                json={"disclaimer_agreed": True, "selected_asset_types": []},
            )
        assert resp.status_code == 400
        assert "2FA" in resp.json()["detail"] or "2단계" in resp.json()["detail"]

    async def test_already_onboarded(self, user_already_onboarded: User):
        """이미 완료된 사용자 → 성공 (멱등)."""
        async with _make_auth_client(user_already_onboarded) as client:
            resp = await client.put(
                "/api/onboarding/complete",
                json={"disclaimer_agreed": True, "selected_asset_types": []},
            )
        assert resp.status_code == 200
        assert resp.json()["onboarding_completed"] is True
