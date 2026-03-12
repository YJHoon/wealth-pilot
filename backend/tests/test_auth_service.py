"""인증 서비스 단위 테스트"""

import uuid

import pytest

from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    verify_token,
)


class TestJWT:
    """JWT 토큰 생성/검증 테스트"""

    def test_create_and_verify_access_token(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id)

        payload = verify_token(token, expected_type="access")
        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"

    def test_create_and_verify_refresh_token(self):
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)

        payload = verify_token(token, expected_type="refresh")
        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"

    def test_access_token_rejected_as_refresh(self):
        """Access Token을 Refresh Token으로 사용하면 거부"""
        user_id = uuid.uuid4()
        token = create_access_token(user_id)

        payload = verify_token(token, expected_type="refresh")
        assert payload is None

    def test_refresh_token_rejected_as_access(self):
        """Refresh Token을 Access Token으로 사용하면 거부"""
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)

        payload = verify_token(token, expected_type="access")
        assert payload is None

    def test_invalid_token_returns_none(self):
        payload = verify_token("invalid.token.here", expected_type="access")
        assert payload is None

    def test_empty_token_returns_none(self):
        payload = verify_token("", expected_type="access")
        assert payload is None
