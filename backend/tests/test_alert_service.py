"""텔레그램 알림 서비스 테스트"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.alert_service import escape_html, send_telegram_message, send_security_alert


@pytest.mark.asyncio
async def test_send_telegram_message_skips_when_no_token():
    """토큰/채팅 ID 미설정 시 전송 건너뛰기."""
    with patch("app.services.alert_service.settings") as mock_settings:
        mock_settings.telegram_bot_token = ""
        mock_settings.telegram_chat_id = ""
        result = await send_telegram_message("test message")
        assert result is False


@pytest.mark.asyncio
async def test_send_telegram_message_success():
    """정상 전송 시 True 반환."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None

    with (
        patch("app.services.alert_service.settings") as mock_settings,
        patch("app.services.alert_service.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.telegram_bot_token = "test-token"
        mock_settings.telegram_chat_id = "12345"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_telegram_message("test message")
        assert result is True
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_telegram_message_failure_does_not_raise():
    """Telegram API 실패 시 예외 발생하지 않고 False 반환."""
    with (
        patch("app.services.alert_service.settings") as mock_settings,
        patch("app.services.alert_service.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.telegram_bot_token = "test-token"
        mock_settings.telegram_chat_id = "12345"

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection error")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_telegram_message("test message")
        assert result is False


@pytest.mark.asyncio
async def test_send_security_alert_formats_message():
    """보안 알림 타입에 맞게 메시지 포맷팅."""
    with patch("app.services.alert_service.send_telegram_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        result = await send_security_alert(
            "new_device_login", "user@test.com", "1.2.3.4", "Chrome"
        )
        assert result is True
        call_args = mock_send.call_args[0][0]
        assert "user@test.com" in call_args
        assert "1.2.3.4" in call_args
        assert "Chrome" in call_args


@pytest.mark.asyncio
async def test_send_security_alert_unknown_type():
    """알 수 없는 alert_type이면 False 반환."""
    result = await send_security_alert(
        "unknown_type", "user@test.com", "1.2.3.4", "Chrome"
    )
    assert result is False


class TestEscapeHtml:
    def test_escapes_angle_brackets(self):
        assert escape_html("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"

    def test_escapes_ampersand(self):
        assert escape_html("A&B") == "A&amp;B"

    def test_plain_text_unchanged(self):
        assert escape_html("삼성전자") == "삼성전자"

    def test_non_string_converted(self):
        assert escape_html(12345) == "12345"


@pytest.mark.asyncio
async def test_send_telegram_message_escapes_by_default():
    """기본적으로 HTML 이스케이프 적용."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None

    with (
        patch("app.services.alert_service.settings") as mock_settings,
        patch("app.services.alert_service.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.telegram_bot_token = "test-token"
        mock_settings.telegram_chat_id = "12345"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await send_telegram_message("<b>bold</b>")
        payload = mock_client.post.call_args[1]["json"]
        assert "&lt;b&gt;" in payload["text"]


@pytest.mark.asyncio
async def test_send_telegram_message_pre_escaped_passthrough():
    """pre_escaped=True 시 이스케이프 건너뜀."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None

    with (
        patch("app.services.alert_service.settings") as mock_settings,
        patch("app.services.alert_service.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.telegram_bot_token = "test-token"
        mock_settings.telegram_chat_id = "12345"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await send_telegram_message("<b>bold</b>", pre_escaped=True)
        payload = mock_client.post.call_args[1]["json"]
        assert "<b>bold</b>" in payload["text"]
