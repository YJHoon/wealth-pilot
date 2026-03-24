import uuid

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, get_db, AsyncSessionLocal
from app.dependencies.auth import get_current_active_user
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def client():
    # LifespanManager로 lifespan 이벤트(startup/shutdown) 실행 (DB 연결 초기화 포함)
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


@pytest_asyncio.fixture
async def db_session():
    """테스트용 DB 세션 — 이전 이벤트 루프에 바인딩된 커넥션 풀 정리."""
    await engine.dispose()
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def mock_user(db_session: AsyncSession):
    """테스트용 사용자 생성."""
    # 이전 테스트 실행에서 남은 잔여 데이터 정리
    await db_session.execute(text(
        "DELETE FROM users WHERE email = 'test@example.com'"
    ))
    await db_session.commit()

    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="테스트 유저",
        totp_enabled=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    yield user
    # cleanup: API 테스트에서 생성된 관련 데이터를 먼저 삭제 (cascade 충돌 방지)
    user_id = str(user.id)
    await db_session.execute(text(f"DELETE FROM trading_orders WHERE user_id = '{user_id}'"))
    await db_session.execute(text(f"DELETE FROM trading_schedule_logs WHERE user_id = '{user_id}'"))
    await db_session.execute(text(f"DELETE FROM trading_positions WHERE user_id = '{user_id}'"))
    await db_session.execute(text(f"DELETE FROM trading_strategies WHERE user_id = '{user_id}'"))
    await db_session.execute(text(f"DELETE FROM trading_accounts WHERE user_id = '{user_id}'"))
    await db_session.execute(text(f"DELETE FROM access_logs WHERE user_id = '{user_id}'"))
    await db_session.execute(text(f"DELETE FROM users WHERE id = '{user_id}'"))
    await db_session.commit()


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession):
    """다른 사용자 (소유권 검증 테스트용)."""
    user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        name="다른 유저",
        totp_enabled=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    yield user
    user_id = str(user.id)
    await db_session.execute(text(f"DELETE FROM users WHERE id = '{user_id}'"))
    await db_session.commit()


@pytest_asyncio.fixture
async def auth_client(mock_user: User):
    """인증된 테스트 클라이언트 — get_current_active_user를 override."""

    async def _override_auth():
        return mock_user

    app.dependency_overrides[get_current_active_user] = _override_auth

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.pop(get_current_active_user, None)
