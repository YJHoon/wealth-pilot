"""보안 서비스 + 보안 헤더 미들웨어 테스트"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.access_log import AccessLog
from app.services.security_service import (
    AccessAction,
    check_new_device,
    check_rapid_login_attempts,
    detect_anomalies,
    log_access,
)


def _make_request(ip: str = "127.0.0.1", user_agent: str = "TestAgent"):
    """테스트용 Request mock 생성."""
    request = MagicMock()
    request.client.host = ip
    request.headers.get = lambda key, default="": user_agent if key == "user-agent" else default
    return request


class TestLogAccess:
    @pytest.mark.asyncio
    async def test_creates_access_log_with_correct_fields(self):
        """log_access가 올바른 필드로 AccessLog를 생성하는지 검증."""
        db = AsyncMock()
        user_id = uuid.uuid4()
        request = _make_request(ip="1.2.3.4", user_agent="Chrome/100")

        log = await log_access(db, user_id, AccessAction.LOGIN, request)

        assert isinstance(log, AccessLog)
        assert log.user_id == user_id
        assert log.action == "login"
        assert log.ip_address == "1.2.3.4"
        assert log.device_info == "Chrome/100"
        assert log.is_suspicious is False
        assert log.expires_at > datetime.now(timezone.utc) + timedelta(days=364)
        db.add.assert_called_once_with(log)

    @pytest.mark.asyncio
    async def test_suspicious_flag(self):
        """is_suspicious=True 설정 검증."""
        db = AsyncMock()
        log = await log_access(
            db, uuid.uuid4(), AccessAction.LOGIN_FAILURE, _make_request(),
            is_suspicious=True,
        )
        assert log.is_suspicious is True

    @pytest.mark.asyncio
    async def test_device_info_override(self):
        """device_info_override가 user-agent보다 우선."""
        db = AsyncMock()
        log = await log_access(
            db, uuid.uuid4(), AccessAction.SESSION_REVOKE, _make_request(),
            device_info_override="revoked session: abc",
        )
        assert log.device_info == "revoked session: abc"


class TestCheckNewDevice:
    @pytest.mark.asyncio
    async def test_returns_true_for_new_device(self):
        """과거 기록 없으면 True."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        db.execute.return_value = mock_result

        result = await check_new_device(db, uuid.uuid4(), "1.2.3.4", "Chrome")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_known_device(self):
        """과거 기록 있으면 False."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        db.execute.return_value = mock_result

        result = await check_new_device(db, uuid.uuid4(), "1.2.3.4", "Chrome")
        assert result is False


class TestCheckRapidLoginAttempts:
    @pytest.mark.asyncio
    async def test_returns_true_when_rapid(self):
        """5분 내 3회 이상이면 True."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        db.execute.return_value = mock_result

        result = await check_rapid_login_attempts(db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_normal(self):
        """5분 내 3회 미만이면 False."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        db.execute.return_value = mock_result

        result = await check_rapid_login_attempts(db, uuid.uuid4())
        assert result is False


class TestDetectAnomalies:
    @pytest.mark.asyncio
    async def test_sends_alert_on_new_device(self):
        """새 기기 감지 시 텔레그램 알림 발송."""
        with (
            patch("app.services.security_service.check_new_device", new_callable=AsyncMock) as mock_new,
            patch("app.services.security_service.check_rapid_login_attempts", new_callable=AsyncMock) as mock_rapid,
            patch("app.services.security_service.send_security_alert", new_callable=AsyncMock) as mock_alert,
        ):
            mock_new.return_value = True
            mock_rapid.return_value = False

            result = await detect_anomalies(
                AsyncMock(), uuid.uuid4(), "user@test.com", _make_request()
            )

            assert result is True
            mock_alert.assert_called_once_with(
                "new_device_login", "user@test.com", "127.0.0.1", "TestAgent"
            )

    @pytest.mark.asyncio
    async def test_sends_alert_on_rapid_attempts(self):
        """빠른 반복 로그인 감지 시 텔레그램 알림 발송."""
        with (
            patch("app.services.security_service.check_new_device", new_callable=AsyncMock) as mock_new,
            patch("app.services.security_service.check_rapid_login_attempts", new_callable=AsyncMock) as mock_rapid,
            patch("app.services.security_service.send_security_alert", new_callable=AsyncMock) as mock_alert,
        ):
            mock_new.return_value = False
            mock_rapid.return_value = True

            result = await detect_anomalies(
                AsyncMock(), uuid.uuid4(), "user@test.com", _make_request()
            )

            assert result is True
            mock_alert.assert_called_once_with(
                "repeated_login_failures", "user@test.com", "127.0.0.1", "TestAgent"
            )

    @pytest.mark.asyncio
    async def test_no_anomaly(self):
        """이상 없으면 False."""
        with (
            patch("app.services.security_service.check_new_device", new_callable=AsyncMock) as mock_new,
            patch("app.services.security_service.check_rapid_login_attempts", new_callable=AsyncMock) as mock_rapid,
        ):
            mock_new.return_value = False
            mock_rapid.return_value = False

            result = await detect_anomalies(
                AsyncMock(), uuid.uuid4(), "user@test.com", _make_request()
            )
            assert result is False


class TestSecurityHeaders:
    """보안 헤더 미들웨어 테스트 — /health 엔드포인트로 검증."""

    @pytest.mark.asyncio
    async def test_security_headers_present(self, client):
        """응답에 보안 헤더가 포함되는지 검증."""
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["x-xss-protection"] == "0"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "default-src 'none'" in resp.headers["content-security-policy"]
        assert "camera=()" in resp.headers["permissions-policy"]
