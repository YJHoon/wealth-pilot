"""TOTP 서비스 단위 테스트"""

import pyotp
import pytest

from app.services.totp_service import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_qr_code,
    generate_totp_secret,
    verify_totp_code,
)


class TestTotpService:
    """TOTP 2FA 서비스 테스트"""

    def test_generate_secret(self):
        secret = generate_totp_secret()
        assert len(secret) > 0
        # base32 문자열인지 확인
        assert secret.isalnum()

    def test_encrypt_decrypt_secret(self):
        secret = generate_totp_secret()
        encrypted = encrypt_totp_secret(secret)

        assert encrypted != secret  # 암호화됨
        decrypted = decrypt_totp_secret(encrypted)
        assert decrypted == secret  # 복호화하면 원래 값

    def test_generate_qr_code(self):
        secret = generate_totp_secret()
        qr_base64, uri = generate_qr_code(secret, "test@example.com")

        assert len(qr_base64) > 0
        assert "otpauth://totp/" in uri
        assert "WealthPilot" in uri
        assert "test" in uri and "example.com" in uri

    def test_verify_valid_code(self):
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        assert verify_totp_code(secret, code) is True

    def test_verify_invalid_code(self):
        secret = generate_totp_secret()
        assert verify_totp_code(secret, "000000") is False

    def test_verify_wrong_length_code(self):
        secret = generate_totp_secret()
        assert verify_totp_code(secret, "12345") is False
